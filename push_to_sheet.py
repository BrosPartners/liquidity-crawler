"""Đẩy data mới nhất (lãi suất huy động + thị trường + ON rate) lên Google Sheet.

    python push_to_sheet.py

Đọc data/latest.json + data/market_latest.json, POST lên Apps Script Web App
(cấu hình trong config.json). Ghi vào 3 tab:
  - "Auto - Deposit"  : lãi suất huy động dạng long (date,bank,term,rate,product)
  - "Auto - Market"   : chỉ tiêu thị trường (liên NH đủ kỳ hạn, OMO, tỷ giá, vĩ mô)
  - "ON rate"         : append 1 điểm ON rate của tuần vào tab lịch sử sẵn có

Dùng keyCols để chạy lại cùng tuần không bị lặp (upsert theo khoá).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.sheet_client import load_config, push_rows

_ROOT = os.path.dirname(os.path.abspath(__file__))
LATEST = os.path.join(_ROOT, "data", "latest.json")
MKT_LATEST = os.path.join(_ROOT, "data", "market_latest.json")

DEP_HEADER = ["date", "bank_code", "bank_name", "term", "rate", "product", "source_url"]
DEP_KEYCOLS = [0, 1, 3, 5]           # date + bank + term + product

MKT_HEADER = ["date", "series_key", "label", "value", "unit", "category", "as_of", "source_url"]
MKT_KEYCOLS = [0, 1]                 # date + series_key


def _load(path: str):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mmddyyyy(iso: str) -> str:
    """'2026-07-04' -> '07/04/2026' (khớp định dạng tab ON rate)."""
    try:
        return _dt.datetime.strptime(iso, "%Y-%m-%d").strftime("%m/%d/%Y")
    except Exception:
        return iso


def main() -> int:
    cfg = load_config()
    if not cfg.can_push:
        print("[SKIP] Chưa cấu hình config.json (web_app_url/token). "
              "Xem sheets/README.md để deploy Apps Script rồi điền config.", file=sys.stderr)
        return 0

    latest = _load(LATEST)
    mkt = _load(MKT_LATEST)
    total_ok = True

    # 1. Lãi suất huy động -> "Auto - Deposit"
    if latest and latest.get("rates"):
        rows = [[r["date"], r["bank_code"], r["bank_name"], r["term"],
                 r["rate"], r["product"], r.get("source_url", "")]
                for r in latest["rates"]]
        try:
            resp = push_rows(cfg, "Auto - Deposit", rows,
                             header=DEP_HEADER, key_cols=DEP_KEYCOLS)
            print(f"[OK]   Auto - Deposit: {resp}")
            total_ok &= bool(resp.get("ok"))
        except Exception as e:
            print(f"[FAIL] Auto - Deposit: {type(e).__name__}: {e}", file=sys.stderr)
            total_ok = False
    else:
        print("[WARN] Không có data/latest.json để đẩy.", file=sys.stderr)

    # 2. Chỉ tiêu thị trường -> "Auto - Market"
    if mkt and mkt.get("series"):
        rows = [[s["date"], s["series_key"], s["label"], s["value"],
                 s.get("unit", ""), s.get("category", ""), s.get("as_of", ""),
                 s.get("source_url", "")]
                for s in mkt["series"]]
        try:
            resp = push_rows(cfg, "Auto - Market", rows,
                             header=MKT_HEADER, key_cols=MKT_KEYCOLS)
            print(f"[OK]   Auto - Market: {resp}")
            total_ok &= bool(resp.get("ok"))
        except Exception as e:
            print(f"[FAIL] Auto - Market: {type(e).__name__}: {e}", file=sys.stderr)
            total_ok = False

        # 3. ON rate -> append vào tab lịch sử "ON rate" (Date, ON rate)
        on = next((s for s in mkt["series"] if s["series_key"] == "interbank_on"), None)
        if on and on.get("value") is not None:
            row = [[_mmddyyyy(on["date"]), on["value"]]]
            try:
                resp = push_rows(cfg, "ON rate", row, key_cols=[0])
                print(f"[OK]   ON rate: {resp}")
                total_ok &= bool(resp.get("ok"))
            except Exception as e:
                print(f"[FAIL] ON rate: {type(e).__name__}: {e}", file=sys.stderr)
                total_ok = False
    else:
        print("[WARN] Không có data/market_latest.json để đẩy.", file=sys.stderr)

    return 0 if total_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
