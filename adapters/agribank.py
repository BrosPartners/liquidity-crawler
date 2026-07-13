"""Adapter Agribank (AGR) — HTML tĩnh, dùng URL tiếng Anh.

URL tiếng Việt redirect 404; URL tiếng Anh có bảng tĩnh đầy đủ.
Bảng 0: "Individual Customers" — KHCN tại quầy: Kỳ hạn | VND | USD | EUR | ...
Bảng 1: "Enterprise Customers" — KHDN, KHÔNG lấy (trước đây gán nhầm là 'online').
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup

from adapters.base import BankAdapter
from core.normalize import parse_term, parse_rate


def _extract_table(table, product: str) -> List[Tuple[str, str, float]]:
    out = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        term = parse_term(cells[0])
        if term is None:
            continue
        rate = parse_rate(cells[1]) if len(cells) > 1 else None
        if rate:
            out.append((term, product, rate))
    return out


class Adapter(BankAdapter):
    code = "AGR"
    name = "Agribank"
    url = "https://www.agribank.com.vn/en/lai-suat"
    mode = "html"

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        out = []
        if len(tables) > 0:
            out.extend(_extract_table(tables[0], "quay"))
        # tables[1] là "Enterprise Customers" (KHDN) — bỏ qua, không phải online KHCN.
        return out
