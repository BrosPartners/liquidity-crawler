"""Bộ trích bảng lãi suất TỔNG QUÁT từ HTML.

Ý tưởng: trang bank thường có >1 bảng (tỷ giá, phí, lãi suất...). Ta chấm điểm
từng bảng theo mức độ "giống bảng lãi suất" (có cột kỳ hạn + ô dạng %), chọn
bảng điểm cao nhất, rồi map: cột đầu = kỳ hạn, các cột còn lại = lãi suất theo
sản phẩm (tại quầy / online) suy ra từ header.

Heuristic này chạy được cho phần lớn bank. Bank nào layout lạ -> override trong
adapter riêng (xem adapters/base.py: parse_html()).
"""
from __future__ import annotations

from typing import List, Tuple
from bs4 import BeautifulSoup

from .normalize import parse_term, parse_rate, detect_product, norm_text


def _table_cells(table) -> List[List[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    return rows


def _score_table(rows: List[List[str]]) -> int:
    """Đếm số ô parse được thành kỳ hạn + số ô parse được thành lãi suất."""
    terms = rates = 0
    for r in rows:
        if r and parse_term(r[0]) is not None:
            terms += 1
        for c in r[1:]:
            if parse_rate(c) is not None:
                rates += 1
    # Cần tối thiểu vài kỳ hạn và vài mức lãi suất mới coi là bảng lãi suất
    return terms * 10 + rates if (terms >= 3 and rates >= 3) else 0


def _header_products(rows: List[List[str]], term_rows: set) -> List[str]:
    """Tìm dòng header (không phải dòng kỳ hạn) -> nhãn sản phẩm cho từng cột."""
    for i, r in enumerate(rows):
        if i in term_rows:
            continue
        if any(k in norm_text(" ".join(r)) for k in ("ky han", "lai suat", "%")):
            return r
    return []


def extract_rates(html: str) -> List[Tuple[str, str, float]]:
    """Trả về list (term, product, rate) thô. Adapter sẽ bọc thành RateRow."""
    soup = BeautifulSoup(html, "lxml")
    best, best_score = None, 0
    for table in soup.find_all("table"):
        rows = _table_cells(table)
        sc = _score_table(rows)
        if sc > best_score:
            best, best_score = rows, sc
    if not best:
        return []

    term_rows = {i for i, r in enumerate(best) if r and parse_term(r[0])}
    header = _header_products(best, term_rows)

    out: List[Tuple[str, str, float]] = []
    for i in term_rows:
        r = best[i]
        term = parse_term(r[0])
        for col, cell in enumerate(r[1:], start=1):
            rate = parse_rate(cell)
            if rate is None:
                continue
            label = header[col] if col < len(header) else ""
            out.append((term, detect_product(label), rate))
    return out
