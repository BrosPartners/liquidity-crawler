"""Crawl chỉ tiêu kinh tế vĩ mô Việt Nam -> data/macro_*.

HAI nguồn ghép lại để vừa có LỊCH SỬ SÂU vừa tới THỜI ĐIỂM HIỆN TẠI:

1. DBnomics (proxy free IMF/IFS) — chuỗi tháng dài (1995→) nhưng trễ ~vài tháng.
     cpi_yoy  M.VN.PCPI_PC_CP_A_PT   reserves M.VN.RAFA_USD
     exports  M.VN.TXG_FOB_USD       imports  M.VN.TMG_CIF_USD
     iip      M.VN.AIP_IX            trade_balance = exports - imports
2. VietnamBiz data.vietnambiz.vn/macro-economic — GIÁ TRỊ MỚI NHẤT (tháng 06/2026…)
   cho ~13 chỉ tiêu, gồm cả FDI & đầu tư công (Vietstock chặn, IMF không có).
   Chỉ có latest -> dùng cho KPI + NỐI ĐUÔI cpi_yoy & trade_balance vào chuỗi IMF
   (những kỳ MỚI HƠN mốc cuối IMF). File macro_history.csv MERGE để tích luỹ dần
   mỗi tháng; backfill khoảng trống 1 lần bằng scripts/backfill_macro_wayback.py.

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
# key nào được NỐI ĐUÔI bằng VietnamBiz (cùng thước đo, cùng đơn vị):
_EXTEND = {"cpi_yoy", "trade_balance"}

# ── Nguồn 2: VietnamBiz macro-economic ───────────────────────────────────
_VNB_URL = "https://data.vietnambiz.vn/macro-economic"
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
# thứ tự hiện KPI
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


def _vnb_period(ngay: str) -> "tuple[str, str] | None":
    """('YYYY-MM'|'YYYY-Qn'|'YYYY', 'nhãn hiển thị') hoặc None."""
    s = str(ngay or "")
    m = re.search(r"Tháng (\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}", f"T{int(m.group(1)):02d}/{m.group(2)}"
    m = re.search(r"Quý (\d)/(\d{4})", s)
    if m:
        return f"{m.group(2)}-Q{m.group(1)}", f"Q{m.group(1)}/{m.group(2)}"
    m = re.search(r"Năm (\d{4})", s)
    if m:
        return m.group(1), f"Năm {m.group(1)}"
    return None


def fetch_vnb(client) -> dict:
    """key -> {value, prev, period, period_label, label, fmt} từ VietnamBiz (latest)."""
    r = client.get(_VNB_URL)
    r.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise RuntimeError("Không tìm thấy __NEXT_DATA__ VietnamBiz")
    data = json.loads(m.group(1))
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

    out: dict = {}
    for o in raw:
        title = o.get("title") or o.get("name") or o.get("label")
        if title not in _VNB or title in {k for k in out}:
            continue
        key, fmt, label = _VNB[title]
        if key in out:
            continue
        pl = _vnb_period(o.get("ngay"))
        if not pl:
            continue
        try:
            val = round(float(o.get("value")), 4)
        except (TypeError, ValueError):
            continue
        prev = o.get("pre_value")
        try:
            prev = round(float(prev), 4) if prev is not None else None
        except (TypeError, ValueError):
            prev = None
        out[key] = {"value": val, "prev": prev, "period": pl[0],
                    "period_label": pl[1], "label": label, "fmt": fmt}
    return out


def _read_existing() -> dict:
    """{(date, key): value} từ macro_history.csv hiện có (để MERGE tích luỹ)."""
    ex = {}
    if not os.path.exists(CSV_PATH):
        return ex
    with open(CSV_PATH, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            try:
                ex[(row["date"], row["series_key"])] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
    return ex


def main() -> int:
    with httpx.Client(headers=_UA, timeout=45, follow_redirects=True) as c:
        # 1) IMF
        imf: dict = {}
        for key, sid in _IMF.items():
            try:
                imf[key] = _fetch_imf(c, sid)
            except Exception as e:
                print(f"[WARN] IMF {key}: {type(e).__name__}: {e}", file=sys.stderr)
                imf[key] = []
        exp = dict(imf.get("exports", []))
        imp = dict(imf.get("imports", []))
        imf["trade_balance"] = sorted((p, round(exp[p] - imp[p], 4)) for p in exp.keys() & imp.keys())
        for k, pts in imf.items():
            if pts:
                print(f"[imf] {k:13} {len(pts):4} điểm  {pts[0][0]} -> {pts[-1][0]}")

        # 2) VietnamBiz (latest, tới hiện tại)
        try:
            vnb = fetch_vnb(c)
            print(f"[vnb] {len(vnb)} chỉ tiêu, kỳ mới nhất "
                  f"{vnb.get('cpi_yoy', {}).get('period_label', '?')}")
        except Exception as e:
            print(f"[WARN] VietnamBiz: {type(e).__name__}: {e}", file=sys.stderr)
            vnb = {}

    if not any(imf.values()) and not vnb:
        print("[FAIL] không lấy được nguồn nào — giữ file cũ.", file=sys.stderr)
        return 1

    # ── MERGE lịch sử: IMF (nền) + đuôi VietnamBiz đã tích luỹ + điểm mới ──
    existing = _read_existing()
    imf_last = {k: (pts[-1][0] if pts else "") for k, pts in imf.items()}
    merged: dict = {}
    for key, pts in imf.items():                       # nền IMF
        for p, v in pts:
            merged[(f"{p}-01", key)] = v
    for (date, key), v in existing.items():            # giữ đuôi đã tích luỹ trước đó
        if key in _EXTEND and date[:7] > imf_last.get(key, "9999"):
            merged[(date, key)] = v
    for key in _EXTEND:                                # nối điểm mới nhất từ VietnamBiz
        o = vnb.get(key)
        if o and re.fullmatch(r"\d{4}-\d{2}", o["period"]) and o["period"] > imf_last.get(key, "9999"):
            merged[(f'{o["period"]}-01', key)] = o["value"]

    rows = sorted((d, k, v) for (d, k), v in merged.items())
    os.makedirs(_DATA, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])
        w.writerows(rows)
    print(f"[OK]  macro_history.csv: {len(rows)} dòng "
          f"(cpi tới {max((d for d, k, _ in rows if k == 'cpi_yoy'), default='?')[:7]})")

    # ── KPI: VietnamBiz (hiện tại) + reserves từ IMF ──
    latest = dict(vnb)
    res = imf.get("reserves") or []
    if res:
        p, v = res[-1]
        latest["reserves"] = {"value": v, "prev": (res[-2][1] if len(res) >= 2 else None),
                              "period": p, "period_label": f"T{p[5:7]}/{p[:4]}",
                              "label": "Dự trữ ngoại hối", "fmt": "milusd"}
    ordered = {k: latest[k] for k in _KPI_ORDER if k in latest}
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    print(f"[OK]  macro_latest.json: {len(ordered)} KPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
