"""Adapter BIDV — Angular SPA, Playwright với domcontentloaded + extra wait.

Cấu trúc bảng sau khi render:
  Cột: Kỳ hạn | USD | VND | JPY | EUR
  Hàng trống (%) = chưa niêm yết; ta chỉ lấy cột VND.
  Trang mặc định là khu vực Hà Nội — đủ đại diện.
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from adapters.base import BankAdapter, _HEADERS
from core.normalize import parse_term, parse_rate


class Adapter(BankAdapter):
    code = "BID"
    name = "BIDV"
    url = "https://bidv.com.vn/vn/tra-cuu-lai-suat/"
    mode = "render"

    def get_html(self) -> str:
        # BIDV Angular: networkidle timeout; dùng domcontentloaded + wait 10s
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not self.headful)
            page = browser.new_page(locale="vi-VN", extra_http_headers=_HEADERS)
            page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)  # đợi Angular điền số
            html = page.content()
            browser.close()
            return html

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        if not tables:
            return []

        # Tìm bảng có cột VND
        rate_table = None
        vnd_col = None
        for t in tables:
            rows = t.find_all("tr")
            for tr in rows[:3]:
                cells = [c.get_text(" ", strip=True).upper() for c in tr.find_all(["th", "td"])]
                if "VND" in cells:
                    vnd_col = cells.index("VND")
                    rate_table = t
                    break
            if rate_table:
                break

        if rate_table is None or vnd_col is None:
            return []

        out: List[Tuple[str, str, float]] = []
        for tr in rate_table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            term = parse_term(cells[0])
            if term is None:
                continue
            rate = parse_rate(cells[vnd_col]) if vnd_col < len(cells) else None
            if rate:
                out.append((term, "quay", rate))
        return out
