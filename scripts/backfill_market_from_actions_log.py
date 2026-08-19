"""Backfill market_history.csv từ log các lần chạy GitHub Actions đã qua.

Bug ở crawl_market.py (write_json() ghi đè market_latest.json TRƯỚC khi
append_history_on_change() so sánh) khiến mọi series bị kẹt ở đúng 1 dòng
duy nhất từ baseline (04/07/2026) đến khi fix. Nhưng MỖI LẦN CHẠY vẫn crawl
đúng giá trị mới và IN RA LOG (dòng "[OK]   <key>   <value>   <unit>   (<as_of>)"),
chỉ là không ghi được vào history — log của Actions vẫn giữ lại giá trị đó.

Script này quét log của các run "crawl-lai-suat" đã thành công, trích lại
các dòng "[OK]" của bước "Crawl data thị trường", dựng lại MarketRow cho
từng ngày, rồi MERGE (upsert theo (date, series_key), không ghi đè điểm đã
có) vào data/market_history.csv.

Yêu cầu: gh CLI đã đăng nhập (gh auth status), quyền đọc repo.

    python scripts/backfill_market_from_actions_log.py --repo BrosPartners/liquidity-crawler
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys

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

# series_key -> (title gốc, category, unit) — đảo ngược SERIES_MAP
_BY_KEY = {key: (title, category, unit) for title, (key, category, unit) in SERIES_MAP.items()}

_LOG_LINE = re.compile(
    r"\[OK\]\s+(?P<key>\S+)\s+(?P<value>-?\d+(?:\.\d+)?)\s+(?P<unit>\S+)\s+\((?P<as_of>[^)]*)\)"
)


def _list_runs(repo: str) -> list[dict]:
    out = subprocess.run(
        ["gh", "run", "list", "--workflow=cron.yml", "--repo", repo, "--limit", "300",
         "--json", "databaseId,createdAt,conclusion"],
        capture_output=True, check=True,
    )
    runs = json.loads(out.stdout.decode("utf-8", errors="replace"))
    return sorted(
        (r for r in runs if r.get("conclusion") == "success"),
        key=lambda r: r["createdAt"],
    )


def _run_log(repo: str, run_id: int) -> str:
    out = subprocess.run(
        ["gh", "run", "view", str(run_id), "--repo", repo, "--log"],
        capture_output=True, check=True,
    )
    return out.stdout.decode("utf-8", errors="replace")


def _parse_run(log: str, run_date: str) -> list[MarketRow]:
    rows = []
    seen = set()
    for line in log.splitlines():
        m = _LOG_LINE.search(line)
        if not m:
            continue
        key = m.group("key")
        if key not in _BY_KEY or key in seen:
            continue
        title, category, unit = _BY_KEY[key]
        try:
            val = round(float(m.group("value")), 4)
        except ValueError:
            continue
        seen.add(key)
        rows.append(MarketRow(
            date=run_date, series_key=key, label=title, value=val, unit=unit,
            category=category, as_of=m.group("as_of"),
            source_url="https://data.vietnambiz.vn/currency-interest-rate", crawled_at="",
        ))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="BrosPartners/liquidity-crawler")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    existing: dict[tuple[str, str], dict] = {}
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[(row["date"], row["series_key"])] = row

    runs = _list_runs(args.repo)
    print(f"[gh] {len(runs)} run thành công (từ {runs[0]['createdAt']} đến {runs[-1]['createdAt']})")

    added = 0
    seen_dates = set()
    for r in runs:
        run_date = r["createdAt"][:10]
        if run_date in seen_dates:
            continue  # 1 điểm/ngày là đủ, bỏ qua các lần chạy dispatch thêm trong ngày
        try:
            log = _run_log(args.repo, r["databaseId"])
        except subprocess.CalledProcessError as e:
            print(f"  [skip] run {r['databaseId']}: {e}", file=sys.stderr)
            continue
        rows = _parse_run(log, run_date)
        if not rows:
            continue
        seen_dates.add(run_date)
        new_here = 0
        for mrow in rows:
            k = (mrow.date, mrow.series_key)
            if k in existing:
                continue
            existing[k] = mrow.to_dict()
            new_here += 1
        added += new_here
        print(f"  [{run_date}] run {r['databaseId']}: {len(rows)} series, {new_here} mới")

    if args.dry_run:
        print(f"[DRY-RUN] sẽ thêm {added} dòng — không ghi file.")
        return 0

    rows_out = sorted(existing.values(), key=lambda r: (r["date"], r["series_key"]))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows_out)
    print(f"[OK] backfill {added} dòng mới -> market_history.csv ({len(rows_out)} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
