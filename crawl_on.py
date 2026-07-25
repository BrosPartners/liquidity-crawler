"""Crawl lãi suất liên NH qua đêm (ON) DAILY -> data/on_rate.csv.

Adapter Vietstock chính chỉ giữ điểm mới nhất; ở đây lấy TẤT CẢ điểm daily ~120
ngày gần nhất và ghi đè on_rate.csv (idempotent). build_static/assemble_market
gộp file này (local THẮNG cho ngày trùng) với lịch sử sâu 2014→ ở Sheet 'ON rate'
-> chart ON rate luôn daily, tự backfill các ngày vừa rồi.

    python crawl_on.py
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

from adapters.vietstock_interbank import fetch_on_history

CSV_PATH = os.path.join(_ROOT, "data", "on_rate.csv")


def main() -> int:
    try:
        hist = fetch_on_history(120)
    except Exception as e:
        print(f"[FAIL] Vietstock ON history: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not hist:
        print("[WARN] không lấy được điểm ON nào.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "value"])
        for d, v in hist:
            w.writerow([d, v])
    print(f"[OK]   on_rate.csv: {len(hist)} ngày ({hist[0][0]} -> {hist[-1][0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
