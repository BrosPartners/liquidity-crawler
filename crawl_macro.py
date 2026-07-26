"""Crawl các chỉ tiêu kinh tế vĩ mô Việt Nam (tháng) -> data/macro_*.

Nguồn: DBnomics (api.db.nomics.world) — proxy free cho IMF/IFS. Đây là nguồn
lịch sử MIỄN PHÍ đáng tin duy nhất tìm được cho VN (Vietstock chặn sau
"Gói sản phẩm"; VietnamBiz redirect /error). IMF/IFS trễ ~vài tháng so với hôm
nay nhưng cho chuỗi tháng dài, thật, tự cập nhật khi IMF phát hành số mới.

Series (IMF/IFS, tần suất tháng):
    cpi_yoy   M.VN.PCPI_PC_CP_A_PT  CPI so cùng kỳ (%)
    reserves  M.VN.RAFA_USD         Dự trữ ngoại hối (triệu USD)
    exports   M.VN.TXG_FOB_USD      Xuất khẩu FOB (triệu USD)
    imports   M.VN.TMG_CIF_USD      Nhập khẩu CIF (triệu USD)
    iip       M.VN.AIP_IX           Chỉ số sản xuất công nghiệp (index)
    trade_balance = exports - imports (tính tại chỗ, triệu USD)

Ghi ĐÈ mỗi lần (idempotent) — DBnomics luôn trả full lịch sử, không cần merge.
FDI / giải ngân đầu tư công KHÔNG có feed free -> không đưa vào.

    python crawl_macro.py
"""
from __future__ import annotations

import csv
import json
import os
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

_API = "https://api.db.nomics.world/v22/series/"

# key -> (DBnomics series id, label, unit, "as-of tần suất")
_SERIES = {
    "cpi_yoy":  ("IMF/IFS/M.VN.PCPI_PC_CP_A_PT", "CPI so cùng kỳ (YoY)", "%",      "%"),
    "reserves": ("IMF/IFS/M.VN.RAFA_USD",        "Dự trữ ngoại hối",      "tỷ USD", "tr USD"),
    "exports":  ("IMF/IFS/M.VN.TXG_FOB_USD",     "Xuất khẩu (FOB)",       "tỷ USD", "tr USD"),
    "imports":  ("IMF/IFS/M.VN.TMG_CIF_USD",     "Nhập khẩu (CIF)",       "tỷ USD", "tr USD"),
    "iip":      ("IMF/IFS/M.VN.AIP_IX",          "Sản xuất công nghiệp (IIP)", "điểm", "index"),
}


def _fetch_series(client: httpx.Client, series_id: str) -> "list[tuple[str, float]]":
    """[(period 'YYYY-MM', value)] đã lọc null, tăng dần theo thời gian."""
    r = client.get(_API + series_id, params={"observations": "1"})
    r.raise_for_status()
    docs = r.json().get("series", {}).get("docs", [])
    if not docs:
        return []
    doc = docs[0]
    periods = doc.get("period", [])
    values = doc.get("value", [])
    out = []
    for p, v in zip(periods, values):
        if v is None or v == "NA":
            continue
        try:
            out.append((p, round(float(v), 4)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def main() -> int:
    headers = {"User-Agent": "Mozilla/5.0 (liquidity-crawler macro)"}
    raw: dict = {}
    with httpx.Client(headers=headers, timeout=45, follow_redirects=True) as c:
        for key, (sid, *_rest) in _SERIES.items():
            try:
                pts = _fetch_series(c, sid)
            except Exception as e:
                print(f"[WARN] {key} ({sid}): {type(e).__name__}: {e}", file=sys.stderr)
                pts = []
            raw[key] = pts
            if pts:
                print(f"[ok]  {key:9} {len(pts):4} điểm  {pts[0][0]} -> {pts[-1][0]}  "
                      f"cuối={pts[-1][1]}")
            else:
                print(f"[--]  {key:9} rỗng")

    if not any(raw.values()):
        print("[FAIL] DBnomics không trả điểm nào — giữ file cũ.", file=sys.stderr)
        return 1

    # trade_balance = exports - imports (theo tháng có đủ 2 vế)
    exp = dict(raw.get("exports", []))
    imp = dict(raw.get("imports", []))
    tb = sorted(((p, round(exp[p] - imp[p], 4)) for p in exp.keys() & imp.keys()))
    if tb:
        raw["trade_balance"] = tb
        print(f"[ok]  {'trade_bal':9} {len(tb):4} điểm  {tb[0][0]} -> {tb[-1][0]}  "
              f"cuối={tb[-1][1]}")

    # ── ghi CSV long: date,key,value (date = YYYY-MM-01) ──
    os.makedirs(_DATA, exist_ok=True)
    rows = []
    for key, pts in raw.items():
        for p, v in pts:
            rows.append((f"{p}-01", key, v))
    rows.sort()
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series_key", "value"])   # 'series_key' để web parseMktCSV đọc được
        w.writerows(rows)
    print(f"[OK]  macro_history.csv: {len(rows)} dòng")

    # ── ghi JSON KPI: mỗi key -> {value, prev, period, label, unit} ──
    latest: dict = {}
    labels = {**{k: (v[1], v[2]) for k, v in _SERIES.items()},
              "trade_balance": ("Cán cân thương mại", "tỷ USD")}
    for key, pts in raw.items():
        if not pts:
            continue
        p, v = pts[-1]
        prev = pts[-2][1] if len(pts) >= 2 else None
        label, unit = labels.get(key, (key, ""))
        latest[key] = {"value": v, "prev": prev, "period": p, "label": label, "unit": unit}
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    print(f"[OK]  macro_latest.json: {len(latest)} chỉ tiêu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
