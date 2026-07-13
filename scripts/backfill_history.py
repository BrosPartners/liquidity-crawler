"""Backfill lịch sử lãi suất huy động 2021–nay từ Wayback Machine.

Nguồn: thoibaonganhang.vn/lai-suat (archived monthly).
Chạy 1 lần từ GitHub Actions (archive.org không bị block ở US/EU servers).

Usage:
    python scripts/backfill_history.py
    python scripts/backfill_history.py --from 2021-01 --to 2024-12
    python scripts/backfill_history.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import sys
import time
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.schema import RateRow
from core.normalize import parse_term, parse_rate

DATA_DIR = os.path.join(_ROOT, "data")
HISTORY = os.path.join(DATA_DIR, "history.csv")

# ── Constants ──────────────────────────────────────────────────────────────
CDX_API = "https://web.archive.org/cdx/search/cdx"
WB_BASE = "https://web.archive.org/web"
TBNH_URL = "https://thoibaonganhang.vn/lai-suat"

BANK_NAME_MAP = {
    "vietcombank":  "VCB",
    "bidv":         "BID",
    "vietinbank":   "CTG",
    "agribank":     "AGR",
    "acb":          "ACB",
    "sacombank":    "STB",
    "techcombank":  "TCB",
    "vpbank":       "VPB",
    "mb bank":      "MBB",
    "mbbank":       "MBB",
    "hdbank":       "HDB",
    "tpbank":       "TPB",
    "lpbank":       "LPB",
    "eximbank":     "EIB",
    "vib":          "VIB",
    "msb":          "MSB",
    "ocb":          "OCB",
    "ncb":          "NCB",
    "pgbank":       "PGB",
    "seabank":      "SSB",
    "vikki bank":   "VKK",
    "vikki":        "VKK",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
}


# ── Wayback CDX API ────────────────────────────────────────────────────────
def get_monthly_snapshots(client: httpx.Client, from_ym: str, to_ym: str) -> List[tuple]:
    """Trả về list (timestamp, wayback_url) mỗi tháng có snapshot của TBNH."""
    params = {
        "url": TBNH_URL,
        "output": "json",
        "collapse": "timestamp:6",   # 1 snapshot/tháng
        "from": from_ym.replace("-", ""),
        "to": to_ym.replace("-", "") + "31235959",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "limit": "300",
    }
    try:
        r = client.get(CDX_API, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        print(f"[ERR] CDX API: {e}", file=sys.stderr)
        return []

    if not rows or len(rows) < 2:
        return []

    # rows[0] = header ["timestamp","original","statuscode"]
    results = []
    for row in rows[1:]:
        ts, orig, sc = row
        wb_url = f"{WB_BASE}/{ts}id_/{orig}"
        results.append((ts, wb_url))
    return results


# ── HTML Parser ────────────────────────────────────────────────────────────
def _bank_code(name: str) -> Optional[str]:
    key = name.lower().strip()
    for k, v in BANK_NAME_MAP.items():
        if k in key:
            return v
    return None


def parse_tbnh_html(html: str, snapshot_date: str) -> List[RateRow]:
    """Parse bảng lãi suất từ thoibaonganhang.vn/lai-suat HTML."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return []

    rows: List[RateRow] = []
    now = _dt.datetime.now().isoformat(timespec="seconds")

    for table in tables:
        tr_list = table.find_all("tr")
        if len(tr_list) < 3:
            continue

        # Tìm header row có "Ngân hàng"
        header_idx = None
        col_terms = []
        for i, tr in enumerate(tr_list):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if cells and any("ngân hàng" in c.lower() for c in cells):
                header_idx = i
                # Parse term headers (skip first col = bank name)
                for h in cells[1:]:
                    term = parse_term(h)
                    col_terms.append(term)
                break

        if header_idx is None or not col_terms:
            continue

        seen: set = set()
        for tr in tr_list[header_idx + 1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not cells or len(cells) < 2:
                continue
            bank_name_raw = cells[0]
            code = _bank_code(bank_name_raw)
            if code is None:
                continue

            bank_name = bank_name_raw.strip()
            for j, term in enumerate(col_terms):
                if term is None:
                    continue
                idx = j + 1
                if idx >= len(cells):
                    continue
                raw = cells[idx]
                # Comma-decimal: "5,90" → "5.90"
                raw_normalized = raw.replace(",", ".")
                rate = parse_rate(raw_normalized)
                if rate is None:
                    continue

                r = RateRow(
                    date=snapshot_date,
                    bank_code=code,
                    bank_name=bank_name,
                    term=term,
                    rate=rate,
                    product="quay",
                    method="cuoi_ky",
                    currency="VND",
                    source_url=TBNH_URL,
                    crawled_at=now,
                )
                k = r.key() + "|" + snapshot_date
                if k not in seen:
                    seen.add(k)
                    rows.append(r)

    return rows


# ── CSV helpers ────────────────────────────────────────────────────────────
def _load_existing_keys() -> set:
    """Load existing (bank_code|term|product|method|currency|date) keys to avoid duplication."""
    keys = set()
    if not os.path.exists(HISTORY):
        return keys
    with open(HISTORY, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            k = f"{row.get('bank_code')}|{row.get('term')}|{row.get('product')}|{row.get('method')}|{row.get('currency')}|{row.get('date')}"
            keys.add(k)
    return keys


def _append_rows(rows: List[RateRow]) -> int:
    """Ghi thêm rows vào history.csv. Trả về số dòng thực sự ghi."""
    if not rows:
        return 0
    os.makedirs(DATA_DIR, exist_ok=True)
    _FIELDS = list(RateRow.__annotations__.keys())
    new_file = not os.path.exists(HISTORY)
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r.to_dict())
    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_ym", default="2021-01",
                    help="Tháng bắt đầu YYYY-MM (default: 2021-01)")
    ap.add_argument("--to", dest="to_ym",
                    default=_dt.date.today().strftime("%Y-%m"),
                    help="Tháng kết thúc YYYY-MM (default: tháng hiện tại)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chỉ in ra, không ghi file")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="Delay giữa các request (giây, default: 2.0)")
    args = ap.parse_args()

    print(f"Backfill {args.from_ym} → {args.to_ym}  dry_run={args.dry_run}")

    existing_keys = _load_existing_keys()
    print(f"Existing history entries: {len(existing_keys)}")

    total_written = 0
    total_skipped = 0

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        # 1. Lấy danh sách snapshots từ CDX
        print("Querying Wayback CDX API...")
        snapshots = get_monthly_snapshots(client, args.from_ym, args.to_ym)
        print(f"Found {len(snapshots)} monthly snapshots")

        if not snapshots:
            print("[WARN] Không tìm thấy snapshot nào. Kiểm tra kết nối tới archive.org")
            return 1

        # 2. Crawl từng snapshot
        for i, (ts, wb_url) in enumerate(snapshots):
            date_str = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            print(f"[{i+1:3}/{len(snapshots)}] {date_str}  {wb_url[-60:]}")

            try:
                r = client.get(wb_url, timeout=20)
                if r.status_code != 200:
                    print(f"  → HTTP {r.status_code}, skip")
                    continue
                html = r.text
            except Exception as e:
                print(f"  → ERR fetch: {e}")
                continue

            parsed = parse_tbnh_html(html, date_str)
            if not parsed:
                print(f"  → 0 rows parsed (page may have changed layout)")
                continue

            # Dedup với existing
            new_rows = []
            for row in parsed:
                k = f"{row.bank_code}|{row.term}|{row.product}|{row.method}|{row.currency}|{row.date}"
                if k not in existing_keys:
                    new_rows.append(row)
                    existing_keys.add(k)
                else:
                    total_skipped += 1

            bank_summary = {}
            for row in new_rows:
                bank_summary.setdefault(row.bank_code, 0)
                bank_summary[row.bank_code] += 1
            print(f"  → {len(new_rows)} new rows  {bank_summary}  (skip={total_skipped})")

            if not args.dry_run and new_rows:
                _append_rows(new_rows)
                total_written += len(new_rows)

            time.sleep(args.delay)

    print(f"\nDone. Written={total_written}  Skipped={total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
