"""Adapter Sacombank (STB) — PDF parsing với pdfplumber.

Sacombank công bố lãi suất dưới dạng PDF tại URL cố định.
PDF có bảng phức tạp: mỗi kỳ hạn × 3 mức tiền × 4 kiểu trả lãi.
Ta lấy: mức tiền thấp nhất (< 500M), lãi cuối kỳ (cột đầu tiên trong group).

Chiến lược: dùng pdfplumber.extract_tables(), tìm dòng có kỳ hạn,
lấy giá trị đầu tiên khác rỗng sau cột kỳ hạn.
"""
from __future__ import annotations

import io
from typing import List, Tuple

import httpx

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate
import datetime as _dt

PDF_URL = (
    "https://www.sacombank.com.vn/content/dam/sacombank/files/"
    "cong-cu/lai-suat/tien-gui/khcn/"
    "SACOMBANK_LAISUATNIEMYETTAIQUAY_KHCN_VIE.pdf"
)


class Adapter:
    code = "STB"
    name = "Sacombank"
    url = PDF_URL

    def __init__(self, headful: bool = False):
        pass

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

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    # Tìm cột "Lãi cuối kỳ" trong 1-3 dòng header đầu.
                    # Chỉ parse bảng có cột này (bỏ qua bảng khuyến mãi/
                    # "Mốc lãi suất" trả lãi trước có số liệu gây nhiễu).
                    rate_col = None
                    header_idx = None
                    for hi, hrow in enumerate(table[:3]):
                        for j, cell in enumerate(hrow or []):
                            norm = (cell or "").lower().replace("\n", " ")
                            if "cuối" in norm and "kỳ" in norm:
                                rate_col = j
                                header_idx = hi
                                break
                        if rate_col is not None:
                            break
                    if rate_col is None:
                        continue

                    for row in table[header_idx + 1:]:
                        if not row or not row[0]:
                            continue
                        term_txt = str(row[0]).lower()
                        # Bỏ dòng gộp kỳ hạn ("Từ 6 - 11 tháng", "Dưới 1 tháng")
                        if "dưới" in term_txt or "từ" in term_txt or "-" in term_txt:
                            continue
                        term = parse_term(str(row[0]))
                        if term is None:
                            continue
                        if rate_col >= len(row):
                            continue
                        cell = row[rate_col]
                        # Bỏ lãi suất thưởng cộng thêm dạng "+ 0.2%/năm"
                        if cell and "+" in str(cell):
                            continue
                        rate = parse_rate(cell)
                        product = "quay"
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
