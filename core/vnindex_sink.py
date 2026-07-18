"""Ghi data/vnindex_history.csv (long: date,series_key,value; key="vnindex").

Nguồn VNDirect DChart trả TOÀN BỘ lịch sử trong 1 request (xem
adapters/vnindex.py) — không cần merge tăng dần như các nguồn phân trang
giới hạn (Vietstock/CafeF, đã thử và loại vì cap ngắn). Mỗi lần crawl ghi
đè lại toàn bộ file bằng dữ liệu mới nhất từ nguồn — đơn giản, tự sửa nếu
nguồn có điều chỉnh giá quá khứ.
"""
from __future__ import annotations

import csv
import os

from adapters.vnindex import fetch_history

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "vnindex_history.csv")


def update(from_date: str = "2017-01-01") -> int:
    """Fetch toàn bộ lịch sử, ghi đè CSV. -> số phiên."""
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = fetch_history(from_date)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        for d, v in sorted(rows):
            w.writerow([d, "vnindex", v])

    return len(rows)


if __name__ == "__main__":
    n = update()
    print(f"VN-Index: {n} phiên (2019 -> nay) ghi vào {CSV_PATH}")
