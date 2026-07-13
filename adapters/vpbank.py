"""Adapter VPBank (VPB) — JSON API.

VPBank có JSON endpoint trả về bảng lãi suất tiết kiệm theo tier tiền gửi.
Ta lấy tier thấp nhất (< 300 triệu) làm mức tham chiếu chuẩn.

Ghi chú (đã điều tra 2026-07): API chỉ trả đúng 4 kỳ hạn
(1M/6M/12M/24M) — không có tham số nào (?type/?channel/?id...) mở thêm
kỳ hạn; JS của chính vpbank.com.vn cũng gọi endpoint này không tham số.
Adapter đã đọc động toàn bộ `columns`, nếu API bổ sung kỳ hạn sẽ tự lấy.
"""
from __future__ import annotations

from typing import List

import httpx

from adapters.base import _HEADERS
from core.normalize import parse_term
from core.schema import RateRow
import datetime as _dt

API_URL = "https://www.vpbank.com.vn/uiux-api/api/interest-rate"


class Adapter:
    code = "VPB"
    name = "VPBank"
    url = API_URL

    def __init__(self, headful: bool = False):
        pass

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=20, http2=False) as client:
            r = client.get(API_URL)
            r.raise_for_status()
            payload = r.json()

        columns = payload.get("columns", [])   # ["1 tháng", "6 tháng", ...]
        data = payload.get("data", [])          # list of rows (tier × term)

        if not columns or not data:
            return []

        # Use first tier (lowest amount, most accessible = "quầy" standard)
        rates_row = data[0]

        rows: List[RateRow] = []
        seen: set = set()
        for col_idx, col_label in enumerate(columns):
            term = parse_term(col_label)
            if term is None:
                continue
            if col_idx >= len(rates_row):
                continue
            rate_val = rates_row[col_idx]
            if not isinstance(rate_val, (int, float)) or rate_val <= 0 or rate_val > 15:
                continue

            row_obj = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=float(rate_val), product="quay",
                source_url=API_URL, crawled_at=now,
            )
            key = row_obj.key()
            if key not in seen:
                seen.add(key)
                rows.append(row_obj)

        return rows
