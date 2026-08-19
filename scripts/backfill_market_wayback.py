"""Backfill khoảng trống market_history.csv (lãi suất liên NH, điều hành SBV,
huy động, tỷ giá, tăng trưởng...) từ Wayback Machine.

Bug ở crawl_market.py (write_json() ghi đè market_latest.json TRƯỚC khi
append_history_on_change() so sánh) khiến mọi series bị kẹt ở đúng 1 dòng
duy nhất từ lần chạy đầu tiên (04/07/2026) đến khi fix (xem commit sửa
crawl_market.py). Mỗi snapshot Wayback của data.vietnambiz.vn/currency-
interest-rate lưu lại giá trị "hiện tại" tại thời điểm đó -> quét snapshot
trong khoảng bị mất để dựng lại các điểm đã bỏ lỡ, MERGE (upsert theo
(date, series_key)) vào data/market_history.csv.

    python scripts/backfill_market_wayback.py [--from 20260704] [--to 20260819]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Optional

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.market_schema import SERIES_MAP, MarketRow  # noqa: E402

CSV_PATH = os.path.join(_ROOT, "data", "market_history.csv")
_FIELDS = list(MarketRow.__annotations__.keys())

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
_CDX = "http://web.archive.org/cdx/search/cdx"
_TARGET = "data.vietnambiz.vn/currency-interest-rate"


def _walk(o, out):
    if isinstance(o, dict):
        keys = set(o.keys())
        if "value" in keys and (keys & {"title", "name", "label"}):
            out.append(o)
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


def _to_date(ngay: str) -> Optional[str]:
    """'Ngày 03/07/2026' -> '2026-07-03'; 'Tháng 07/2026' -> '2026-07-01'."""
    s = str(ngay or "")
    m = re.search(r"Ngày (\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"Tháng (\d{1,2})/(\d{4})", s)
    if m:
        mo, y = m.groups()
        return f"{y}-{int(mo):02d}-01"
    return None


def _parse_snapshot(html: str) -> list[MarketRow]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    raw: list = []
    _walk(data.get("props", {}), raw)

    out = []
    seen = set()
    for o in raw:
        title = o.get("title") or o.get("name") or o.get("label")
        if title not in SERIES_MAP:
            continue
        key, category, unit = SERIES_MAP[title]
        if key in seen:
            continue
        date = _to_date(o.get("ngay"))
        if not date:
            continue
        try:
            val = round(float(o.get("value")), 4)
        except (TypeError, ValueError):
            continue
        seen.add(key)
        out.append(MarketRow(
            date=date, series_key=key, label=title, value=val, unit=unit,
            category=category, as_of=str(o.get("ngay") or ""),
            source_url=f"https://{_TARGET}", crawled_at="",
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="20260704")
    ap.add_argument("--to", dest="to", default="20261231")
    args = ap.parse_args()

    found: dict[tuple[str, str], MarketRow] = {}
    with httpx.Client(headers=_UA, timeout=60, follow_redirects=True) as c:
        r = c.get(_CDX, params={"url": _TARGET, "output": "json", "from": args.frm, "to": args.to,
                                 "collapse": "timestamp:8", "fl": "timestamp,statuscode",
                                 "filter": "statuscode:200"})
        r.raise_for_status()
        rows = r.json()
        snaps = [x[0] for x in rows[1:]] if len(rows) > 1 else []
        print(f"[cdx] {_TARGET}: {len(snaps)} snapshot")
        for ts in snaps:
            try:
                html = c.get(f"http://web.archive.org/web/{ts}id_/https://{_TARGET}").text
                pts = _parse_snapshot(html)
            except Exception as e:
                print(f"  [skip] {ts}: {type(e).__name__}", file=sys.stderr)
                continue
            for mrow in pts:
                found[(mrow.date, mrow.series_key)] = mrow
            if pts:
                print(f"  [{ts[:8]}] " + ", ".join(f"{r.series_key}={r.value}({r.date})" for r in pts))
            time.sleep(0.4)

    if not found:
        print("[WARN] không dựng được điểm nào từ Wayback.", file=sys.stderr)
        return 1

    existing: dict[tuple[str, str], dict] = {}
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[(row["date"], row["series_key"])] = row

    added = 0
    for k, mrow in found.items():
        if k not in existing:
            added += 1
        existing[k] = mrow.to_dict()

    rows_out = sorted(existing.values(), key=lambda r: (r["date"], r["series_key"]))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows_out)
    print(f"[OK] backfill {len(found)} điểm ({added} mới) -> market_history.csv "
          f"({len(rows_out)} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
