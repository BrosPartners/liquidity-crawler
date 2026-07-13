"""Adapter HDBank (HDB) — dynamic PDF parsing.

HDBank publishes deposit rates as a PDF at a CDN URL that changes periodically.
Strategy:
  1. Playwright to scrape the most recent "BIỂU LÃI SUẤT TIỀN GỬI KHÁCH HÀNG CÁ NHÂN" link.
  2. Download PDF with httpx.
  3. pdfplumber to extract tables and parse VND Cuối kỳ rates.
"""
from __future__ import annotations

import io
import re
from typing import List

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from adapters.base import _HEADERS, render_html
from core.normalize import parse_term, parse_rate
from core.schema import RateRow
import datetime as _dt

RATE_PAGE_URL = "https://hdbank.com.vn/vi/personal/cong-cu/interest-rate"


def _get_pdf_url() -> str:
    """Render page and find the most recent deposit rate PDF link."""
    html = render_html(RATE_PAGE_URL, wait_until="domcontentloaded", extra_wait=5000)
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a"):
        txt = a.get_text(strip=True).upper()
        href = a.get("href", "")
        if "TIỀN GỬI" in txt and "KHÁCH HÀNG CÁ NHÂN" in txt and href.endswith(".pdf"):
            return href
    raise RuntimeError("HDB: cannot find deposit rate PDF link")


class Adapter:
    code = "HDB"
    name = "HDBank"
    url = RATE_PAGE_URL

    def __init__(self, headful: bool = False):
        self._headful = headful

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        pdf_url = _get_pdf_url()

        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30, http2=False) as client:
            r = client.get(pdf_url)
            r.raise_for_status()
            pdf_bytes = r.content

        rows: List[RateRow] = []
        seen: set = set()
        for term, rate in _parse_pdf(pdf_bytes):
            row_obj = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product="quay",
                source_url=pdf_url, crawled_at=now,
            )
            key = row_obj.key()
            if key not in seen:
                seen.add(key)
                rows.append(row_obj)
        return rows


def _first_rate(cells) -> float | None:
    for c in cells:
        v = parse_rate(c)
        if v is not None:
            return v
    return None


def _parse_pdf(pdf_bytes: bytes) -> List[tuple]:
    """Chỉ parse BẢNG CHÍNH 'Tiền gửi tiết kiệm VNĐ' — bảng đầu tiên có
    header 'Cuối kỳ' và >= 8 dòng kỳ hạn. PDF còn nhiều bảng sản phẩm khác
    (ký quỹ 3.5% flat mọi kỳ hạn, tiền gửi có kỳ hạn, online, iSmart...);
    quét tất cả từng gây leak 48M/60M=3.5 vào data.

    Kỳ hạn 12/13 tháng có 2 dòng: 'LS12 loại 1' (điều kiện đặc biệt, ~7%+)
    và 'LS12 loại 2' (niêm yết chuẩn) ở dòng kế (row[0] rỗng). Lấy 'loại 2'.
    """
    def _norm(c) -> str:
        return str(c or "").replace("\n", " ").strip().lower()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                # Tìm header 'Cuối kỳ' trong 4 dòng đầu
                has_cuoi_ky = any(
                    "cuối kỳ" in _norm(cell)
                    for hrow in table[:4] for cell in (hrow or [])
                )
                if not has_cuoi_ky:
                    continue
                n_terms = sum(1 for r in table if r and r[0] and parse_term(str(r[0])))
                if n_terms < 8:
                    continue

                out: List[tuple] = []
                pending_term = None  # kỳ hạn (*) chờ dòng 'loại 2'
                for row in table:
                    cells = [str(c or "") for c in row]
                    first = cells[0].strip()
                    joined = _norm(" ".join(cells[:3]))
                    if first:
                        term = parse_term(first)
                        if term is None:
                            continue
                        if "loại 1" in joined:
                            pending_term = term   # mức đặc biệt — bỏ, chờ loại 2
                            continue
                        rate = _first_rate(cells[1:])
                        if rate is not None:
                            out.append((term, rate))
                        pending_term = None
                    elif pending_term and "loại 2" in joined:
                        rate = _first_rate(cells[1:])
                        if rate is not None:
                            out.append((pending_term, rate))
                        pending_term = None
                return out  # chỉ lấy bảng chính đầu tiên
    return []
