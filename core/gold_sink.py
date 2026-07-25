"""Ghi output giá vàng cho dashboard: latest.json + history.csv (long) + brands.csv."""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os

HIST_KEYS = ["world_gold_usd", "world_gold_vnd", "sjc_sell", "gap", "pct_gap",
             "usd_vnd", "fx_vcb", "fx_tudo", "fx_sbv"]


def write_gold_outputs(data, data_dir):
    os.makedirs(data_dir, exist_ok=True)

    with open(os.path.join(data_dir, "gold_latest.json"), "w", encoding="utf-8") as f:
        json.dump(data["latest"], f, ensure_ascii=False, indent=2)

    # MERGE (không ghi đè cụt): giữ lịch sử cũ, chỉ cập nhật/thêm cho các ngày GẦN
    # ĐÂY (<=180 ngày so với mốc mới nhất của file). Nhờ vậy khi file nguồn thay đổi
    # cấu trúc / thiếu lịch sử cũ (vd bỏ cột tỷ giá, mất SJC 2017-2023) thì lịch sử
    # tốt đã tích lũy KHÔNG bị mất; các ngày cũ là bất biến, tránh dòng sai ngày ghi đè.
    hist_path = os.path.join(data_dir, "gold_history.csv")
    merged = {}   # (date, key) -> value(str)
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 3 and row[0] != "date":
                    merged[(row[0], row[1])] = row[2]

    new_dates = [row["date"] for row in data["history"] if row.get("date")]
    max_new = max(new_dates) if new_dates else ""
    cutoff = ""
    if max_new:
        try:
            cutoff = (_dt.date.fromisoformat(max_new) - _dt.timedelta(days=180)).isoformat()
        except Exception:
            cutoff = ""
    for row in data["history"]:
        d = row.get("date")
        if not d or (cutoff and d < cutoff):   # ngày cũ: giữ nguyên lịch sử
            continue
        for k in HIST_KEYS:
            v = row.get(k)
            if v is not None:
                merged[(d, k)] = v

    with open(hist_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "series_key", "value"])
        for (d, k) in sorted(merged):
            w.writerow([d, k, merged[(d, k)]])

    with open(os.path.join(data_dir, "gold_brands.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "company", "buy", "sell"])
        for b in data["brands"]:
            w.writerow([b["date"], b["company"],
                        "" if b["buy"] is None else b["buy"],
                        "" if b["sell"] is None else b["sell"]])
