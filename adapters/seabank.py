"""Adapter SeABank (SSB) — trang "Biểu lãi suất" (Next.js, JS-render).

Nguồn: https://www.seabank.com.vn/cong-cu-tien-ich/bieu-lai-suat?type=lai-suat

Trang là ứng dụng Next.js: bảng lãi suất được nạp qua Server Action (POST) sau
khi client hydrate, KHÔNG có trong HTML tĩnh và cũng không nằm trong payload RSC
(đã kiểm chứng: httpx GET/RSC không chứa số). Không tìm thấy REST/JSON API công
khai. => Bắt buộc dùng Playwright (render_html) rồi parse DOM đã render.

Mặc định trang chọn sẵn đúng đối tượng cần lấy:
  - Đối tượng khách hàng: "Khách hàng cá nhân"
  - Tên sản phẩm:        "Tiết kiệm Lĩnh lãi cuối kỳ"
  - Số tiền/Loại tiền:   VND
Đây chính là lãi suất tiết kiệm cá nhân VND (lĩnh lãi cuối kỳ). SeABank không
tách quầy/online trong biểu này => product = "quay".

Bảng render KHÔNG phải <table> mà là danh sách các dòng dạng
  "1 Tháng"  "3.95 %"  |  "3 Tháng" "4.45 %"  |  "12 Tháng" "5.10 %" ...
(đã đối chiếu web 2026-07: 3M=4.45, 12M=5.10). Ta parse bằng regex trên text
đã render, ghép "<số> Tháng/Ngày/Tuần" với "<số> %" liền kề.

Đã kiểm chứng số khớp web ngày 2026-07.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import List

from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate

URL = "https://www.seabank.com.vn/cong-cu-tien-ich/bieu-lai-suat?type=lai-suat"

# Ghép "<n> Tháng|Ngày|Tuần" ... "<x> %" (cách nhau bởi vài ký tự/tab/space).
_ROW_RE = re.compile(
    r"(\d{1,2})\s*(Tháng|Thang|Ngày|Ngay|Tuần|Tuan)\s*[^%\d]{0,20}?(\d{1,2}(?:[.,]\d{1,2})?)\s*%",
    re.IGNORECASE,
)


class Adapter:
    code = "SSB"
    name = "SeABank"

    def __init__(self, headful: bool = False):
        self.headful = headful

    def _extract(self, text: str) -> List[tuple]:
        out: List[tuple] = []
        for num, unit, rate_str in _ROW_RE.findall(text):
            u = unit.lower()
            if u.startswith(("tháng", "thang")):
                raw_term = f"{num} tháng"
            elif u.startswith(("tuần", "tuan")):
                raw_term = f"{num} tuần"
            else:
                raw_term = f"{num} ngày"
            term = parse_term(raw_term)
            rate = parse_rate(rate_str)
            if term and rate is not None:
                out.append((term, rate))
        return out

    def _render(self) -> str:
        """Mở trang, đợi bảng lãi suất render xong (server action POST).

        Không dùng render_html() của base vì nó chờ 'networkidle' — trang có
        analytics ping liên tục nên không bao giờ idle. Ở đây dùng
        'domcontentloaded' rồi poll DOM tới khi thấy dòng '<n> Tháng ... %'.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not self.headful,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                locale="vi-VN", user_agent=_HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            # Poll tới khi text bảng lãi suất xuất hiện (regex kỳ hạn + %).
            html = ""
            for _ in range(20):  # tối đa ~20s
                html = page.content()
                if _ROW_RE.search(BeautifulSoup(html, "lxml").get_text(" ", strip=True)):
                    break
                page.wait_for_timeout(1000)
            browser.close()
            return html

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        html = self._render()

        # Chỉ lấy text trong <main> để tránh nhiễu từ footer/menu.
        soup = BeautifulSoup(html, "lxml")
        main = soup.find("main")
        text = main.get_text(" ", strip=True) if main else soup.get_text(" ", strip=True)

        rows: List[RateRow] = []
        seen: set = set()
        for term, rate in self._extract(text):
            if not (0 < rate <= 15):
                continue
            r = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product="quay",
                source_url=URL, crawled_at=now,
            )
            if r.key() not in seen:
                seen.add(r.key())
                rows.append(r)
        return rows
