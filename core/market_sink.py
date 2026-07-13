"""Ghi data thị trường: market_latest.json + market_history.csv (chỉ khi đổi)."""
from __future__ import annotations

import csv
import json
import os
from typing import List

from .market_schema import MarketRow

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LATEST = os.path.join(DATA_DIR, "market_latest.json")
HISTORY = os.path.join(DATA_DIR, "market_history.csv")

_FIELDS = list(MarketRow.__annotations__.keys())


def write_json(rows: List[MarketRow], generated_at: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r.cat_rank, r.series_key))
    payload = {
        "generated_at": generated_at,
        "count": len(rows),
        "series": [r.to_dict() for r in rows],
    }
    with open(LATEST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_prev() -> dict:
    """market_latest.json trước -> {series_key: value}."""
    if not os.path.exists(LATEST):
        return {}
    try:
        with open(LATEST, encoding="utf-8") as f:
            data = json.load(f)
        return {d["series_key"]: d.get("value") for d in data.get("series", [])}
    except Exception:
        return {}


def append_history_on_change(rows: List[MarketRow]) -> int:
    """Chỉ ghi vào history những series đổi giá trị so với lần trước.
    Lần đầu (chưa có file) ghi toàn bộ làm baseline cho time series."""
    os.makedirs(DATA_DIR, exist_ok=True)
    new_file = not os.path.exists(HISTORY)
    if new_file:
        changed = rows
    else:
        prev = _load_prev()
        changed = [r for r in rows if prev.get(r.series_key) != r.value]
    if not changed:
        return 0
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in changed:
            w.writerow(r.to_dict())
    return len(changed)
