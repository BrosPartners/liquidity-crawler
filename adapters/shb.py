"""Adapter SHB (Ngân hàng TMCP Sài Gòn - Hà Nội) — PDF chính thức, pdfplumber.

Trang HTML lãi suất của SHB (shb.com.vn, ibanking.shb.com.vn) bị WAF chặn với
CẢ httpx lẫn Playwright headless (403 "Xác minh bảo mật"). Tuy nhiên file PDF
tĩnh dưới /wp-content/uploads/ KHÔNG bị WAF chặn (200 OK qua httpx thường).
SHB dùng 1 URL CỐ ĐỊNH cho biểu lãi suất hiện hành, tự đè nội dung mỗi kỳ
điều chỉnh (tên file còn "Thang-6" nhưng Last-Modified luôn là ngày cập nhật
mới nhất — xác nhận qua header, không phải file tháng 6 cũ).

PDF có nhiều bảng; 2 bảng lãi suất tiền gửi cá nhân VND theo kỳ hạn (mục 1 và
mục 4 trong văn bản):
  - Mục 1 "Biểu lãi suất tiết kiệm bậc thang" (không nhãn "online")
    -> product = "quay". Có 2 dòng "Cuối kỳ" theo mức tiền (< 2 tỷ / >= 2 tỷ);
    lấy mức thấp nhất "< 2 tỷ" cho đại diện khách hàng cá nhân phổ thông.
  - Mục 4 "Biểu lãi suất Tiền gửi tiết kiệm online..." -> product = "online".
    Không có mức tiền, chỉ 1 dòng "Cuối kỳ".
Nhận diện bảng: có dòng mà ô đầu chứa "cuối kỳ" VÀ hàng header cùng bảng có
≥8 ô parse được thành kỳ hạn (loại các bảng nhỏ mục 2/3/5 không đủ kỳ hạn).
Thứ tự xuất hiện trong PDF: bảng đạt điều kiện đầu tiên = quầy, bảng thứ 2 = online.

Đối chiếu PDF 2026-07 (quầy): 1M=4.40, 3M=4.50, 6M=5.80, 9M=5.80, 12M=6.20.
Đối chiếu PDF 2026-07 (online): 1M=4.60, 3M=4.65, 6M=6.20, 9M=6.40, 12M=6.50.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import List, Optional

import httpx

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate

PDF_URL = (
    "https://www.shb.com.vn/wp-content/uploads/2023/02/"
    "01.-BIEU-LS-HDV-VND-KHCN-Thang-6.pdf"
)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _term(cell) -> Optional[str]:
    # PDF đôi khi tách "1 T" có khoảng trắng giữa số và chữ -> gộp lại trước khi parse.
    return parse_term(re.sub(r"\s+", "", str(cell or "")))


class Adapter:
    code = "SHB"
    name = "SHB"
    url = PDF_URL

    def __init__(self, headful: bool = False):
        pass  # giữ tương thích interface

    def fetch(self) -> List[RateRow]:
        import pdfplumber

        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30, http2=False) as client:
            r = client.get(PDF_URL)
            r.raise_for_status()
            pdf_bytes = r.content

        rows: List[RateRow] = []
        seen: set = set()
        table_n = 0

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if not any(row and "cuối" in _norm(row[0]) and "kỳ" in _norm(row[0])
                               for row in table):
                        continue
                    # Header = dòng có nhiều ô parse được thành kỳ hạn nhất (6 dòng đầu).
                    best_hi, best_n = None, 0
                    for hi, hrow in enumerate(table[:6]):
                        n = sum(1 for c in (hrow or []) if _term(c) is not None)
                        if n > best_n:
                            best_n, best_hi = n, hi
                    if best_n < 8:
                        continue  # bảng nhỏ (mục 2/3/5), không phải lịch kỳ hạn đầy đủ

                    header = table[best_hi]
                    product = "quay" if table_n == 0 else "online"
                    table_n += 1

                    # Dòng "Cuối kỳ" mức thấp nhất (nếu có cột mức tiền "< 2 tỷ").
                    chosen = None
                    for row in table:
                        cell0 = _norm(row[0]) if row else ""
                        if "cuối" in cell0 and "kỳ" in cell0:
                            if chosen is None:
                                chosen = row
                            if len(row) > 3 and "<" in _norm(row[3]):
                                chosen = row
                                break
                    if chosen is None:
                        continue

                    for i, hcell in enumerate(header):
                        term = _term(hcell)
                        if term is None or i >= len(chosen):
                            continue
                        rate = parse_rate(chosen[i])
                        if rate is None:
                            continue
                        row_obj = RateRow(
                            date=today, bank_code=self.code, bank_name=self.name,
                            term=term, rate=rate, product=product,
                            source_url=PDF_URL, crawled_at=now,
                        )
                        if row_obj.key() not in seen:
                            seen.add(row_obj.key())
                            rows.append(row_obj)

        return rows
