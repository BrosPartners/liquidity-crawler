"""Adapter MB Bank (MBB) — Playwright với stealth headers.

mbbank.com.vn có WAF chặn bot thông thường (403).
Dùng Playwright với full browser context + realistic fingerprint.
Nếu vẫn 403, fallback về trang công bố lãi suất dạng HTML.
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from adapters.base import BankAdapter
from core.normalize import parse_term, parse_rate
from core.extract import extract_rates

# URL trang niêm yết lãi suất (dạng bài đăng, không phải calculator)
URL_PRIMARY  = "https://www.mbbank.com.vn/Tools/tien-gui"
URL_FALLBACK = "https://www.mbbank.com.vn/chi-tiet/bieu-phi-khach-hang-ca-nhan/lai-suat-huy-dong-mb-2025-4-14-14-38-8/5258"


class Adapter(BankAdapter):
    code = "MBB"
    name = "MB Bank"
    url = URL_PRIMARY
    mode = "render"

    def get_html(self) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not self.headful,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                locale="vi-VN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

            for url in (URL_PRIMARY, URL_FALLBACK):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(6000)
                    html = page.content()
                    soup = BeautifulSoup(html, "lxml")
                    if soup.find_all("table") and "%" in html:
                        browser.close()
                        return html
                except Exception:
                    pass

            html = page.content()
            browser.close()
            return html

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        out = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            # Tìm cột lãi trả sau (cuối kỳ) — cột 1 thường là "Lãi trả sau"
            header = []
            for tr in rows[:3]:
                cells = [c.get_text(" ", strip=True).lower() for c in tr.find_all(["th","td"])]
                if any("lai" in c or "%" in c for c in cells):
                    header = cells
                    break

            cuoi_ky_col = 1  # default
            for j, h in enumerate(header[1:], 1):
                if any(k in h for k in ["sau", "cuoi", "end", "mat dinh"]):
                    cuoi_ky_col = j
                    break

            for tr in rows:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
                if not cells:
                    continue
                term = parse_term(cells[0])
                if term is None:
                    continue
                rate = parse_rate(cells[cuoi_ky_col]) if cuoi_ky_col < len(cells) else None
                if rate:
                    out.append((term, "quay", rate))

        return out if out else extract_rates(html)
