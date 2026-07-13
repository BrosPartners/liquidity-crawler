"""Adapter Vietcombank (VCB) — JSON API (không cần Playwright).

Endpoint: GET /vi-VN/api/interestrates?accountType=Personal
Trả về JSON: {Count, UpdatedDate, AccountType, Data: [{tenorType, tenor,
  currencyCode, tenorDisplay, rates}, ...]}

Ta chỉ lấy currencyCode=VND, tenorType=Savings (tiết kiệm).
VCB không phân biệt online/quầy trong API này — gán product='quay'.
"""
from __future__ import annotations

import datetime as _dt
from typing import List

import httpx

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate

API_URL = "https://www.vietcombank.com.vn/vi-VN/api/interestrates?accountType=Personal"
REFERER = "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/KHCN---Lai-suat"


class Adapter:
    code = "VCB"
    name = "Vietcombank"

    def __init__(self, headful: bool = False):
        pass  # headful không dùng, giữ tương thích interface

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(http2=False, follow_redirects=True, timeout=20) as client:
            r = client.get(API_URL, headers={**_HEADERS, "Referer": REFERER,
                                             "Accept": "application/json"})
            r.raise_for_status()
            data = r.json()

        rows: List[RateRow] = []
        seen: set = set()
        for item in data.get("Data", []):
            if item.get("currencyCode") != "VND":
                continue
            if item.get("tenorType") not in ("Savings", "TimeDeposit", None):
                continue
            raw_term = item.get("tenorDisplay") or item.get("tenor") or ""
            term = parse_term(raw_term)
            if term is None:
                continue
            # API trả decimal (0.059 = 5.9%/năm) → nhân 100
            raw_rate = item.get("rates")
            rate = round(float(raw_rate) * 100, 4) if raw_rate is not None else None
            if rate is not None and not (0 < rate <= 15):
                rate = None
            if rate is None:
                continue
            r_row = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product="quay",
                source_url=API_URL, crawled_at=now,
            )
            if r_row.key() not in seen:
                seen.add(r_row.key())
                rows.append(r_row)
        return rows
