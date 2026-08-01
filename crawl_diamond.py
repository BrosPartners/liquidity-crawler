"""Crawl chỉ số giá kim cương IDEX Diamond Index (Total) DAILY.

Nguồn: idexonline.com/diamond_prices_index — chart Flot nạp qua endpoint
    /Bid_Control-home_graph?driver_id=0&fromDate=YYYY-M-D&toDate=YYYY-M-D
trả JSON {"label":"Total","data":[[timestamp_ms, index], ...]} (daily, free,
không cần auth). driver_id=0 = chỉ số tổng.

Ghi đè data/diamond_index.csv (date, value) từ 2024-01-01 -> nay (idempotent).

    python crawl_diamond.py
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import sys

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(_ROOT, "data", "diamond_index.csv")
_URL = "https://www.idexonline.com/Bid_Control-home_graph"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Referer": "https://www.idexonline.com/diamond_prices_index",
    "X-Requested-With": "XMLHttpRequest",
}


def main() -> int:
    today = _dt.date.today()
    params = {"driver_id": "0", "fromDate": "2024-1-1",
              "toDate": f"{today.year}-{today.month}-{today.day}"}
    try:
        r = httpx.get(_URL, params=params, headers=_HEADERS, timeout=40, follow_redirects=True)
        r.raise_for_status()
        data = r.json().get("data") or []
    except Exception as e:
        print(f"[FAIL] IDEX: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not data:
        print("[WARN] IDEX trả data rỗng.", file=sys.stderr)
        return 1

    rows = []
    for pt in data:
        try:
            ms, val = pt[0], pt[1]
            d = _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc).strftime("%Y-%m-%d")
            rows.append((d, round(float(val), 2)))
        except (TypeError, ValueError, IndexError):
            continue
    # dedup theo ngày (giữ điểm cuối), sắp tăng dần
    by = {}
    for d, v in rows:
        by[d] = v
    rows = sorted(by.items())

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "value"])
        w.writerows(rows)
    print(f"[OK]   diamond_index.csv: {len(rows)} ngày ({rows[0][0]} -> {rows[-1][0]}), "
          f"cuối={rows[-1][1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
