"""Đọc data GỐC cho dashboard TỪ Google Sheet (các tab Auto-* + ON rate).

Dùng bởi build_static.py để nhúng. Sheet là nguồn sự thật; nếu 1 tab chưa tồn
tại/đọc lỗi thì trả None để build_static fallback về file cục bộ.
"""
from __future__ import annotations

import csv
import io
import json
from typing import List, Optional, Tuple

from core.sheet_client import SheetConfig, read_tab_csv

DEP_TAB = "Auto - Deposit"
MKT_TAB = "Auto - Market"
ON_TAB = "ON rate"
DEPGROUP_TAB = "Dep rates - Group"
BOND_TAB = "VN-US 10y bond yield"


def bond_from_sheet(cfg: "SheetConfig") -> Optional[str]:
    """Lợi suất TPCP 10Y VN & US từ tab 'VN-US 10y bond yield'.

    -> history CSV long (date, series_key, value) với vn_10y / us_10y / bond_gap
    (gap = VN - US). Trả None nếu tab không có/đọc lỗi.
    """
    try:
        rows = _rows(read_tab_csv(cfg, BOND_TAB))
    except Exception:
        return None
    if not rows:
        return None
    head = rows[0]
    try:
        di, vi, ui = head.index("date"), head.index("VN"), head.index("US")
    except ValueError:
        return None

    def num(x):
        try:
            return float(str(x).replace(",", "").strip())
        except Exception:
            return None

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "series_key", "value"])
    n = 0
    for r in rows[1:]:
        if len(r) <= max(di, vi, ui):
            continue
        d = _norm_date(r[di])
        if not d or len(d) != 10 or not d[:4].isdigit():
            continue
        vn, us = num(r[vi]), num(r[ui])
        if vn is not None:
            w.writerow([d, "vn_10y", vn]); n += 1
        if us is not None:
            w.writerow([d, "us_10y", us]); n += 1
        if vn is not None and us is not None:
            w.writerow([d, "bond_gap", round(vn - us, 4)]); n += 1
    return buf.getvalue() if n else None

# Thứ tự 18 bank trong tab 'Dep rates - Group' (khối 12M cột 10-27, 3M cột 30-47)
BANKS18 = ["VCB", "CTG", "BID", "VPB", "TCB", "MBB", "ACB", "STB", "SHB",
           "HDB", "TPB", "VIB", "LPB", "EIB", "SSB", "NAB", "MSB", "OCB"]
DEP12_COL0 = 10   # cột VCB của khối 12M
DEP3_COL0 = 30    # cột VCB của khối 3M


def _rows(csv_text: str) -> List[List[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def _norm_date(s: str) -> str:
    """'07/04/2026' hoặc '7/4/26' -> '2026-07-04'; giữ nguyên nếu đã ISO."""
    s = (s or "").strip()
    if not s:
        return s
    if "-" in s and len(s.split("-")[0]) == 4:
        return s
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            import datetime as dt
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s


def _histgroup_rows(cfg: SheetConfig) -> List[list]:
    """Parse lịch sử 12M/3M của 18 bank từ tab 'Dep rates - Group' (2019→nay).

    -> list [date, bank_code, bank_name, term, rate, product].
    Emit cho CẢ 'quay' và 'online' để chart diễn biến hiện lịch sử dù chọn kênh nào
    (nguồn gốc là lãi suất niêm yết, không tách quầy/online). Không đưa vào latest.
    """
    try:
        rows = _rows(read_tab_csv(cfg, DEPGROUP_TAB))
    except Exception:
        return []
    out = []
    for r in rows[1:]:
        if len(r) <= DEP3_COL0 + len(BANKS18):
            # dòng ngắn (thiếu khối 3M) vẫn xử lý phần có; pad cho an toàn
            r = list(r) + [""] * (DEP3_COL0 + len(BANKS18) - len(r) + 1)
        d = _norm_date(r[3]) if len(r) > 3 else ""
        if not d or len(d) != 10 or not d[:4].isdigit():
            continue
        for i, bank in enumerate(BANKS18):
            for col0, term in ((DEP12_COL0, "12M"), (DEP3_COL0, "3M")):
                c = col0 + i
                if c >= len(r):
                    continue
                raw = str(r[c]).replace("%", "").replace(",", "").strip()
                try:
                    v = float(raw)
                except Exception:
                    continue
                if v <= 0 or v > 25:      # loại 0 và giá trị rác
                    continue
                out.append([d, bank, bank, term, v, "quay"])
                out.append([d, bank, bank, term, v, "online"])
    return out


def deposit_from_sheet(cfg: SheetConfig) -> Optional[Tuple[str, str]]:
    """-> (latest_json_str, history_csv_str) hoặc None."""
    try:
        text = read_tab_csv(cfg, DEP_TAB)
    except Exception:
        return None
    rows = _rows(text)
    if not rows or "bank_code" not in rows[0]:
        return None
    head = rows[0]
    idx = {c: head.index(c) for c in head}
    recs = [r for r in rows[1:] if len(r) > idx["rate"] and r[idx["date"]].strip()]
    if not recs:
        return None
    # latest.json từ ngày mới nhất
    dates = sorted({r[idx["date"]] for r in recs})
    last = dates[-1]
    def g(r, c):
        return r[idx[c]] if c in idx and idx[c] < len(r) else ""
    def num(x):
        try:
            return float(x)
        except Exception:
            return None
    latest_rates = []
    for r in recs:
        if r[idx["date"]] != last:
            continue
        latest_rates.append({
            "date": g(r, "date"), "bank_code": g(r, "bank_code"),
            "bank_name": g(r, "bank_name"), "term": g(r, "term"),
            "rate": num(g(r, "rate")), "product": g(r, "product"),
            "source_url": g(r, "source_url"),
        })
    latest = {
        "generated_at": last,
        "count": len(latest_rates),
        "banks": sorted({x["bank_code"] for x in latest_rates}),
        "rates": latest_rates,
    }
    # history.csv: lịch sử 12M/3M (Dep rates - Group, 2019→) + snapshot weekly (Auto - Deposit)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "bank_code", "bank_name", "term", "rate", "product"])
    n_hist = 0
    for row in _histgroup_rows(cfg):
        w.writerow(row)
        n_hist += 1
    for r in recs:
        w.writerow([g(r, "date"), g(r, "bank_code"), g(r, "bank_name"),
                    g(r, "term"), g(r, "rate"), g(r, "product")])
    if n_hist:
        print(f"[sheet] deposit history: +{n_hist} dòng từ 'Dep rates - Group'")
    return json.dumps(latest, ensure_ascii=False), buf.getvalue()


def _onrate_points(cfg: SheetConfig) -> List[Tuple[str, float]]:
    """[(date_iso, value)] từ tab 'ON rate'."""
    try:
        text = read_tab_csv(cfg, ON_TAB)
    except Exception:
        return []
    out = []
    for r in _rows(text)[1:]:
        if len(r) < 2:
            continue
        d = _norm_date(r[0])
        try:
            v = float(str(r[1]).replace(",", "").strip())
        except Exception:
            continue
        if d:
            out.append((d, v))
    return out


ON_LABEL = "Lãi suất liên ngân hàng qua đêm (ON)"


def assemble_market(cfg: SheetConfig, local_latest: str,
                    local_history: str) -> Optional[Tuple[str, str]]:
    """Ghép market_latest/history cho dashboard, ưu tiên nguồn sheet.

    - Series thị trường (OMO, tỷ giá, tenor...): tab 'Auto - Market' nếu có,
      không thì giữ local (tham số truyền vào).
    - interbank_on: LUÔN thay bằng lịch sử daily từ tab 'ON rate' nếu có.
    Trả None nếu không lấy được gì từ sheet (build_static giữ nguyên local).
    """
    on_pts = _onrate_points(cfg)
    mkt_rows = None
    try:
        rows = _rows(read_tab_csv(cfg, MKT_TAB))
        if rows and "series_key" in rows[0]:
            mkt_rows = rows
    except Exception:
        mkt_rows = None

    if mkt_rows is None and not on_pts:
        return None  # không có gì mới từ sheet

    # Khởi tạo từ local (giữ các series không có trên sheet)
    latest_by_key = {}
    hist_rows: List[list] = []  # [date, series_key, label, value, unit, category]
    try:
        loc = json.loads(local_latest) if local_latest and local_latest != "null" else {}
        for s in loc.get("series", []):
            latest_by_key[s["series_key"]] = dict(s)
    except Exception:
        pass
    if local_history:
        lr = _rows(local_history)
        if lr and "series_key" in lr[0]:
            h = lr[0]; ix = {c: h.index(c) for c in h}
            for r in lr[1:]:
                if len(r) <= ix["value"]:
                    continue
                hist_rows.append([r[ix["date"]], r[ix["series_key"]],
                                  r[ix.get("label", ix["series_key"])] if "label" in ix else "",
                                  r[ix["value"]],
                                  r[ix["unit"]] if "unit" in ix else "",
                                  r[ix["category"]] if "category" in ix else ""])

    # Override bằng Auto - Market
    if mkt_rows is not None:
        head = mkt_rows[0]; idx = {c: head.index(c) for c in head}
        def g(r, c):
            return r[idx[c]] if c in idx and idx[c] < len(r) else ""
        hist_rows = [row for row in hist_rows]  # giữ local trước; Auto-Market thêm/ghi đè theo (date,key)
        seen = {(row[0], row[1]) for row in hist_rows}
        for r in mkt_rows[1:]:
            if len(r) <= idx["value"] or not g(r, "date"):
                continue
            key = g(r, "series_key")
            try:
                val = float(str(g(r, "value")).replace(",", ""))
            except Exception:
                continue
            if (g(r, "date"), key) not in seen:
                hist_rows.append([g(r, "date"), key, g(r, "label"), val, g(r, "unit"), g(r, "category")])
            prev = latest_by_key.get(key)
            if not prev or g(r, "date") >= prev.get("date", ""):
                latest_by_key[key] = {
                    "date": g(r, "date"), "series_key": key, "label": g(r, "label"),
                    "value": val, "unit": g(r, "unit"), "category": g(r, "category"),
                    "as_of": g(r, "as_of"), "source_url": g(r, "source_url"),
                }

    # interbank_on: gộp lịch sử daily tab ON rate + điểm live crawl (local),
    # dedupe theo ngày, latest = ngày mới nhất (tránh lấy nhầm điểm cũ của sheet).
    if on_pts:
        by_date = {}
        for row in hist_rows:               # điểm interbank_on đang có (local)
            if row[1] == "interbank_on":
                try:
                    by_date[row[0]] = float(str(row[3]).replace(",", ""))
                except Exception:
                    pass
        prev_on = latest_by_key.get("interbank_on")
        if prev_on and prev_on.get("date"):
            by_date[prev_on["date"]] = prev_on["value"]
        for d, v in on_pts:                  # tab ON rate (ưu tiên nếu trùng ngày)
            by_date[d] = v
        hist_rows = [row for row in hist_rows if row[1] != "interbank_on"]
        for d in sorted(by_date):
            hist_rows.append([d, "interbank_on", ON_LABEL, by_date[d], "%/năm", "lien_nh"])
        d = max(by_date)
        latest_by_key["interbank_on"] = {
            "date": d, "series_key": "interbank_on", "label": ON_LABEL,
            "value": by_date[d], "unit": "%/năm", "category": "lien_nh", "as_of": d,
            "source_url": "https://docs.google.com/spreadsheets/d/%s" % cfg.sheet_id,
        }

    if not latest_by_key and not hist_rows:
        return None
    latest = {
        "generated_at": max((x.get("date", "") for x in latest_by_key.values()), default=""),
        "count": len(latest_by_key),
        "series": list(latest_by_key.values()),
    }
    hist = io.StringIO()
    hw = csv.writer(hist, lineterminator="\n")
    hw.writerow(["date", "series_key", "label", "value", "unit", "category"])
    for row in hist_rows:
        hw.writerow(row)
    return json.dumps(latest, ensure_ascii=False), hist.getvalue()
