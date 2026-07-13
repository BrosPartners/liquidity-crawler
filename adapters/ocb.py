"""Adapter OCB (Ngân hàng Phương Đông) — HTML tĩnh (SSR / Angular Universal).

Trang "Lãi suất tiết kiệm": https://www.ocb.com.vn/vi/cong-cu/lai-suat
Trang là ứng dụng Angular nhưng được render sẵn phía server (SSR), nên httpx
tải được HTML đã có sẵn bảng lãi suất — KHÔNG cần Playwright.

Bảng lãi suất tiết kiệm cá nhân (bảng đầu tiên) có 4 cột:
    Kỳ hạn | Tiền gửi có kỳ hạn | Tiết kiệm thông thường | Tiết kiệm Online
Ta lấy:
    - Cột "Tiết kiệm thông thường" → product="quay"
    - Cột "Tiết kiệm Online"       → product="online"
Cột "Tiền gửi có kỳ hạn" trùng giá trị với "Tiết kiệm thông thường" → bỏ qua.

Các bảng còn lại trên trang là lãi suất cho vay / lãi suất cơ sở → bỏ qua
(nhận diện qua header, chỉ nhận bảng có chứa "tiet kiem").

Đối chiếu web 2026-07: 1M=4.75, 3M=4.75, 6M=6.40/6.50, 12M=6.70/6.80,
36M=7.00/7.10 (thông thường/online).
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate, norm_text

URL = "https://www.ocb.com.vn/vi/cong-cu/lai-suat"


def _cells(tr) -> List[str]:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


class Adapter:
    code = "OCB"
    name = "OCB"

    def __init__(self, headful: bool = False):
        pass  # headful không dùng, giữ tương thích interface

    def _get_html(self) -> str:
        last = None
        with httpx.Client(http2=False, follow_redirects=True, timeout=90) as client:
            for _ in range(3):
                try:
                    r = client.get(URL, headers=_HEADERS)
                    r.raise_for_status()
                    return r.text
                except Exception as e:  # trang OCB thỉnh thoảng timeout — thử lại
                    last = e
        raise last

    def _parse(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        out: List[Tuple[str, str, float]] = []

        for tb in soup.find_all("table"):
            rows = tb.find_all("tr")
            if not rows:
                continue
            header = _cells(rows[0])
            hnorm = [norm_text(h) for h in header]
            # Chỉ nhận bảng lãi suất TIẾT KIỆM (bỏ bảng cho vay / lãi suất cơ sở)
            if not any("tiet kiem" in h for h in hnorm):
                continue

            # Xác định cột quầy / online theo header
            col_quay = col_online = None
            for idx, h in enumerate(hnorm):
                if "tiet kiem" not in h:
                    continue
                if "online" in h:
                    col_online = idx
                elif col_quay is None:  # "tiet kiem thong thuong"
                    col_quay = idx
            if col_quay is None and col_online is None:
                continue

            targets = []
            if col_quay is not None:
                targets.append((col_quay, "quay"))
            if col_online is not None:
                targets.append((col_online, "online"))

            for tr in rows[1:]:
                cells = _cells(tr)
                if not cells:
                    continue
                term = parse_term(cells[0])
                if term is None:
                    continue
                for col, product in targets:
                    if col >= len(cells):
                        continue
                    rate = parse_rate(cells[col])  # loại 0 và ngoài (0,15]
                    if rate:
                        out.append((term, product, rate))
            break  # chỉ có 1 bảng tiết kiệm

        return out

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        html = self._get_html()
        rows: List[RateRow] = []
        seen: set = set()
        for term, product, rate in self._parse(html):
            r = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product=product,
                source_url=URL, crawled_at=now,
            )
            if r.key() not in seen:
                seen.add(r.key())
                rows.append(r)
        return rows
