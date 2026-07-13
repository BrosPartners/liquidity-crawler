"""Adapter LPBank (LPB, Lộc Phát / trước là LienVietPostBank) — JSON API.

Trang https://lpbank.com.vn/ca-nhan/lai-suat là Angular SPA (HTML tĩnh KHÔNG có
bảng). Bảng lãi suất được nạp qua 1 API JSON công khai:

    POST https://lpbank.com.vn/api/content-service/public/interest-rate/findAll
    body: {"category": "TK_TTQ_KHCN"}     (Tiết kiệm Tại Quầy — KHCN)

Response: {"status":"200","data":[ {term, groupInterest, recordType,
    startValue, monthValue, quarterValue, endValue, lsVnd, ...}, ... ]}

Ta lấy:
  - recordType == "DATA"            (bỏ NOTE / FILE)
  - groupInterest == "LSHD_VND"     (bỏ USD/EUR)
  - endValue                        (lãi suất lĩnh lãi CUỐI KỲ, %/năm — cột
                                      chuẩn để so sánh giữa các bank)

LPBank chỉ niêm yết biểu lãi suất tại quầy KHCN trên trang này (các tab là
"Chi nhánh/PGD Ngân hàng" và "PGD Bưu điện", đều là gửi tại quầy — không có
bảng Online riêng) → product = "quay".

Đã đối chiếu web (2026-07): 1T=0.10, 1M=4.30, 3M=4.30, 6M=6.20, 12M=6.30,
13M=6.40, 24M=6.60, 36M=6.20.

httpx-only, không cần Playwright. Windows: http2=False.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import List

import httpx

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term

API_URL = "https://lpbank.com.vn/api/content-service/public/interest-rate/findAll"
REFERER = "https://lpbank.com.vn/ca-nhan/lai-suat"
CATEGORY = "TK_TTQ_KHCN"   # Tiết kiệm tại quầy — khách hàng cá nhân


class Adapter:
    code = "LPB"
    name = "LPBank"

    def __init__(self, headful: bool = False):
        pass  # httpx-only; giữ tương thích interface

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        headers = {
            **_HEADERS,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://lpbank.com.vn",
            "Referer": REFERER,
        }
        with httpx.Client(http2=False, follow_redirects=True, timeout=25) as client:
            r = client.post(API_URL, headers=headers,
                            content=json.dumps({"category": CATEGORY}))
            r.raise_for_status()
            data = r.json()

        if str(data.get("status")) != "200":
            raise RuntimeError(f"LPBank API status={data.get('status')} "
                               f"msg={data.get('message')}")

        rows: List[RateRow] = []
        seen: set = set()
        for item in data.get("data") or []:
            if item.get("recordType") != "DATA":
                continue
            if item.get("groupInterest") != "LSHD_VND":
                continue

            term = parse_term(item.get("term") or "")
            if term is None:
                continue

            raw = item.get("endValue")          # lãi cuối kỳ, đã là %/năm
            if raw is None:
                continue
            rate = round(float(raw), 4)
            if not (0 < rate <= 15):            # reject <=0 và >15
                continue

            r_row = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product="quay",
                source_url=REFERER, crawled_at=now,
            )
            if r_row.key() not in seen:
                seen.add(r_row.key())
                rows.append(r_row)
        return rows
