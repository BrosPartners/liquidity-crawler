"""Crawl chỉ số giá kim cương IDEX theo NHIỀU kích thước (carat) DAILY.

Nguồn: idexonline.com endpoint Flot
    /Bid_Control-home_graph?driver_id=<id>&fromDate=YYYY-M-D&toDate=YYYY-M-D
trả JSON {"label":..., "data":[[ms, index]]} (daily, free). Mỗi driver_id là 1
danh mục (shape + carat + màu/độ sạch). Lấy Tổng + thang Round theo carat.

Ghi data/diamond_index.csv dạng LONG (date, series_key, value) từ 2015 -> nay.

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
# series_key -> (driver_id, nhãn). Tổng + thang kích thước Round (0.5ct -> 5ct).
_DRIVERS = {
    "d_total":     (0,  "Tổng (Total)"),
    "d_round_0_5": (7,  "Round 0.5ct"),
    "d_round_0_7": (6,  "Round 0.7ct"),
    "d_round_0_9": (10, "Round 0.9ct"),
    "d_round_1_0": (1,  "Round 1ct"),
    "d_round_1_5": (3,  "Round 1.5ct"),
    "d_round_2_0": (2,  "Round 2ct"),
    "d_round_3_0": (5,  "Round 3ct"),
    "d_round_4_0": (15, "Round 4ct"),
    "d_round_5_0": (12, "Round 5ct"),
}


def _fetch(client, did: int) -> "list[tuple[str, float]]":
    r = client.get(_URL, params={"driver_id": str(did), "fromDate": "2015-1-1",
                                 "toDate": f"{_dt.date.today().year}-{_dt.date.today().month}-{_dt.date.today().day}"})
    r.raise_for_status()
    out = {}
    for pt in r.json().get("data") or []:
        try:
            d = _dt.datetime.fromtimestamp(pt[0] / 1000, _dt.timezone.utc).strftime("%Y-%m-%d")
            out[d] = round(float(pt[1]), 2)
        except (TypeError, ValueError, IndexError):
            continue
    return sorted(out.items())


def main() -> int:
    rows = []
    with httpx.Client(headers=_HEADERS, timeout=40, follow_redirects=True) as c:
        for key, (did, label) in _DRIVERS.items():
            try:
                pts = _fetch(c, did)
            except Exception as e:
                print(f"[WARN] {key} (driver {did}): {type(e).__name__}: {e}", file=sys.stderr)
                continue
            for d, v in pts:
                rows.append((d, key, v))
            if pts:
                print(f"[ok]  {key:12} {len(pts):5} ngày  {pts[0][0]} -> {pts[-1][0]}  cuối={pts[-1][1]}")

    if not rows:
        print("[FAIL] IDEX không trả điểm nào — giữ file cũ.", file=sys.stderr)
        return 1
    rows.sort()
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        w.writerows(rows)
    print(f"[OK]  diamond_index.csv: {len(rows)} dòng, {len({k for _, k, _ in rows})} kích thước")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
