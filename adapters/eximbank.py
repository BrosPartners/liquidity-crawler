"""Adapter Eximbank (EIB) — PDF biểu lãi suất (không cần Playwright).

Trang https://eximbank.com.vn/lai-suat-tiet-kiem là SPA Next.js: bảng lãi suất
KHÔNG render ra <table> trong HTML (chỉ có widget máy tính lãi suất). Nguồn dữ
liệu chính thức, ổn định là file PDF được trang này liên kết:

    https://media.eximbank.com.vn/exim/files/KHCN-LaisuathuydongVND.pdf
    ("Lãi suất huy động tiền gửi VNĐ đối với khách hàng cá nhân")

Ta tải PDF bằng httpx (http2=False) và parse bảng bằng pdfplumber:

  • QUẦY  — Mục "A.1 LÃI SUẤT TIẾT KIỆM, TIỀN GỬI CÁ NHÂN": mỗi hàng là 1 kỳ hạn,
    nhiều cột theo cách lãnh lãi; ta lấy CỘT CUỐI (Lãnh lãi cuối kỳ) = số cuối
    cùng parse được trên hàng → product="quay".
  • ONLINE — Mục "A.8 LÃI SUẤT TIỀN GỬI ONLINE": bảng ngang, header 1T/2T/...,
    hàng "Lãi cuối kỳ" → product="online".

Chỉ lấy VND, tiết kiệm/tiền gửi cá nhân, lãi cuối kỳ. Reject rate <=0 hoặc >15.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import List, Tuple

import httpx

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate

PDF_URL = "https://media.eximbank.com.vn/exim/files/KHCN-LaisuathuydongVND.pdf"
PAGE_URL = "https://eximbank.com.vn/lai-suat-tiet-kiem"

# Kỳ hạn chuẩn (số tháng) theo thứ tự cột trong bảng Online A.8
_ONLINE_TERMS = ["1M", "2M", "3M", "6M", "9M", "12M", "15M", "18M", "24M", "36M"]


def _num(s) -> float | None:
    """Ô PDF -> float; '3,4' -> 3.4; bỏ chuỗi không phải mức lãi suất."""
    if s is None:
        return None
    s = str(s).strip()
    # Chỉ nhận ô dạng số thuần (có thể có dấu phẩy thập phân), tránh '900\ntriệu'
    if not re.fullmatch(r"\d{1,2}(?:[.,]\d{1,2})?", s):
        return None
    return parse_rate(s)


class Adapter:
    code = "EIB"
    name = "Eximbank"

    def __init__(self, headful: bool = False):
        pass  # dùng httpx + pdfplumber, không cần trình duyệt

    def _get_pdf(self) -> bytes:
        with httpx.Client(http2=False, follow_redirects=True, timeout=30,
                          verify=False) as client:
            r = client.get(PDF_URL, headers=_HEADERS)
            r.raise_for_status()
            return r.content

    def _parse(self, pdf_bytes: bytes) -> List[Tuple[str, str, float]]:
        import pdfplumber

        out: List[Tuple[str, str, float]] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tables = [t for pg in pdf.pages for t in pg.extract_tables()]

        # ── QUẦY: bảng A.1 (bảng có cột kỳ hạn dọc + nhiều mức "Lãnh lãi") ──
        # Nhận diện: bảng có >=8 hàng mà cột thứ 2 parse được thành kỳ hạn.
        counter_table = None
        best = 0
        for tb in tables:
            hits = sum(1 for row in tb
                       if len(row) > 2 and parse_term(row[1] or "") is not None)
            if hits > best:
                best, counter_table = hits, tb
        if counter_table:
            for row in counter_table:
                if len(row) < 3:
                    continue
                term = parse_term(row[1] or "")
                if term is None:
                    continue
                # Lãnh lãi cuối kỳ = số HỢP LỆ cuối cùng trên hàng
                rate = None
                for cell in row[2:]:
                    v = _num(cell)
                    if v is not None:
                        rate = v
                if rate is not None and 0 < rate <= 15:
                    out.append((term, "quay", rate))

        # ── ONLINE: bảng A.8 — hàng bắt đầu bằng "Lãi cuối kỳ", theo sau là
        # đúng 10 mức lãi suất khớp cột 1T..36T. Chọn bảng có header "... T".
        online_row = None
        for tb in tables:
            flat = [(c or "") for row in tb for c in row]
            # header online dùng dạng "1 T","12 T" — dấu hiệu bảng A.8
            if not any(re.fullmatch(r"\d{1,2}\s*T", str(c).strip()) for c in flat):
                continue
            for row in tb:
                label = (row[0] or "").strip().lower()
                if label.startswith("lãi cuối kỳ") or label.startswith("lai cuoi ky"):
                    vals = [_num(c) for c in row]
                    vals = [v for v in vals if v is not None]
                    if len(vals) >= 8:
                        online_row = vals
                        break
            if online_row:
                break
        if online_row:
            for term, rate in zip(_ONLINE_TERMS, online_row):
                if rate is not None and 0 < rate <= 15:
                    out.append((term, "online", rate))

        return out

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        pdf_bytes = self._get_pdf()
        rows: List[RateRow] = []
        seen: set = set()
        for term, product, rate in self._parse(pdf_bytes):
            r = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product=product,
                source_url=PDF_URL, crawled_at=now,
            )
            if r.key() not in seen:
                seen.add(r.key())
                rows.append(r)
        return rows
