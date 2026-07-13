"""Adapter VietinBank (CTG) — HTML tĩnh, httpx.

Bảng 0 có cấu trúc: Kỳ hạn | VND | USD | EUR
Tên kỳ hạn dạng dải: "Từ 1 tháng đến dưới 2 tháng" -> lấy số đầu tiên -> 1M.
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup

from adapters.base import BankAdapter
from core.normalize import parse_term, parse_rate


class Adapter(BankAdapter):
    code = "CTG"
    name = "VietinBank"
    url = "https://www.vietinbank.vn/ca-nhan/cong-cu-tien-ich/lai-suat-khcn"
    mode = "html"

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        if not tables:
            return []

        # Bảng 0: lãi suất tiền gửi VND/USD/EUR
        # Header: Kỳ hạn | VND | USD | EUR  -> VND ở col 1
        out = []
        for tr in tables[0].find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not cells or "VND" in cells[0].upper():
                continue
            raw = cells[0].replace("\xa0", " ")
            import re
            from core.normalize import norm_text as _nt
            raw_n = _nt(raw)
            # Bỏ qua dòng "Dưới X tháng" (< X month) — không phải kỳ hạn chuẩn
            if re.match(r"(duoi|under|less)", raw_n, re.I):
                continue
            # Đơn vị: tìm bất kỳ đâu trong chuỗi (có thể chỉ đứng sau số cuối:
            # "Từ 11 đến dưới 12 tháng")
            u = "M" if re.search(r"thang|month", raw_n) else \
                "W" if re.search(r"tuan|week", raw_n) else None
            nums = re.findall(r"\d+", raw_n)
            if u and nums:
                if re.match(r"tren", raw_n) and "duoi" in raw_n:
                    # "Trên X đến dưới Y" — dải hở ở giữa, hai biên đã có dòng riêng
                    continue
                if re.match(r"tren", raw_n) and len(nums) >= 2:
                    n = nums[1]   # "Trên 12 tháng đến 13 tháng" -> 13M
                else:
                    n = nums[0]   # "Từ X ... đến dưới Y" hoặc "X tháng" -> X
                term = f"{int(n)}{u}"
            else:
                term = parse_term(raw)
            if term is None:
                continue
            rate = parse_rate(cells[1]) if len(cells) > 1 else None
            if rate:
                out.append((term, "quay", rate))
        return out
