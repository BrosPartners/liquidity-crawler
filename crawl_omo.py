"""Crawl khối lượng bơm/hút OMO DAILY -> data/omo_volume.csv (tỷ đồng).

Nguồn: Vietstock /Macro/GetReportDataByIDs (free, xem adapters/vietstock_omo.py).
Ghi đè file mỗi lần (idempotent, ~400 ngày gần nhất).

    python crawl_omo.py
"""
from __future__ import annotations

import csv
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from adapters.vietstock_omo import fetch_omo_history

CSV_PATH = os.path.join(_ROOT, "data", "omo_volume.csv")


def main() -> int:
    try:
        hist = fetch_omo_history(400)
    except Exception as e:
        print(f"[FAIL] Vietstock OMO: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not hist:
        print("[WARN] không lấy được điểm OMO nào.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "bom", "hut", "net"])
        for d, bom, hut, net in hist:
            w.writerow([d, "" if bom is None else bom, "" if hut is None else hut, net])
    print(f"[OK]   omo_volume.csv: {len(hist)} ngày ({hist[0][0]} -> {hist[-1][0]}), "
          f"net cuối={hist[-1][3]} tỷ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
