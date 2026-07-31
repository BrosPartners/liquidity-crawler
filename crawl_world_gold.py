"""Crawl giá vàng thế giới (USD/oz) + quy đổi VND/lượng từ yfinance.

Nguồn giá vàng chính là file Telegram (gold_history.csv) nhưng cột vàng thế giới
đôi lúc trễ vài ngày so với SJC. Ở đây lấy GC=F (vàng COMEX, ~spot) + VND=X
(USD/VND) từ Yahoo để web NỐI ĐUÔI world_gold_usd/vnd cho các ngày file vàng
chưa có (web hiệu chỉnh mức để liền mạch).

world_gold_vnd = usd/oz × 1.20565 (oz→lượng) × usd_vnd.

    python crawl_world_gold.py   -> data/world_gold.csv (date, world_gold_usd, world_gold_vnd)
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import sys

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(_ROOT, "data", "world_gold.csv")
_OZ_PER_LUONG = 1.20565   # 37.5g / 31.1035g
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}


def _yahoo(client, symbol: str) -> "dict[str, float]":
    r = client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                   params={"range": "3mo", "interval": "1d"})
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    cl = res["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%d")
        out[d] = c
    return out


def main() -> int:
    with httpx.Client(headers=_UA, timeout=30, follow_redirects=True) as c:
        try:
            gold = _yahoo(c, "GC=F")
            vnd = _yahoo(c, "VND=X")
        except Exception as e:
            print(f"[FAIL] yfinance: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    if not gold or not vnd:
        print("[WARN] yfinance rỗng.", file=sys.stderr)
        return 1

    vnd_dates = sorted(vnd)
    rows = []
    for d in sorted(gold):
        # forward-fill USD/VND: lấy điểm VND=X gần nhất <= d
        vd = [x for x in vnd_dates if x <= d]
        if not vd:
            continue
        usdvnd = vnd[vd[-1]]
        usd = round(gold[d], 2)
        vnd_luong = round(usd * _OZ_PER_LUONG * usdvnd)
        rows.append((d, usd, vnd_luong))

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "world_gold_usd", "world_gold_vnd"])
        w.writerows(rows)
    print(f"[OK]   world_gold.csv: {len(rows)} ngày ({rows[0][0]} -> {rows[-1][0]}), "
          f"cuối usd={rows[-1][1]} vnd={rows[-1][2]:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
