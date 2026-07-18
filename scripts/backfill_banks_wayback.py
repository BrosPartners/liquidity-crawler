"""Backfill lãi suất huy động TỪ WEB TỪNG NGÂN HÀNG qua Wayback Machine.

Khác với scripts/backfill_history.py (dùng 1 trang tổng hợp thoibaonganhang.vn),
script này lấy snapshot web GỐC của từng bank trên web.archive.org rồi parse bằng
đúng logic adapter live (hoặc parser tương đương) → dữ liệu chính chủ.

Giới hạn thực tế (đã khảo sát 2026-07): archive.org chỉ lưu web từng bank rất
thưa (~1 snapshot / 6 tháng, ngày lệch nhau) và KHÔNG replay được trang JS-render
(BID/VIB/SSB/MBB) hay JSON API không được lưu (LPB). Nên chỉ 8 bank khả thi:

    HTML  : ACB, CTG, AGR, OCB, TPB, MSB
    JSON  : VCB, VPB

Kết quả đẩy lên Google Sheet tab 'Auto - Deposit' (upsert theo date+bank+term+
product) — đúng nguồn mà dashboard đọc lịch sử huy động.

Usage:
    python scripts/backfill_banks_wayback.py --dry-run           # chỉ in
    python scripts/backfill_banks_wayback.py                      # in + đẩy Sheet
    python scripts/backfill_banks_wayback.py --from 2026-01 --to 2026-07
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from typing import Callable, Dict, List, Tuple

import httpx
from bs4 import BeautifulSoup

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.normalize import parse_term, parse_rate, norm_text  # noqa: E402
from adapters.acb import Adapter as ACBAdapter                # noqa: E402
from adapters.vietinbank import Adapter as CTGAdapter         # noqa: E402
from adapters.agribank import Adapter as AGRAdapter           # noqa: E402
from adapters.ocb import Adapter as OCBAdapter, URL as OCB_URL  # noqa: E402
from adapters.vietcombank import API_URL as VCB_URL           # noqa: E402
from adapters.vpbank import API_URL as VPB_URL                # noqa: E402
from adapters.tpbank import API_URL as TPB_URL                # noqa: E402
from adapters.msb import URL as MSB_URL                        # noqa: E402

CDX_API = "https://web.archive.org/cdx/search/cdx"
WB_BASE = "https://web.archive.org/web"
_HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36")}

BANK_NAMES = {
    "ACB": "ACB", "CTG": "VietinBank", "AGR": "Agribank", "OCB": "OCB",
    "TPB": "TPBank", "MSB": "MSB", "VCB": "Vietcombank", "VPB": "VPBank",
}

# Term = list[(term, product, rate)]
Extractor = Callable[[str], List[Tuple[str, str, float]]]


# ── Extractors (JSON banks: parser inline; HTML banks: dùng adapter live) ──────
def _vcb(text: str) -> List[Tuple[str, str, float]]:
    data = json.loads(text)
    out = []
    for item in data.get("Data", []):
        if item.get("currencyCode") != "VND":
            continue
        if item.get("tenorType") not in ("Savings", "TimeDeposit", None):
            continue
        term = parse_term(item.get("tenorDisplay") or item.get("tenor") or "")
        if term is None:
            continue
        rr = item.get("rates")
        rate = round(float(rr) * 100, 4) if rr is not None else None
        if rate is None or not (0 < rate <= 15):
            continue
        out.append((term, "quay", rate))
    return out


def _vpb(text: str) -> List[Tuple[str, str, float]]:
    p = json.loads(text)
    cols, data = p.get("columns", []), p.get("data", [])
    if not cols or not data:
        return []
    row = data[0]
    out = []
    for i, c in enumerate(cols):
        term = parse_term(c)
        if term is None or i >= len(row):
            continue
        v = row[i]
        if not isinstance(v, (int, float)) or v <= 0 or v > 15:
            continue
        out.append((term, "quay", float(v)))
    return out


def _tpb(html: str) -> List[Tuple[str, str, float]]:
    soup = BeautifulSoup(html, "lxml")
    tbl = soup.find("table")
    if not tbl:
        return []
    trs = tbl.find_all("tr")
    if not trs:
        return []
    header = [c.get_text(" ", strip=True) for c in trs[0].find_all(["td", "th"])]
    col_map = {}
    for i, h in enumerate(header):
        ht = norm_text(h)
        if "ien tu" in ht:
            col_map[i] = "online"
        elif "cuoi ky" in ht:
            col_map[i] = "quay"
    if not col_map:
        return []
    out = []
    for tr in trs[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        term = parse_term(cells[0])
        if term is None:
            continue
        for i, prod in col_map.items():
            if i >= len(cells):
                continue
            rate = parse_rate(cells[i])
            if rate:
                out.append((term, prod, rate))
    return out


def _msb(html: str) -> List[Tuple[str, str, float]]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for div in soup.select("div.msb-saving-rate-table"):
        raw = div.get("data-config")
        if not raw:
            continue
        try:
            cfg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        table = cfg.get("ratesTableVND") or {}
        for fk, prod in (("tai_quay", "quay"), ("truc_tuyen", "online")):
            for e in table.get(fk, []):
                term = parse_term(e.get("ky_han", ""))
                if term is None:
                    continue
                rate = None
                for k in ("LAI_SUAT_CAO_NHAT", "ROT_GOC_TUNG_PHAN", "HOP_DONG_TIEN_GUI"):
                    if e.get(k) is not None:
                        rate = e[k]
                        break
                if rate is None:
                    continue
                try:
                    rate = round(float(rate), 4)
                except (TypeError, ValueError):
                    continue
                if not (0 < rate <= 15):
                    continue
                out.append((term, prod, rate))
    return out


# (bank_code, wayback_url, extractor)
BANKS: List[Tuple[str, str, Extractor]] = [
    ("ACB", ACBAdapter.url, ACBAdapter().parse_html),
    ("CTG", CTGAdapter.url, CTGAdapter().parse_html),
    ("AGR", AGRAdapter.url, AGRAdapter().parse_html),
    ("OCB", OCB_URL, OCBAdapter()._parse),
    ("TPB", TPB_URL, _tpb),
    ("MSB", MSB_URL, _msb),
    ("VCB", VCB_URL, _vcb),
    ("VPB", VPB_URL, _vpb),
]


# ── Wayback helpers ────────────────────────────────────────────────────────
def _get(client: httpx.Client, url: str, tries: int = 4, timeout: int = 60):
    last = None
    for i in range(tries):
        try:
            return client.get(url, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def snapshots(client: httpx.Client, url: str, frm: str, to: str) -> List[str]:
    """Trả list timestamp (YYYYMMDDhhmmss), tối đa 1/ngày."""
    r = _get(client, CDX_API + "?" + _qs({
        "url": url, "output": "json", "from": frm.replace("-", ""),
        "to": to.replace("-", "") + "31", "fl": "timestamp",
        "filter": "statuscode:200", "collapse": "timestamp:8", "limit": "50",
    }))
    rows = r.json()
    return [x[0] for x in rows[1:]] if len(rows) > 1 else []


def _qs(d: dict) -> str:
    from urllib.parse import urlencode
    return urlencode(d)


def _mirror_products(triples: List[Tuple[str, str, float]]) -> List[Tuple[str, str, float]]:
    """Đảm bảo mỗi (term) có cả 'quay' và 'online' (nhân bản nếu chỉ 1 kênh) —
    lãi suất niêm yết, khớp quy ước tab 'Dep rates - Group' để chart hiện dù chọn
    kênh nào. Nếu bank vốn có cả 2 kênh khác nhau thì giữ nguyên."""
    by_term: Dict[str, Dict[str, float]] = {}
    for term, prod, rate in triples:
        by_term.setdefault(term, {})[prod] = rate
    out = []
    for term, pm in by_term.items():
        if "quay" not in pm and "online" in pm:
            pm["quay"] = pm["online"]
        if "online" not in pm and "quay" in pm:
            pm["online"] = pm["quay"]
        for prod, rate in pm.items():
            out.append((term, prod, rate))
    return out


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", default="2026-01")
    ap.add_argument("--to", dest="to", default="2026-07")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in, không đẩy Sheet")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    print(f"Backfill web từng bank qua Wayback: {args.frm} → {args.to}\n")

    all_rows: List[list] = []   # [date, bank_code, bank_name, term, rate, product, source_url]
    client = httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=60)

    for code, url, extract in BANKS:
        try:
            ts_list = snapshots(client, url, args.frm, args.to)
        except Exception as e:
            print(f"[ERR ] {code}: CDX {type(e).__name__}: {e}")
            continue
        if not ts_list:
            print(f"[----] {code}: không có snapshot")
            continue

        bank_total = 0
        for ts in ts_list:
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            wb = f"{WB_BASE}/{ts}id_/{url}"
            try:
                text = _get(client, wb).text
                triples = extract(text)
            except Exception as e:
                print(f"[warn] {code} {date}: {type(e).__name__}: {e}")
                continue
            triples = _mirror_products(triples)
            if not triples:
                print(f"[warn] {code} {date}: 0 dòng parse được")
                continue
            for term, prod, rate in triples:
                all_rows.append([date, code, BANK_NAMES[code], term, rate, prod, url])
            bank_total += len(triples)
            time.sleep(args.delay)
        print(f"[ OK ] {code}: {bank_total} dòng từ {len(ts_list)} snapshot "
              f"({', '.join(f'{t[4:6]}/{t[6:8]}' for t in ts_list)})")

    print(f"\nTổng: {len(all_rows)} dòng từ {len({r[1] for r in all_rows})} bank.")
    if not all_rows:
        return 1

    if args.dry_run:
        print("(dry-run — không đẩy Sheet)")
        return 0

    # Đẩy Sheet 'Auto - Deposit' (upsert theo date+bank+term+product)
    from core.sheet_client import load_config, push_rows
    cfg = load_config()
    if not cfg.can_push:
        print("[SKIP] chưa cấu hình config.json để đẩy Sheet.", file=sys.stderr)
        return 0
    header = ["date", "bank_code", "bank_name", "term", "rate", "product", "source_url"]
    resp = push_rows(cfg, "Auto - Deposit", all_rows, header=header, key_cols=[0, 1, 3, 5])
    print(f"[Sheet] Auto - Deposit: {resp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
