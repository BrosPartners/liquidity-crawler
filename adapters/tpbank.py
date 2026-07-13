"""Adapter TPBank (TPB) — HTML fragment tĩnh (httpx, không cần Playwright).

Trang https://tpb.vn/cong-cu-tinh-toan/lai-suat là SPA: bảng lãi suất được nạp
qua AJAX ($('#tab-1').load(...)) từ một fragment HTML của CMS WebSphere Portal:

    /wps/wcm/connect/tpbank_data/sa-website/.../danh-cho-khach-hang-ca-nhan
        ?source=library&srv=cmpnt&cmpntid=<uuid>

Fragment (bảng đầu tiên) là biểu lãi suất tiền gửi KHCN, cột:
    KÌ HẠN | TIẾT KIỆM TRƯỜNG AN LỘC | TIẾT KIỆM ĐIỆN TỬ | TIẾT KIỆM TÍNH LÃI CUỐI KỲ

Ta chỉ lấy:
  - "TIẾT KIỆM ĐIỆN TỬ"        -> product="online"
  - "TIẾT KIỆM TÍNH LÃI CUỐI KỲ" -> product="quay"  (gửi tại quầy, lãi cuối kỳ)
Bỏ cột "TRƯỜNG AN LỘC" (sản phẩm chuyên biệt) và các bảng khác (VTM, LS cơ sở).

Đối chiếu web 2026-07: 3T online=4.75/quay=4.20 ; 12T online=6.20 ; 6T online=6.00/quay=5.50.
"""
from __future__ import annotations

import datetime as _dt
from typing import List

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate, norm_text

PAGE_URL = "https://tpb.vn/cong-cu-tinh-toan/lai-suat"
_PATH = ("/tpbank_data/sa-website/ty-gia-lai-suat-cong-cu-tinh-toan/lai-xuat/"
         "danh-cho-khach-hang-ca-nhan")
API_URL = ("https://tpb.vn/wps/wcm/connect" + _PATH +
           "?source=library&srv=cmpnt&cmpntid=c3723702-cc5e-43bc-8123-867223571d0a")

# Nhận diện cột theo tiêu đề (đã bỏ dấu, lowercase qua norm_text).
_ONLINE_KEY = "ien tu"        # TIẾT KIỆM ĐIỆN TỬ (đ không tách dấu qua NFD)
_COUNTER_KEY = "cuoi ky"      # TIẾT KIỆM TÍNH LÃI CUỐI KỲ


def _cells(tr) -> List[str]:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


class Adapter:
    code = "TPB"
    name = "TPBank"

    def __init__(self, headful: bool = False):
        pass  # không dùng Playwright

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(http2=False, follow_redirects=True, timeout=20) as client:
            r = client.get(API_URL, headers={**_HEADERS, "Referer": PAGE_URL})
            r.raise_for_status()
            html = r.text

        soup = BeautifulSoup(html, "lxml")
        rows: List[RateRow] = []
        seen: set = set()

        # Bảng đầu tiên = biểu lãi suất tiết kiệm KHCN.
        table = soup.find("table")
        if table is None:
            return rows
        trs = table.find_all("tr")
        if not trs:
            return rows

        # Xác định chỉ số cột online / quầy từ hàng tiêu đề.
        header = _cells(trs[0])
        col_map = {}  # col_index -> product
        for idx, h in enumerate(header):
            ht = norm_text(h)
            if _ONLINE_KEY in ht:
                col_map[idx] = "online"
            elif _COUNTER_KEY in ht:
                col_map[idx] = "quay"
        if not col_map:
            return rows

        for tr in trs[1:]:
            cells = _cells(tr)
            if not cells:
                continue
            term = parse_term(cells[0])
            if term is None:
                continue
            for idx, product in col_map.items():
                if idx >= len(cells):
                    continue
                rate = parse_rate(cells[idx])
                if rate is None or not (0 < rate <= 15):
                    continue
                r_row = RateRow(
                    date=today, bank_code=self.code, bank_name=self.name,
                    term=term, rate=rate, product=product,
                    source_url=PAGE_URL, crawled_at=now,
                )
                if r_row.key() not in seen:
                    seen.add(r_row.key())
                    rows.append(r_row)
        return rows
