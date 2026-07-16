"""Lịch sử VN-Index (đóng cửa hàng ngày) — VNDirect DChart API.

Endpoint public, không cần đăng nhập/token (dùng bởi nhiều app tài chính VN
để nhúng chart, định dạng UDF chuẩn TradingView):

    GET https://dchart-api.vndirect.com.vn/dchart/history
        ?resolution=D&symbol=VNINDEX&from=<unix>&to=<unix>

Trả về TOÀN BỘ khoảng ngày trong 1 request (không phân trang) — khác hẳn
Vietstock (giới hạn cứng ~1 năm, trang 14+ luôn rỗng) và CafeF (giới hạn
~3 tháng, đã thử và loại). Đã verify: đáy COVID 2020-03-24 = 659.21 khớp
lịch sử; giá trị mới nhất khớp Vietstock live.

Response: {"t":[unix...], "o":[...], "h":[...], "l":[...], "c":[...],
"v":[...], "s":"ok"}. Ta chỉ cần "t" (đổi UTC date) + "c" (đóng cửa).
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Tuple

import httpx

URL = "https://dchart-api.vndirect.com.vn/dchart/history"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
}


def fetch_history(from_date: str = "2019-01-01") -> List[Tuple[str, float]]:
    """[(date_iso, close)] tăng dần, từ from_date ('YYYY-MM-DD') đến hôm nay."""
    d0 = _dt.datetime.strptime(from_date, "%Y-%m-%d")
    frm = int(d0.timestamp())
    to = int(_dt.datetime.now().timestamp()) + 86400

    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30, http2=False) as c:
        r = c.get(URL, params={"resolution": "D", "symbol": "VNINDEX", "from": frm, "to": to})
        r.raise_for_status()
        data = r.json()

    if data.get("s") != "ok":
        raise RuntimeError(f"VNDirect DChart trả status không phải 'ok': {data.get('s')}")

    ts, closes = data.get("t") or [], data.get("c") or []
    out = []
    for t, close in zip(ts, closes):
        d = _dt.datetime.utcfromtimestamp(t).date().isoformat()
        if close is not None:
            out.append((d, float(close)))
    return out
