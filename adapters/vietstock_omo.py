"""Khối lượng bơm/hút OMO (nghiệp vụ thị trường mở) — Vietstock, DAILY, tỷ đồng.

Dùng CÙNG endpoint free /Macro/GetReportDataByIDs như VNIBOR liên NH (adapters/
vietstock_interbank.py). UI trang "Kết quả đấu thầu thị trường mở" bị khóa
(VietstockID) nhưng API vẫn trả các NormID:
    521 = Giá trị bơm OMO   (tỷ đồng, +)
    522 = Giá trị hút OMO   (tỷ đồng, -)
    523 = Giá trị bơm ròng OMO (= bơm - hút; + là bơm ròng, - là hút ròng)

fetch_omo_history() -> [(date_iso, bom, hut, net)] daily.
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Tuple

import httpx

from adapters.vietstock_interbank import BASE, ENDPOINT, _HEADERS, _token, _to_float

_PAGE = BASE + "/vi-mo/du-lieu/lai-suat-lien-ngan-hang-vnibor-66"  # trang free để lấy token
_NORMS = {"521": "bom", "522": "hut", "523": "net"}


def fetch_omo_history(days: int = 400) -> List[Tuple[str, float, float, float]]:
    """[(date_iso, bom, hut, net)] daily trong `days` ngày gần nhất (tỷ đồng)."""
    today = _dt.date.today()
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=40, http2=False) as c:
        token = _token(c.get(_PAGE).text)
        if not token:
            raise RuntimeError("Không lấy được __RequestVerificationToken từ Vietstock")
        r = c.post(ENDPOINT, data={
            "listID[]": list(_NORMS.keys()), "termTypeID": 1, "type": "NORM",
            "fromDate": (today - _dt.timedelta(days=days)).isoformat(),
            "toDate": today.isoformat(),
            "__RequestVerificationToken": token,
        }, headers={"Referer": _PAGE, "X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        data = r.json()

    cols = (data.get("DataStructure") or "").split("|")
    ci = {c: i for i, c in enumerate(cols)}
    for need in ("NormID", "TimeOrder", "Value"):
        if need not in ci:
            raise RuntimeError(f"Response Vietstock thiếu cột {need}")

    by_date: dict = {}   # date_iso -> {bom, hut, net}
    for line in data.get("Data") or []:
        parts = line.split("|")
        key = _NORMS.get(parts[ci["NormID"]])
        if not key:
            continue
        val = _to_float(parts[ci["Value"]])
        if val is None:
            continue
        to = parts[ci["TimeOrder"]]  # YYYYMMDD
        if len(to) == 8 and to.isdigit():
            d = f"{to[:4]}-{to[4:6]}-{to[6:8]}"
            by_date.setdefault(d, {})[key] = val

    out = []
    for d in sorted(by_date):
        r = by_date[d]
        bom = r.get("bom")
        hut = r.get("hut")
        net = r.get("net")
        if net is None and bom is not None and hut is not None:
            net = round(bom + hut, 2)   # hut đã âm -> bom + hut = ròng
        if net is None:
            continue
        out.append((d, bom, hut, net))
    return out
