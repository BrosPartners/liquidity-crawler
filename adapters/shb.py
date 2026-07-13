"""Adapter SHB (Ngân hàng TMCP Sài Gòn - Hà Nội) — HTML tĩnh qua httpx.

Nguồn chính thức shb.com.vn bị WAF chặn (403 với httpx/WebFetch), trang lãi
suất lại JS-render nặng và URL không ổn định. Do đó ta dùng nguồn tổng hợp
ổn định 24hmoney.vn (HTTP 200, HTML tĩnh, bảng sạch), được cập nhật theo biểu
lãi suất niêm yết của SHB.

Trang có nhiều bảng; 2 bảng lãi suất tiền gửi cá nhân VND là:
  - Bảng có heading "... gửi tại Quầy"     -> product = "quay"
  - Bảng có heading "... gửi Trực tuyến"    -> product = "online"
Mỗi bảng: cột 0 = kỳ hạn, cột 1 = lãi suất (%/năm), ví dụ "4.5%".

Đối chiếu web 2026-07 (tại quầy): 1M=4.40, 3M=4.50, 6M=5.80, 9M=5.80, 12M=6.20.
Đối chiếu web 2026-07 (online):  1M=4.75, 3M=4.75, 6M=7.70, 9M=7.70, 12M=7.80.
"""
from __future__ import annotations

import datetime as _dt
from typing import List

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate, norm_text

URL = "https://24hmoney.vn/lai-suat-gui-ngan-hang/shb"


def _cells(tr) -> List[str]:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


class Adapter:
    code = "SHB"
    name = "SHB"

    def __init__(self, headful: bool = False):
        pass  # giữ tương thích interface

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(http2=False, follow_redirects=True, timeout=20) as client:
            r = client.get(URL, headers=_HEADERS)
            r.raise_for_status()
            html = r.text

        soup = BeautifulSoup(html, "lxml")
        rows: List[RateRow] = []
        seen: set = set()

        for table in soup.find_all("table"):
            trs = table.find_all("tr")
            if not trs:
                continue
            # Xác định product từ heading đứng ngay trước bảng.
            prev = table.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "div"])
            heading = norm_text(prev.get_text(" ", strip=True)) if prev else ""
            if "quay" in heading:
                product = "quay"
            elif "truc tuyen" in heading or "online" in heading:
                product = "online"
            else:
                # Không phải bảng lãi suất tiền gửi cá nhân đã gắn nhãn -> bỏ.
                continue

            for tr in trs:
                cells = _cells(tr)
                if len(cells) < 2:
                    continue
                term = parse_term(cells[0])
                if term is None:
                    continue
                rate = parse_rate(cells[1])
                if rate is None or not (0 < rate <= 15):
                    continue
                row = RateRow(
                    date=today, bank_code=self.code, bank_name=self.name,
                    term=term, rate=rate, product=product,
                    source_url=URL, crawled_at=now,
                )
                if row.key() not in seen:
                    seen.add(row.key())
                    rows.append(row)

        return rows
