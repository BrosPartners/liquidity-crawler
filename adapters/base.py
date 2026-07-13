"""Interface chung cho mọi bank adapter.

mode = 'html'   → fetch bằng httpx (nhanh, không cần Playwright)
mode = 'render' → Playwright headless (cho trang JS-render)
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from core.schema import RateRow
from core.extract import extract_rates

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html_static(url: str, timeout: int = 20) -> str:
    """Tải HTML tĩnh bằng httpx — nhanh, không cần trình duyệt."""
    import httpx
    r = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    return r.text


def render_html(url: str, headful: bool = False, wait_selector: Optional[str] = None,
                timeout_ms: int = 30000, wait_until: str = "networkidle",
                extra_wait: int = 0) -> str:
    """Mở URL bằng Chromium headless, đợi JS render, trả HTML cuối cùng."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful,
                                     args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = browser.new_context(locale="vi-VN",
                                   user_agent=_HEADERS["User-Agent"],
                                   viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                pass
        if extra_wait:
            page.wait_for_timeout(extra_wait)
        html = page.content()
        browser.close()
        return html


class BankAdapter:
    """Kế thừa và đặt: code, name, url, mode.
    Override parse_html() nếu cần xử lý layout đặc biệt.
    """
    code: str = ""
    name: str = ""
    url: str = ""
    mode: str = "render"           # 'html' | 'render'
    wait_selector: Optional[str] = None

    def __init__(self, headful: bool = False):
        self.headful = headful

    def get_html(self) -> str:
        if self.mode == "html":
            return fetch_html_static(self.url)
        return render_html(self.url, headful=self.headful, wait_selector=self.wait_selector)

    def parse_html(self, html: str) -> List[tuple]:
        return extract_rates(html)

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        html = self.get_html()
        rows: List[RateRow] = []
        seen = set()
        for term, product, rate in self.parse_html(html):
            r = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product=product,
                source_url=self.url, crawled_at=now,
            )
            if r.key() not in seen:
                seen.add(r.key())
                rows.append(r)
        return rows
