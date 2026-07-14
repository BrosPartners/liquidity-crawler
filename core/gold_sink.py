"""Ghi output giá vàng cho dashboard: latest.json + history.csv (long) + brands.csv."""
from __future__ import annotations

import csv
import json
import os

HIST_KEYS = ["world_gold_usd", "world_gold_vnd", "sjc_sell", "gap", "pct_gap",
             "usd_vnd", "fx_vcb", "fx_tudo", "fx_sbv"]


def write_gold_outputs(data, data_dir):
    os.makedirs(data_dir, exist_ok=True)

    with open(os.path.join(data_dir, "gold_latest.json"), "w", encoding="utf-8") as f:
        json.dump(data["latest"], f, ensure_ascii=False, indent=2)

    with open(os.path.join(data_dir, "gold_history.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "series_key", "value"])
        for row in data["history"]:
            for k in HIST_KEYS:
                v = row.get(k)
                if v is not None:
                    w.writerow([row["date"], k, v])

    with open(os.path.join(data_dir, "gold_brands.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "company", "buy", "sell"])
        for b in data["brands"]:
            w.writerow([b["date"], b["company"],
                        "" if b["buy"] is None else b["buy"],
                        "" if b["sell"] is None else b["sell"]])
