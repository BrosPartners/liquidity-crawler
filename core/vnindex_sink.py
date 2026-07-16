"""Cập nhật data/vnindex_history.csv (long: date,series_key,value; key="vnindex").

Nguồn Vietstock (xem adapters/vietstock_vnindex.py) chỉ trả tối đa ~1 năm lịch
sử qua endpoint miễn phí (trang 14+ luôn rỗng, đã verify) — không phải giới
hạn code, mà là giới hạn thật của trang "Thống kê giá" công khai. Vì vậy
KHÔNG backfill lại mỗi ngày (lãng phí + vô ích); mỗi lần crawl chỉ lấy vài
trang gần nhất rồi MERGE vào file đã có, giúp lịch sử tự dài ra theo thời
gian (giống cách accumulate của các series thị trường khác trong dự án).
"""
from __future__ import annotations

import csv
import os
from typing import List, Tuple

from adapters.vietstock_vnindex import fetch_latest

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "vnindex_history.csv")


def _read_existing() -> dict:
    out = {}
    if not os.path.exists(CSV_PATH):
        return out
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("series_key") == "vnindex" and row.get("date"):
                try:
                    out[row["date"]] = float(row["value"])
                except (TypeError, ValueError):
                    continue
    return out


def update(n_pages: int = 3) -> Tuple[int, int]:
    """Lấy ~n_pages*20 phiên gần nhất, merge vào CSV. -> (tổng dòng, dòng mới/đổi)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    existing = _read_existing()
    fresh: List[Tuple[str, float]] = fetch_latest(n_pages=n_pages)

    changed = 0
    for d, v in fresh:
        if existing.get(d) != v:
            existing[d] = v
            changed += 1

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        for d in sorted(existing):
            w.writerow([d, "vnindex", existing[d]])

    return len(existing), changed


if __name__ == "__main__":
    total, changed = update()
    print(f"VN-Index: {total} phiên trong file, {changed} phiên mới/đổi lần này.")
