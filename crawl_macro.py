"""Crawl chỉ tiêu kinh tế vĩ mô Việt Nam -> data/macro_*.

HAI nguồn ghép lại để vừa có LỊCH SỬ SÂU vừa tới THỜI ĐIỂM HIỆN TẠI:

1. DBnomics (proxy free IMF/IFS) — chuỗi tháng dài (2006/2008→) nhưng trễ ~vài tháng.
     cpi_yoy  M.VN.PCPI_PC_CP_A_PT   reserves M.VN.RAFA_USD
     exports  M.VN.TXG_FOB_USD       imports  M.VN.TMG_CIF_USD   iip M.VN.AIP_IX
   IIP/XK/NK là mức tuyệt đối/chỉ số -> TÍNH YoY (so cùng kỳ 12 tháng) để cùng
   thước đo với VietnamBiz, nhờ đó nối đuôi được.
2. VietnamBiz (miễn phí, tới hiện tại T06/2026…):
     data.vietnambiz.vn/macro-economic       — CPI/IIP/XK/NK YoY, FDI, đầu tư công…
     data.vietnambiz.vn/currency-interest-rate — dự trữ ngoại hối (tuyệt đối)
   Chỉ có latest -> KPI + NỐI ĐUÔI vào chuỗi IMF. macro_history.csv MERGE tích luỹ;
   khoảng trống backfill 1 lần bằng scripts/backfill_macro_wayback.py.

Key lưu vào macro_history.csv: cpi_yoy, reserves, trade_balance, iip_yoy,
exports_yoy, imports_yoy.  FDI/đầu tư công/GDP/ngân sách: chỉ KPI (không lịch sử).

    python crawl_macro.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

import httpx

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_ROOT, "data")
CSV_PATH = os.path.join(_DATA, "macro_history.csv")
JSON_PATH = os.path.join(_DATA, "macro_latest.json")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36", "Accept-Language": "vi-VN,vi;q=0.9"}

# ── Nguồn 1: IMF/IFS qua DBnomics ────────────────────────────────────────
_API = "https://api.db.nomics.world/v22/series/"
_IMF = {
    "cpi_yoy":  "IMF/IFS/M.VN.PCPI_PC_CP_A_PT",
    "reserves": "IMF/IFS/M.VN.RAFA_USD",
    "exports":  "IMF/IFS/M.VN.TXG_FOB_USD",
    "imports":  "IMF/IFS/M.VN.TMG_CIF_USD",
    "iip":      "IMF/IFS/M.VN.AIP_IX",
}
# key ĐƯỢC nối đuôi bằng VietnamBiz (cùng thước đo) + tích luỹ theo tháng:
_EXTEND = {"cpi_yoy", "trade_balance", "reserves", "iip_yoy", "exports_yoy", "imports_yoy"}

# ── Nguồn 2: VietnamBiz ──────────────────────────────────────────────────
_VNB_MACRO = "https://data.vietnambiz.vn/macro-economic"
_VNB_MONEY = "https://data.vietnambiz.vn/currency-interest-rate"
# title -> (key, fmt, label). fmt: pct | milusd (÷1000 = tỷ USD)
_VNB = {
    "Tăng trưởng CPI (YoY)":            ("cpi_yoy",         "pct",    "CPI so cùng kỳ (YoY)"),
    "Tỷ lệ lạm phát (Average CPI YoY)": ("inflation_avg",   "pct",    "Lạm phát bình quân"),
    "Tăng trưởng GDP (YoY)":            ("gdp_growth",      "pct",    "Tăng trưởng GDP"),
    "IIP (YoY)":                        ("iip_yoy",         "pct",    "Sản xuất công nghiệp (IIP YoY)"),
    "FDI đăng ký (YoY)":                ("fdi_registered",  "pct",    "FDI đăng ký (YoY)"),
    "FDI thực hiện (YoY)":              ("fdi_realized",    "pct",    "FDI thực hiện (YoY)"),
    "Vốn đầu tư NSNN (YoY)":            ("public_investment", "pct",  "Đầu tư công · vốn NSNN (YoY)"),
    "Xuất khẩu (YoY)":                  ("exports_yoy",     "pct",    "Xuất khẩu (YoY)"),
    "Nhập khẩu (YoY)":                  ("imports_yoy",     "pct",    "Nhập khẩu (YoY)"),
    "Cán cân thương mại (Triệu USD)":   ("trade_balance",   "milusd", "Cán cân thương mại"),
    "Bán lẻ HH&DV (YoY)":              ("retail_yoy",      "pct",    "Bán lẻ HH&DV (YoY)"),
    "Thu ngân sách (YoY)":              ("budget_rev",      "pct",    "Thu ngân sách (YoY)"),
    "Chi ngân sách (YoY)":              ("budget_exp",      "pct",    "Chi ngân sách (YoY)"),
}
_VNB_RESERVES = "Dự trữ ngoại hối (Triệu USD)"   # ở trang currency-interest-rate
_KPI_ORDER = ["cpi_yoy", "inflation_avg", "gdp_growth", "iip_yoy", "fdi_registered",
              "fdi_realized", "public_investment", "exports_yoy", "imports_yoy",
              "trade_balance", "retail_yoy", "reserves", "budget_rev", "budget_exp"]


def _fetch_imf(client, sid):
    r = client.get(_API + sid, params={"observations": "1"})
    r.raise_for_status()
    docs = r.json().get("series", {}).get("docs", [])
    if not docs:
        return []
    doc = docs[0]
    out = []
    for p, v in zip(doc.get("period", []), doc.get("value", [])):
        if v is None or v == "NA":
            continue
        try:
            out.append((p, round(float(v), 4)))
        except (TypeError, ValueError):
            continue
    out.sort()
    return out


def _yoy(pts):
    """[(YYYY-MM, value)] -> [(YYYY-MM, %YoY)] so với cùng tháng năm trước."""
    by = dict(pts)
    out = []
    for p, v in pts:
        y, m = p.split("-")
        prev = f"{int(y) - 1}-{m}"
        base = by.get(prev)
        if base and base != 0:
            out.append((p, round((v / base - 1) * 100, 4)))
    return out


def _period(ngay: str):
    m = re.search(r"Tháng (\d{1,2})/(\d{4})", str(ngay or ""))
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}", f"T{int(m.group(1)):02d}/{m.group(2)}"
    m = re.search(r"Quý (\d)/(\d{4})", str(ngay or ""))
    if m:
        return f"{m.group(2)}-Q{m.group(1)}", f"Q{m.group(1)}/{m.group(2)}"
    m = re.search(r"Năm (\d{4})", str(ngay or ""))
    if m:
        return m.group(1), f"Năm {m.group(1)}"
    return None


def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def _objs(data):
    raw = []

    def walk(o):
        if isinstance(o, dict):
            if "value" in o and (set(o) & {"title", "name", "label"}):
                raw.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk((data or {}).get("props", {}))
    return raw


def fetch_vnb(client) -> dict:
    """key -> {value, prev, period, period_label, label, fmt} (macro + reserves)."""
    out: dict = {}
    # macro-economic
    r = client.get(_VNB_MACRO)
    r.raise_for_status()
    for o in _objs(_next_data(r.text)):
        title = o.get("title") or o.get("name") or o.get("label")
        if title not in _VNB:
            continue
        key, fmt, label = _VNB[title]
        if key in out:
            continue
        pl = _period(o.get("ngay"))
        if not pl:
            continue
        try:
            val = round(float(o.get("value")), 4)
        except (TypeError, ValueError):
            continue
        try:
            prev = round(float(o.get("pre_value")), 4) if o.get("pre_value") is not None else None
        except (TypeError, ValueError):
            prev = None
        out[key] = {"value": val, "prev": prev, "period": pl[0],
                    "period_label": pl[1], "label": label, "fmt": fmt}
    # currency-interest-rate -> reserves (tuyệt đối)
    try:
        r2 = client.get(_VNB_MONEY)
        r2.raise_for_status()
        for o in _objs(_next_data(r2.text)):
            if (o.get("title") or o.get("name") or o.get("label")) == _VNB_RESERVES:
                pl = _period(o.get("ngay"))
                if pl:
                    out["reserves"] = {"value": round(float(o["value"]), 4),
                                       "prev": (round(float(o["pre_value"]), 4)
                                                if o.get("pre_value") is not None else None),
                                       "period": pl[0], "period_label": pl[1],
                                       "label": "Dự trữ ngoại hối", "fmt": "milusd"}
                break
    except Exception as e:
        print(f"[WARN] VNB reserves: {type(e).__name__}: {e}", file=sys.stderr)
    return out


def _read_existing() -> dict:
    ex = {}
    if not os.path.exists(CSV_PATH):
        return ex
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                ex[(row["date"], row["series_key"])] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
    return ex


def main() -> int:
    with httpx.Client(headers=_UA, timeout=45, follow_redirects=True) as c:
        imf_raw = {}
        for key, sid in _IMF.items():
            try:
                imf_raw[key] = _fetch_imf(c, sid)
            except Exception as e:
                print(f"[WARN] IMF {key}: {type(e).__name__}: {e}", file=sys.stderr)
                imf_raw[key] = []
        # chuỗi lưu trữ: cpi_yoy & reserves giữ nguyên; iip/xk/nk -> YoY; trade_balance = xk-nk
        exp = dict(imf_raw.get("exports", []))
        imp = dict(imf_raw.get("imports", []))
        imf = {
            "cpi_yoy": imf_raw.get("cpi_yoy", []),
            "reserves": imf_raw.get("reserves", []),
            "iip_yoy": _yoy(imf_raw.get("iip", [])),
            "exports_yoy": _yoy(imf_raw.get("exports", [])),
            "imports_yoy": _yoy(imf_raw.get("imports", [])),
            "trade_balance": sorted((p, round(exp[p] - imp[p], 4)) for p in exp.keys() & imp.keys()),
        }
        for k, pts in imf.items():
            if pts:
                print(f"[imf] {k:13} {len(pts):4} điểm  {pts[0][0]} -> {pts[-1][0]}")

        try:
            vnb = fetch_vnb(c)
            print(f"[vnb] {len(vnb)} chỉ tiêu, CPI kỳ {vnb.get('cpi_yoy', {}).get('period_label', '?')}, "
                  f"reserves kỳ {vnb.get('reserves', {}).get('period_label', '?')}")
        except Exception as e:
            print(f"[WARN] VietnamBiz: {type(e).__name__}: {e}", file=sys.stderr)
            vnb = {}

    if not any(imf.values()) and not vnb:
        print("[FAIL] không lấy được nguồn nào — giữ file cũ.", file=sys.stderr)
        return 1

    # ── MERGE: IMF (nền) + đuôi đã tích luỹ + điểm mới VietnamBiz ──
    existing = _read_existing()
    imf_last = {k: (pts[-1][0] if pts else "") for k, pts in imf.items()}
    merged: dict = {}
    for key, pts in imf.items():
        for p, v in pts:
            merged[(f"{p}-01", key)] = v
    for (date, key), v in existing.items():
        if key in _EXTEND and date[:7] > imf_last.get(key, "9999"):
            merged[(date, key)] = v
    for key in _EXTEND:
        o = vnb.get(key)
        if o and re.fullmatch(r"\d{4}-\d{2}", o["period"]) and o["period"] > imf_last.get(key, "9999"):
            merged[(f'{o["period"]}-01', key)] = o["value"]

    rows = sorted((d, k, v) for (d, k), v in merged.items())
    os.makedirs(_DATA, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        w.writerows(rows)
    _last = lambda k: max((d for d, kk, _ in rows if kk == k), default="?")[:7]
    print(f"[OK]  macro_history.csv: {len(rows)} dòng  (cpi→{_last('cpi_yoy')}, "
          f"iip→{_last('iip_yoy')}, xk→{_last('exports_yoy')}, reserves→{_last('reserves')})")

    # ── KPI: VietnamBiz (hiện tại), reserves VNB nếu có, không thì IMF ──
    latest = dict(vnb)
    if "reserves" not in latest and imf["reserves"]:
        p, v = imf["reserves"][-1]
        latest["reserves"] = {"value": v, "prev": (imf["reserves"][-2][1] if len(imf["reserves"]) >= 2 else None),
                              "period": p, "period_label": f"T{p[5:7]}/{p[:4]}",
                              "label": "Dự trữ ngoại hối", "fmt": "milusd"}
    ordered = {k: latest[k] for k in _KPI_ORDER if k in latest}
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    print(f"[OK]  macro_latest.json: {len(ordered)} KPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
