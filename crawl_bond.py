"""Crawl lợi suất TPCP 10Y: US tự động (FRED) + VN từ Google Sheet (carry-forward).

Bối cảnh: nguồn VN 10Y free daily đều bị chặn/không ổn định (investing/HNX/
stooq/TE...). US 10Y thì đổi hằng ngày và tốn công cập nhật tay nhất -> tự động
qua FRED (DGS10, free không cần key). VN 10Y ổn định hơn, team cập nhật định kỳ
vào tab Sheet 'VN-US 10y bond yield'; ở đây giữ VN từ Sheet và CARRY-FORWARD giá
trị cuối cho các ngày sau (tới khi Sheet có số mới thì tự đúng lại).

Ghi data/bond_yield.csv (long: date, series_key, value) với vn_10y / us_10y /
bond_gap (= VN - US). build_static ưu tiên đọc file này (Sheet chỉ là fallback).

    python crawl_bond.py
"""
from __future__ import annotations

import csv
import io
import os
import sys
import datetime as _dt

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from core.sheet_client import load_config          # noqa: E402
from scripts import sheet_source as ss             # noqa: E402

DATA_DIR = os.path.join(_ROOT, "data")
CSV_PATH = os.path.join(DATA_DIR, "bond_yield.csv")
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"  # ^TNX = US 10Y yield
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36")}


def _fetch(url, params, tries=4):
    import time
    last = None
    for i in range(tries):
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                return r
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def fetch_us_yahoo(from_date: str = "2019-01-01") -> dict:
    """{date_iso: yield%} US 10Y từ Yahoo ^TNX (giá đã là %/năm)."""
    d0 = int(_dt.datetime.strptime(from_date, "%Y-%m-%d").timestamp())
    now = int(_dt.datetime.now().timestamp()) + 86400
    r = _fetch(YAHOO_URL, {"period1": d0, "period2": now, "interval": "1d"})
    res = r.json()["chart"]["result"][0]
    ts = res.get("timestamp") or []
    cl = res["indicators"]["quote"][0].get("close") or []
    out = {}
    for t, v in zip(ts, cl):
        if v is None:
            continue
        d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).date().isoformat()
        out[d] = round(float(v), 3)
    return out


def fetch_us_fred(from_date: str = "2019-01-01") -> dict:
    """{date_iso: yield%} US 10Y từ FRED DGS10 (fallback nếu Yahoo lỗi)."""
    r = _fetch(FRED_URL, {"id": "DGS10", "cosd": from_date})
    out = {}
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v and v != "." and len(d) == 10:
            try:
                out[d] = float(v)
            except ValueError:
                pass
    return out


def fetch_us(from_date: str = "2019-01-01") -> dict:
    """US 10Y: thử Yahoo trước, FRED fallback."""
    try:
        d = fetch_us_yahoo(from_date)
        if d:
            print(f"[OK]   US10Y từ Yahoo ^TNX: {len(d)} ngày, tới {max(d)}")
            return d
    except Exception as e:
        print(f"[WARN] Yahoo ^TNX lỗi, thử FRED: {type(e).__name__}: {e}", file=sys.stderr)
    d = fetch_us_fred(from_date)
    print(f"[OK]   US10Y từ FRED DGS10: {len(d)} ngày, tới {max(d) if d else '—'}")
    return d


def _base_from_sheet(cfg) -> tuple[dict, dict]:
    """(vn, us) {date: value} từ tab Sheet 'VN-US 10y bond yield'."""
    vn, us = {}, {}
    long_csv = None
    try:
        long_csv = ss.bond_from_sheet(cfg)
    except Exception as e:
        print(f"[WARN] đọc Sheet bond bỏ qua: {type(e).__name__}: {e}", file=sys.stderr)
    if not long_csv:
        return vn, us
    for row in csv.reader(io.StringIO(long_csv)):
        if len(row) < 3 or row[0] == "date":
            continue
        d, k, v = row[0], row[1], row[2]
        try:
            fv = float(v)
        except ValueError:
            continue
        if k == "vn_10y":
            vn[d] = fv
        elif k == "us_10y":
            us[d] = fv
    return vn, us


def main() -> int:
    cfg = load_config()
    vn, us = _base_from_sheet(cfg)
    print(f"[OK]   Sheet base: VN {len(vn)} ngày (tới {max(vn) if vn else '—'}), "
          f"US {len(us)} ngày (tới {max(us) if us else '—'})")

    # US từ Yahoo/FRED — cập nhật tới nay; ghi đè/bổ sung lên base Sheet.
    try:
        us.update(fetch_us("2019-01-01"))
    except Exception as e:
        print(f"[WARN] US10Y online lỗi (giữ US từ Sheet): {type(e).__name__}: {e}", file=sys.stderr)

    # Carry-forward VN cho mọi ngày (tới khi Sheet có số mới thì tự đúng lại).
    all_dates = sorted(set(vn) | set(us))
    last_vn = None
    rows = []
    n_vn = n_us = n_gap = 0
    for d in all_dates:
        if d in vn:
            last_vn = vn[d]
        v_vn = last_vn
        v_us = us.get(d)
        if v_vn is not None:
            rows.append([d, "vn_10y", v_vn]); n_vn += 1
        if v_us is not None:
            rows.append([d, "us_10y", v_us]); n_us += 1
        if v_vn is not None and v_us is not None:
            rows.append([d, "bond_gap", round(v_vn - v_us, 4)]); n_gap += 1

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        w.writerows(rows)

    last = all_dates[-1] if all_dates else "—"
    print(f"[OK]   bond_yield.csv: {n_vn} vn / {n_us} us / {n_gap} gap, tới {last} "
          f"(VN carry-forward sau {max(vn) if vn else '—'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
