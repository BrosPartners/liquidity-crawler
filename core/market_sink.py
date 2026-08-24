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


def _existing_today_keys(dates: set) -> set:
    """{(date, series_key)} da co san trong history, chi doc cac dong co
    date nam trong `dates` — dung de chong trung khi workflow chay lai
    2 lan cung 1 ngay (vd workflow_dispatch thu cong)."""
    if not os.path.exists(HISTORY):
        return set()
    out = set()
    try:
        with open(HISTORY, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("date") in dates:
                    out.add((row.get("date"), row.get("series_key")))
    except Exception:
        pass
    return out


def append_history_on_change(rows: List[MarketRow]) -> int:
    """Ghi 1 dong/ngay cho MOI series, KE CA khi gia tri khong doi — de chart
    khong bi 'dung lai' truoc mat khi gia tri phang nhieu ngay lien tiep
    (vd ty gia trung tam SBV giu nguyen vai ngay). Idempotent trong cung 1
    ngay: chi bo qua neu (date, series_key) do DA co san (tranh dong trung
    khi chay lai workflow thu cong).

    Ten ham giu nguyen (khong phai "on_change" nua) de khong phai sua cac
    noi da goi no (crawl_market.py, scripts/backfill_market_*.py)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    new_file = not os.path.exists(HISTORY)
    if new_file:
        to_write = rows
    else:
        existing = _existing_today_keys({r.date for r in rows})
        to_write = [r for r in rows if (r.date, r.series_key) not in existing]
    if not to_write:
        return 0
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in to_write:
            w.writerow(r.to_dict())
    return len(to_write)
