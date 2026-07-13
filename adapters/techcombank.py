"""Adapter Techcombank (TCB) — PDF động qua GraphQL API (không cần Playwright).

Trang cũ /cong-cu-tien-ich/bieu-mau-lai-suat đã 404. Trang mới:
  https://techcombank.com/cong-cu-tien-ich/bieu-phi-lai-suat
là AEM SPA, gọi GraphQL persisted query trả danh sách document KHCN:
  /graphql/execute.json/techcombank/viewDocumentList;cfPath=/content/dam/
  techcombank/master-data/vi/list-view-document/cong-cu-tien-ich/bieu-phi-lai-suat/khcn/
Trong đó item có categoryTitle "Lãi suất tiền gửi tiết kiệm Thường" trỏ tới PDF.

PDF: pdfplumber extract_tables() bị vỡ layout → dùng extract_text(layout=True).
Bảng VND trang 1, cột: KỲ HẠN | PRIVATE | PRIORITY | INSPIRE | KH THƯỜNG |
HÀNG THÁNG | HÀNG QUÝ | TRẢ LÃI TRƯỚC. Lấy cột 4 (KH THƯỜNG = khách hàng
thường, trả lãi cuối kỳ) — đúng chuẩn so sánh liên NH. Fallback: nếu GraphQL
đổi, render trang bằng Playwright và tìm href *tiet-kiem-thuong*.pdf.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import List, Optional

import httpx
import pdfplumber

from adapters.base import _HEADERS, render_html
from core.normalize import norm_text, parse_term
from core.schema import RateRow

PAGE_URL = "https://techcombank.com/cong-cu-tien-ich/bieu-phi-lai-suat"
GRAPHQL_URL = (
    "https://techcombank.com/graphql/execute.json/techcombank/"
    "viewDocumentList%3BcfPath%3D/content/dam/techcombank/master-data/vi/"
    "list-view-document/cong-cu-tien-ich/bieu-phi-lai-suat/khcn/"
)
BASE = "https://techcombank.com"


def _pdf_url_from_graphql(client: httpx.Client) -> Optional[str]:
    r = client.get(GRAPHQL_URL, headers={**_HEADERS, "Accept": "application/json"})
    r.raise_for_status()
    items = (r.json().get("data", {})
             .get("listViewDocumentFragmentList", {}).get("items", []))
    for it in items:
        title = norm_text(((it.get("categoryTitle") or {}).get("plaintext")) or "")
        if "tiet kiem thuong" in title:
            doc = it.get("documentPath") or {}
            url = doc.get("_publishUrl") or (BASE + doc.get("_path", ""))
            if url and url.endswith(".pdf"):
                return url
    return None


def _pdf_url_fallback() -> Optional[str]:
    """Playwright render trang, tìm link PDF 'tiet-kiem-thuong'."""
    html = render_html(PAGE_URL, wait_until="domcontentloaded", extra_wait=6000)
    m = re.search(r'href="([^"]*tiet-kiem-thuong[^"]*\.pdf)"', html)
    if m:
        href = m.group(1)
        return href if href.startswith("http") else BASE + href
    return None


# Dòng dữ liệu: "12M   6.40  6.30  6.15  6.15  5.90  6.00  5.70"
_ROW_RE = re.compile(r"^\s*(KKH|\d{1,2}M)\s+((?:\d+\.\d+\s*)+)$", re.I)


def _parse_pdf(pdf_bytes: bytes) -> List[tuple]:
    """Parse bảng 'TIẾT KIỆM CÓ KỲ HẠN VND' bằng text layout.

    Lấy cột thứ 4 (KH THƯỜNG, trả lãi cuối kỳ). Riêng KKH: nhãn nằm dòng
    riêng ('KKH' rồi dòng số '0.05 x7' rồi 'Demand') — bắt dòng toàn số
    ngay sau nhãn KKH.
    """
    out: List[tuple] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            up = re.sub(r"\s+", " ", text.upper())
            if "KỲ HẠN VND" not in up and "VND SAVINGS" not in up:
                continue
            pending_kkh = False
            for line in text.splitlines():
                s = line.strip()
                if s.upper() == "KKH":
                    pending_kkh = True
                    continue
                if pending_kkh:
                    nums = re.findall(r"\d+\.\d+", s)
                    if nums:
                        out.append(("KKH", float(nums[min(3, len(nums) - 1)])))
                        pending_kkh = False
                    continue
                m = _ROW_RE.match(s)
                if not m:
                    continue
                term = parse_term(m.group(1))
                if term is None:
                    continue
                nums = [float(x) for x in re.findall(r"\d+\.\d+", m.group(2))]
                if len(nums) >= 4:
                    rate = nums[3]          # cột KH THƯỜNG (cuối kỳ)
                    if 0 < rate <= 15:
                        out.append((term, rate))
            break  # chỉ lấy trang bảng VND đầu tiên
    return out


class Adapter:
    code = "TCB"
    name = "Techcombank"
    url = PAGE_URL

    def __init__(self, headful: bool = False):
        self._headful = headful

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(headers=_HEADERS, follow_redirects=True,
                          timeout=30, http2=False) as client:
            pdf_url = None
            try:
                pdf_url = _pdf_url_from_graphql(client)
            except Exception:
                pass
            if not pdf_url:
                pdf_url = _pdf_url_fallback()
            if not pdf_url:
                raise RuntimeError("TCB: không tìm được link PDF biểu lãi suất")
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
            if row_obj.key() not in seen:
                seen.add(row_obj.key())
                rows.append(row_obj)
        return rows
