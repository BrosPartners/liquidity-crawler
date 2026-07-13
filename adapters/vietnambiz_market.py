"""Adapter thị trường tiền tệ — data.vietnambiz.vn/currency-interest-rate.

Trang Next.js SSR, mọi số liệu nhúng trong <script id="__NEXT_DATA__">.
Lấy: lãi suất liên NH qua đêm, lãi suất điều hành SBV (OMO/tín phiếu/chiết khấu/
tái cấp vốn), tỷ giá, tăng trưởng M2/tín dụng/huy động, dự trữ ngoại hối.

Nguồn gốc SBV (dttktt.sbv.gov.vn) bị chặn network + là SPA khó parse -> dùng
VietnamBiz làm nguồn trung gian (miễn phí, không chặn bot). Không có khối lượng
bơm/rút OMO (chỉ WiFeed trả phí có) — chỉ có lãi suất OMO/tín phiếu.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from typing import List

import httpx

from core.market_schema import MarketRow, SERIES_MAP

URL = "https://data.vietnambiz.vn/currency-interest-rate"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept-Language": "vi-VN,vi;q=0.9",
}


def _walk(o, out):
    """Đệ quy gom mọi object dạng series {title/name/label + value}."""
    if isinstance(o, dict):
        keys = set(o.keys())
        if "value" in keys and (keys & {"title", "name", "label"}):
            out.append(o)
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


class Adapter:
    code = "MARKET"
    name = "VietnamBiz Market Data"
    url = URL

    def fetch(self) -> List[MarketRow]:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        today = _dt.date.today().isoformat()

        r = httpx.get(URL, headers=_HEADERS, follow_redirects=True, timeout=30)
        r.raise_for_status()
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            raise RuntimeError("Không tìm thấy __NEXT_DATA__ trên trang VietnamBiz")
        data = json.loads(m.group(1))

        raw: list = []
        _walk(data.get("props", {}), raw)

        rows: List[MarketRow] = []
        seen: set = set()
        for o in raw:
            title = o.get("title") or o.get("name") or o.get("label")
            if title not in SERIES_MAP:
                continue
            key, category, unit = SERIES_MAP[title]
            if key in seen:
                continue
            val = o.get("value")
            try:
                val = round(float(val), 4) if val is not None else None
            except (TypeError, ValueError):
                val = None
            seen.add(key)
            rows.append(MarketRow(
                date=today, series_key=key, label=title, value=val,
                unit=unit, category=category, as_of=str(o.get("ngay") or ""),
                source_url=URL, crawled_at=now,
            ))
        return rows
