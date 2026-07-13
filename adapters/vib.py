"""Adapter VIB — lãi suất tiết kiệm KHCN (Playwright render, không dùng httpx).

Nguồn: https://www.vib.com.vn/vn/tiet-kiem  (mode = 'render')

Vì sao Playwright bắt buộc:
  - www.vib.com.vn có WAF "Challenge Validation" (proof-of-work) chặn httpx →
    fetch tĩnh chỉ trả về trang challenge 1.8KB, không có dữ liệu.
  - Trang /vn/lai-suat là trang 404 (SPA). Trang niêm yết lãi suất tiết kiệm
    thực tế là /vn/tiet-kiem, render server-side sau khi qua challenge.

Cấu trúc trang (2026-07):
  Mỗi sản phẩm là 1 div.saving-li-item-content, có:
    - input.sav-title      : tên sản phẩm
    - input.sav-int-type   : IT1 = "Tiền gửi trực tuyến" (online);
                             IT2 = "Tiền gửi có kỳ hạn" (tại quầy)
    - input.sav-ccy        : loại tiền (chỉ lấy VND)
    - div.vib-v2-left-box-table-expression  : các kỳ hạn (header cột)
        thứ tự: [1 tháng, 6 tháng, < 1 tháng, 2, 3, 4, 5, 7, 8, 9, 10, 11,
                 12, 15, 18, 24, 36] — "Nổi bật" chỉ là badge trên 1T & 6T.
    - div.vib-v2-right-box-table-expression : mỗi row = 1 mức tiền gửi,
        gồm nhãn mức + N giá trị "X.XX%" khớp thứ tự header.

Ta chỉ lấy 2 sản phẩm tiết kiệm cá nhân VND chuẩn:
  IT1 → product="online", IT2 → product="quay".
Lấy dòng mức gửi THẤP NHẤT (row đầu) làm lãi suất đại diện.
Kỳ hạn "< 1 tháng" → parse_term() trả None → tự động bị bỏ (đúng ý).

Đối chiếu web 2026-07:
  Online (min 2tr): 3M=4.45, 12M=7.00  |  Tại quầy (min 10tr): 3M=4.35, 12M=6.50
"""
from __future__ import annotations

import re
from typing import List, Tuple

from bs4 import BeautifulSoup

from adapters.base import BankAdapter
from core.normalize import parse_term, parse_rate

_RATE_RE = re.compile(r"-?\d+(?:[.,]\d+)?\s*%")


class Adapter(BankAdapter):
    code = "VIB"
    name = "VIB"
    url = "https://www.vib.com.vn/vn/tiet-kiem"
    mode = "render"
    # Đợi ít nhất 1 khối sản phẩm đã render xong (class is_loaded)
    wait_selector = "div.saving-li-item-content.is_loaded"

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        out: List[Tuple[str, str, float]] = []

        for block in soup.select("div.saving-li-item-content"):
            def _val(cls: str) -> str:
                el = block.select_one("input." + cls)
                return (el.get("value") or "").strip() if el else ""

            int_type = _val("sav-int-type")
            ccy = _val("sav-ccy")

            # Chỉ 2 sản phẩm tiết kiệm cá nhân VND chuẩn.
            if int_type == "IT1":
                product = "online"
            elif int_type == "IT2":
                product = "quay"
            else:
                continue
            if "VND" not in ccy:
                continue

            left = block.select_one("div.vib-v2-left-box-table-expression")
            right = block.select_one("div.vib-v2-right-box-table-expression")
            if left is None or right is None:
                continue

            # Header kỳ hạn: mỗi ô con là 1 cột. Bỏ ô rỗng đầu (nếu có).
            headers = [
                x.get_text(" ", strip=True)
                for x in left.find_all(recursive=False)
            ]
            headers = [h for h in headers if h]
            terms = [parse_term(h) for h in headers]

            # Dòng dữ liệu: lấy mức gửi thấp nhất (row đầu tiên).
            rows = right.find_all(recursive=False)
            if not rows:
                continue
            row_text = rows[0].get_text(" ", strip=True)
            rates_raw = _RATE_RE.findall(row_text)

            # Mỗi row đầu chứa đúng N giá trị khớp N cột kỳ hạn (mức gửi thấp
            # nhất). Nếu lấy hụt → bỏ qua an toàn; nếu dư → cắt N phần tử đầu.
            if len(rates_raw) < len(terms):
                continue
            rates_raw = rates_raw[: len(terms)]

            for term, raw in zip(terms, rates_raw):
                if term is None:                       # "< 1 tháng" → bỏ
                    continue
                rate = parse_rate(raw)                 # reject <=0, >15, None
                if rate is None:
                    continue
                out.append((term, product, rate))

        return out
