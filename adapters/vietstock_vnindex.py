"""Lịch sử VN-Index (đóng cửa hàng ngày) — Vietstock.

Trang: finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1&code=-19
Data nạp qua AJAX (giống pattern vietstock_interbank.py — anti-forgery token):
  1. GET trang -> lấy __RequestVerificationToken (hidden input, có thể không có
     dấu nháy quanh value) + cookies phiên.
  2. POST /data/KQGDThongKeGiaStockPaging (form-encoded):
     page, pageSize, catID=1 (HOSE), stockID=-19 (mã đặc biệt của VN-Index),
     fromDate/toDate (YYYY-MM-DD), __RequestVerificationToken.
     Server LUÔN trả tối đa 20 dòng/trang (pageSize lớn hơn bị bỏ qua, đã verify).
     Response JSON: [ [1 dòng tóm tắt], [list dòng theo TrID giảm dần, mới nhất
     trước] ]. Field cần: TradingDate ("/Date(unix_ms)/"), ClosePrice.

fromDate/toDate lọc theo NGÀY GIAO DỊCH nhưng vẫn phải phân trang thủ công
(page=1,2,3,...) vì server không tôn trọng khoảng ngày để trả gọn — trang sau
luôn là 20 phiên liền trước, bất kể ta đặt fromDate xa đến đâu. Dừng khi trang
trả về rỗng HOẶC ngày trong trang đã < from_date.
"""
from __future__ import annotations

import datetime as _dt
import re
import time
from typing import List, Optional, Tuple

import httpx

BASE = "https://finance.vietstock.vn"
PAGE = BASE + "/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1&code=-19"
ENDPOINT = BASE + "/data/KQGDThongKeGiaStockPaging"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept-Language": "vi-VN,vi;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


def _token(html: str) -> Optional[str]:
    m = re.search(
        r'name=["\']?__RequestVerificationToken["\']?[^>]*?value=["\']?([\w\-]+)', html)
    return m.group(1) if m else None


def _from_dotnet_date(s: str) -> Optional[str]:
    """'/Date(1784048400000)/' -> '2026-07-14' (UTC — khớp ngày giao dịch VN)."""
    m = re.search(r"\((\d+)\)", s or "")
    if not m:
        return None
    ts = int(m.group(1)) / 1000
    return _dt.datetime.utcfromtimestamp(ts).date().isoformat()


def fetch_range(from_date: str, to_date: Optional[str] = None,
                 delay: float = 0.4, max_pages: int = 500) -> List[Tuple[str, float]]:
    """[(date_iso, close)] giảm dần theo TrID, đã lọc >= from_date, <= to_date.

    from_date/to_date: 'YYYY-MM-DD'. Dừng phân trang khi gặp ngày < from_date
    hoặc trang rỗng. delay giữa các trang để lịch sự với server.
    """
    to_date = to_date or _dt.date.today().isoformat()
    out: List[Tuple[str, float]] = []

    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30, http2=False) as c:
        html = c.get(PAGE).text
        token = _token(html)
        if not token:
            raise RuntimeError("Không lấy được __RequestVerificationToken từ Vietstock")

        page = 1
        while page <= max_pages:
            payload = {
                "page": page, "pageSize": 20, "catID": 1, "stockID": -19,
                "fromDate": from_date, "toDate": to_date,
                "__RequestVerificationToken": token,
            }
            r = c.post(ENDPOINT, data=payload,
                       headers={"Referer": PAGE, "X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status()
            data = r.json()
            rows = data[1] if len(data) > 1 else []
            if not rows:
                break

            stop = False
            for row in rows:
                d = _from_dotnet_date(row.get("TradingDate", ""))
                close = row.get("ClosePrice")
                if not d or close is None:
                    continue
                if d < from_date:
                    stop = True
                    break
                out.append((d, float(close)))
            if stop or len(rows) < 20:
                break
            page += 1
            time.sleep(delay)

    return out


def fetch_latest(n_pages: int = 3) -> List[Tuple[str, float]]:
    """~n_pages*20 phiên gần nhất — dùng cho crawl hằng ngày (không cần backfill lại)."""
    today = _dt.date.today()
    from_date = (today - _dt.timedelta(days=n_pages * 30)).isoformat()
    return fetch_range(from_date, today.isoformat(), max_pages=n_pages)
