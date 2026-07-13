"""Ghi dữ liệu ra: JSON (nguồn cho website) + history.csv (chỉ ghi khi đổi).

Google Sheet là tùy chọn (import nội bộ để không bắt buộc cài gspread cho MVP).
"""
from __future__ import annotations

import csv
import json
import os
from typing import List

from .schema import RateRow

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LATEST = os.path.join(DATA_DIR, "latest.json")
HISTORY = os.path.join(DATA_DIR, "history.csv")

_FIELDS = list(RateRow.__annotations__.keys())


def _load_prev() -> dict:
    """latest.json trước đó -> {key: rate} để so sánh phát hiện thay đổi."""
    if not os.path.exists(LATEST):
        return {}
    try:
        with open(LATEST, encoding="utf-8") as f:
            data = json.load(f)
        prev = {}
        for d in data.get("rates", []):
            r = RateRow(**{k: d.get(k) for k in _FIELDS})
            prev[r.key()] = r.rate
        return prev
    except Exception:
        return {}


def write_json(rows: List[RateRow], generated_at: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r.bank_code, r.product, r.term_rank))
    payload = {
        "generated_at": generated_at,
        "count": len(rows),
        "banks": sorted({r.bank_code for r in rows}),
        "rates": [r.to_dict() for r in rows],
    }
    with open(LATEST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def append_history_on_change(rows: List[RateRow]) -> int:
    """Chỉ ghi vào history.csv những mức đã đổi so với lần trước. Trả về số dòng ghi."""
    os.makedirs(DATA_DIR, exist_ok=True)
    new_file = not os.path.exists(HISTORY)
    if new_file:
        changed = rows  # baseline: ghi toàn bộ snapshot đầu tiên làm mốc cho time series
    else:
        prev = _load_prev()
        changed = [r for r in rows if prev.get(r.key()) != r.rate]
    if not changed:
        return 0
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in changed:
            w.writerow(r.to_dict())
    return len(changed)


def write_sheet(rows: List[RateRow]) -> None:
    """Tùy chọn — ghi snapshot mới nhất vào Google Sheet.

    Cần: pip install gspread google-auth và env GOOGLE_APPLICATION_CREDENTIALS,
    GSHEET_ID. Bỏ qua êm nếu chưa cấu hình.
    """
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        return
    import gspread  # import muộn — không bắt buộc cho MVP

    gc = gspread.service_account(filename=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    ws = gc.open_by_key(sheet_id).sheet1
    ws.clear()
    ws.update([_FIELDS] + [[r.to_dict()[k] for k in _FIELDS] for r in rows])
