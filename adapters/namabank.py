"""Adapter Nam A Bank (NAB) — HTML tĩnh qua httpx (không cần Playwright).

Trang https://www.namabank.com.vn/lai-suat render bảng lãi suất bằng JS:
laisuat.js đọc data-news-href của <option> rồi $.ajax GET từng URL con và lấy
phần `.fullcontent`. Ta gọi thẳng 2 URL con (KHCN tiết kiệm VND):

  - /lai-suat-tien-gui-vnd-2                          → Tiền gửi VND tại quầy
      cột: Kỳ hạn | Lãi cuối kỳ | Lãi hàng tháng | Lãi đầu kỳ | ...
      → product="quay", lấy cột "Lãi cuối kỳ" (index 1).
  - /bieu-lai-suat-tiet-kiem-truc-tuyen-online-nam    → Tiết kiệm Online
      cột: Kỳ hạn (tháng) | Lãi cuối kỳ
      → product="online", cột index 1.

Ô kỳ hạn quầy có dạng "3 tháng, Từ 90 - 119 ngày" — parse_term khớp "3 tháng"
= 3M (không nhầm sang ngày vì regex tháng/tuần ưu tiên số đứng trước đơn vị).
Đối chiếu web 2026-07: quầy 3M=4.60, 12M=6.20; online 3M=4.75, 12M=6.60.
"""
from __future__ import annotations

import datetime as _dt
from typing import List

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate

BASE = "https://www.namabank.com.vn"
REFERER = f"{BASE}/lai-suat"
SOURCES = [
    ("/lai-suat-tien-gui-vnd-2", "quay"),
    ("/bieu-lai-suat-tiet-kiem-truc-tuyen-online-nam", "online"),
]


class Adapter:
    code = "NAB"
    name = "Nam A Bank"

    def __init__(self, headful: bool = False):
        pass  # httpx tĩnh, headful không dùng

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        rows: List[RateRow] = []
        seen: set = set()

        with httpx.Client(http2=False, follow_redirects=True, timeout=20,
                          headers={**_HEADERS, "Referer": REFERER}) as client:
            for path, product in SOURCES:
                url = BASE + path
                resp = client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")
                scope = soup.select_one(".fullcontent") or soup
                table = scope.find("table")
                if table is None:
                    continue
                for tr in table.find_all("tr"):
                    cells = [c.get_text(" ", strip=True)
                             for c in tr.find_all(["td", "th"])]
                    if len(cells) < 2:
                        continue
                    # Ô kỳ hạn quầy: "1 tháng, Từ 30 - 59 ngày" — chỉ lấy
                    # phần trước dấu phẩy để parse_term không bắt nhầm "59 ngày".
                    term = parse_term(cells[0].split(",")[0])
                    if term is None:
                        continue
                    # Cột 1 = "Lãi cuối kỳ" cho cả hai bảng
                    rate = parse_rate(cells[1])
                    if rate is None:
                        continue
                    r = RateRow(
                        date=today, bank_code=self.code, bank_name=self.name,
                        term=term, rate=rate, product=product,
                        source_url=url, crawled_at=now,
                    )
                    if r.key() not in seen:
                        seen.add(r.key())
                        rows.append(r)
        return rows
