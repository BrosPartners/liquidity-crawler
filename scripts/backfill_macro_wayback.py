"""Backfill khoảng trống CPI & cán cân thương mại từ Wayback Machine (1 lần).

IMF/IFS trễ (~2025-03), VietnamBiz chỉ có latest -> giữa 2 nguồn có khoảng trống
(vd 2025-04 → 2026-05). Mỗi snapshot Wayback của data.vietnambiz.vn/macro-economic
lưu lại giá trị "hiện tại" tại thời điểm đó -> quét snapshot hằng tháng để dựng lại
các điểm tháng đã mất, MERGE vào data/macro_history.csv (upsert theo (date,key)).

Chỉ backfill 2 key được nối đuôi trong crawl_macro.py: cpi_yoy, trade_balance.
Chạy trên GitHub Actions (Wayback hay timeout ở mạng nội bộ VN).

    python scripts/backfill_macro_wayback.py [--from 2025-04] [--to 2026-06]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(_ROOT, "data", "macro_history.csv")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
_CDX = "http://web.archive.org/cdx/search/cdx"
# mỗi target: (url cần archive, {title VietnamBiz -> key trong macro_history})
_TARGETS = [
    ("data.vietnambiz.vn/macro-economic", {
        "Tăng trưởng CPI (YoY)": "cpi_yoy",
        "Cán cân thương mại (Triệu USD)": "trade_balance",
        "IIP (YoY)": "iip_yoy",
        "Xuất khẩu (YoY)": "exports_yoy",
        "Nhập khẩu (YoY)": "imports_yoy",
    }),
    ("data.vietnambiz.vn/currency-interest-rate", {
        "Dự trữ ngoại hối (Triệu USD)": "reserves",
    }),
]


def _period(ngay: str):
    m = re.search(r"Tháng (\d{1,2})/(\d{4})", str(ngay or ""))
    return f"{m.group(2)}-{int(m.group(1)):02d}" if m else None


def _parse_snapshot(html: str, want: dict) -> dict:
    """{key: (period 'YYYY-MM', value)} từ 1 trang archived."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    raw: list = []

    def walk(o):
        if isinstance(o, dict):
            if "value" in o and (set(o) & {"title", "name", "label"}):
                raw.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data.get("props", {}))
    out = {}
    for o in raw:
        t = o.get("title") or o.get("name") or o.get("label")
        key = want.get(t)
        if not key or key in out:
            continue
        per = _period(o.get("ngay"))
        if not per:
            continue
        try:
            out[key] = (per, round(float(o.get("value")), 4))
        except (TypeError, ValueError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2025-01")
    ap.add_argument("--to", dest="to", default="2026-12")
    args = ap.parse_args()
    frm = args.frm.replace("-", "") + "01"
    to = args.to.replace("-", "") + "31"

    found: dict = {}   # (period, key) -> value  (snapshot mới hơn ghi đè)
    with httpx.Client(headers=_UA, timeout=60, follow_redirects=True) as c:
        for target, want in _TARGETS:
            r = c.get(_CDX, params={"url": target, "output": "json", "from": frm, "to": to,
                                    "collapse": "timestamp:6", "fl": "timestamp,statuscode",
                                    "filter": "statuscode:200"})
            r.raise_for_status()
            rows = r.json()
            snaps = [x[0] for x in rows[1:]] if len(rows) > 1 else []
            print(f"[cdx] {target}: {len(snaps)} snapshot")
            for ts in snaps:
                try:
                    html = c.get(f"http://web.archive.org/web/{ts}id_/https://{target}").text
                    pts = _parse_snapshot(html, want)
                except Exception as e:
                    print(f"  [skip] {ts}: {type(e).__name__}", file=sys.stderr)
                    continue
                for key, (per, val) in pts.items():
                    found[(per, key)] = val
                if pts:
                    print(f"  [{ts[:8]}] " + ", ".join(f"{k}={v[1]}({v[0]})" for k, v in pts.items()))
                time.sleep(0.4)

    if not found:
        print("[WARN] không dựng được điểm nào từ Wayback.", file=sys.stderr)
        return 1

    # MERGE upsert vào macro_history.csv
    existing = {}
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[(row["date"], row["series_key"])] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue
    added = 0
    for (per, key), val in found.items():
        k = (f"{per}-01", key)
        if k not in existing:
            added += 1
        existing[k] = val
    rows_out = sorted((d, key, v) for (d, key), v in existing.items())
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        w.writerows(rows_out)
    print(f"[OK] backfill {len(found)} điểm ({added} mới) -> macro_history.csv "
          f"({len(rows_out)} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
