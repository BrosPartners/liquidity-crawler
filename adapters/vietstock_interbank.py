"""Adapter lãi suất liên ngân hàng VNIBOR đủ kỳ hạn — Vietstock.

Trang: finance.vietstock.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang-vnibor-66
Data nạp qua AJAX. Luồng:
  1. GET trang -> lấy anti-forgery token (hidden input trong form
     #__CHART_AjaxAntiForgeryForm, thuộc tính KHÔNG có dấu nháy) + cookies.
  2. POST /Macro/GetReportDataByIDs với listID[]=<NormID>, termTypeID=1 (Ngày),
     type=NORM, fromDate/toDate, kèm __RequestVerificationToken.
     Trả JSON {DataStructure, DataType, Data:[ "pipe|delimited|row", ... ]}.

Category 66 = VNIBOR. NormID -> kỳ hạn (đã xác minh):
  293 Qua đêm(ON) 294 1 tuần 295 2 tuần 296 1 tháng 297 3 tháng
  (298 6 tháng, 299 12 tháng thường trống -> bỏ qua).
Giá trị dùng dấu phẩy thập phân (vd "6,62"), unit %/năm.

Vietstock là nguồn chuyên hơn cho liên NH -> cung cấp interbank_on/1w/2w/1m/3m.
crawl_market.py ưu tiên các key này, bỏ interbank_on của VietnamBiz nếu Vietstock OK.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import List, Optional

import httpx

from core.market_schema import MarketRow

BASE = "https://finance.vietstock.vn"
PAGE = BASE + "/vi-mo/du-lieu/lai-suat-lien-ngan-hang-vnibor-66"
ENDPOINT = BASE + "/Macro/GetReportDataByIDs"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept-Language": "vi-VN,vi;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

# NormID -> (series_key, label)
_NORM_MAP = {
    "293": ("interbank_on", "Lãi suất liên ngân hàng qua đêm (ON)"),
    "294": ("interbank_1w", "Lãi suất liên ngân hàng 1 tuần"),
    "295": ("interbank_2w", "Lãi suất liên ngân hàng 2 tuần"),
    "296": ("interbank_1m", "Lãi suất liên ngân hàng 1 tháng"),
    "297": ("interbank_3m", "Lãi suất liên ngân hàng 3 tháng"),
}
_UNIT = "%/năm"


def _token(html: str) -> Optional[str]:
    # thuộc tính có thể có/không dấu nháy: value=AbC-_1 hoặc value="AbC"
    m = re.search(
        r'name=["\']?__RequestVerificationToken["\']?[^>]*?value=["\']?([\w\-]+)', html)
    return m.group(1) if m else None


def _to_float(s: str) -> Optional[float]:
    s = (s or "").strip().replace(".", "").replace(",", ".")  # "1.234,5" -> "1234.5"
    if not s:
        return None
    try:
        return round(float(s), 4)
    except ValueError:
        return None


class Adapter:
    code = "MARKET_VNIBOR"
    name = "Vietstock VNIBOR liên ngân hàng"
    url = PAGE

    def fetch(self) -> List[MarketRow]:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        today = _dt.date.today()

        with httpx.Client(headers=_HEADERS, follow_redirects=True,
                          timeout=30, http2=False) as c:
            html = c.get(PAGE).text
            token = _token(html)
            if not token:
                raise RuntimeError("Không lấy được __RequestVerificationToken từ Vietstock")

            payload = {
                "listID[]": list(_NORM_MAP.keys()),
                "termTypeID": 1,          # 1 = Ngày (daily)
                "type": "NORM",
                "fromDate": (today - _dt.timedelta(days=90)).isoformat(),
                "toDate": today.isoformat(),
                "__RequestVerificationToken": token,
            }
            r = c.post(ENDPOINT, data=payload,
                       headers={"Referer": PAGE, "X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                raise RuntimeError(f"GetReportDataByIDs không trả JSON (ct={ct})")
            data = r.json()

        cols = (data.get("DataStructure") or "").split("|")
        if "NormID" not in cols:
            raise RuntimeError("Response Vietstock thiếu cột NormID")
        ci = {c: i for i, c in enumerate(cols)}
        raw = data.get("Data") or []
        if not raw:
            raise RuntimeError("Vietstock trả Data rỗng")

        # với mỗi NormID lấy dòng mới nhất theo TimeOrder (YYYYMMDD)
        latest: dict = {}
        for line in raw:
            parts = line.split("|")
            nid = parts[ci["NormID"]]
            if nid not in _NORM_MAP:
                continue
            order = parts[ci["TimeOrder"]]
            val = parts[ci["Value"]]
            if not (val or "").strip():
                continue  # bỏ dòng không có giá trị
            cur = latest.get(nid)
            if cur is None or order > cur[0]:
                latest[nid] = (order, parts)

        rows: List[MarketRow] = []
        for nid, (order, parts) in latest.items():
            key, label = _NORM_MAP[nid]
            val = _to_float(parts[ci["Value"]])
            if val is None:
                continue
            as_of = parts[ci["ReportTime"]]  # dd/mm/yyyy
            rows.append(MarketRow(
                date=today.isoformat(), series_key=key, label=label, value=val,
                unit=_UNIT, category="lien_nh", as_of=as_of,
                source_url=PAGE, crawled_at=now,
            ))
        if not rows:
            raise RuntimeError("Vietstock: không parse được kỳ hạn liên NH nào")
        return rows
