"""Crawl lãi suất liên NH DAILY (đủ kỳ hạn ON/1W/2W/1M/3M) từ Vietstock.

Ghi 2 file (1 lần fetch):
  - data/interbank_rates.csv  (long: date, series_key, value) — cho chart đa kỳ hạn.
  - data/on_rate.csv          (date, value) — CHỈ ON, giữ tương thích với
    assemble_market (gộp lịch sử sâu 'ON rate' ở Sheet cho chart interbank_on).

Adapter Vietstock chính chỉ giữ điểm mới nhất; ở đây lấy TẤT CẢ điểm daily từ
2024-01-01 -> nay và ghi đè (idempotent).

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

from adapters.vietstock_interbank import fetch_all_history

ALL_PATH = os.path.join(_ROOT, "data", "interbank_rates.csv")
ON_PATH = os.path.join(_ROOT, "data", "on_rate.csv")


def main() -> int:
    try:
        hist = fetch_all_history(from_date="2024-01-01")   # [(date, series_key, value)]
    except Exception as e:
        print(f"[FAIL] Vietstock interbank history: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not hist:
        print("[WARN] không lấy được điểm liên NH nào.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(ALL_PATH), exist_ok=True)

    with open(ALL_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        for d, k, v in hist:
            w.writerow([d, k, v])

    on = [(d, v) for d, k, v in hist if k == "interbank_on"]
    with open(ON_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "value"])
        for d, v in on:
            w.writerow([d, v])

    keys = sorted({k for _, k, _ in hist})
    print(f"[OK]   interbank_rates.csv: {len(hist)} điểm, {len(keys)} kỳ hạn "
          f"({keys}); on_rate.csv: {len(on)} ngày")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
