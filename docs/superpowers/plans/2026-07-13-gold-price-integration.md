# Gold Price Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị giá vàng (SJC + 6 hãng + vàng thế giới + gap) thành một tab "Giá vàng" trong dashboard `liquidity-crawler`, tự cập nhật hàng ngày từ file `gold_prices_all.xlsx` mà một bot Telegram có sẵn đăng lúc 9:00, chạy trên GitHub Actions và deploy Vercel.

**Architecture:** GitHub Actions (cron) dùng Telethon (phiên tài khoản user) kéo `gold_prices_all.xlsx` mới nhất từ Telegram group → `core/gold_parse.py` parse → `core/gold_sink.py` ghi `data/gold_latest.json` + `data/gold_history.csv` + `data/gold_brands.csv` → `scripts/build_static.py` nhúng vào `dist/dashboard.html` → commit → Vercel auto-deploy. Crawler bank/market vẫn chạy local (Phase 3 sau); `build_static.py` đọc data bank từ Google Sheet lúc build nên vẫn tươi.

**Tech Stack:** Python 3.12 (openpyxl, telethon), HTML/Canvas JS thuần (không CDN), GitHub Actions, Vercel static hosting.

## Global Constraints

- Môi trường máy local: Windows PowerShell. Chạy Python in tiếng Việt phải set `PYTHONIOENCODING=utf-8` (hoặc `PYTHONUTF8=1`).
- Dashboard KHÔNG dùng CDN — chỉ Canvas + JS nội tuyến (tái dùng helper sẵn có).
- Parse Excel theo **TÊN sheet/cột** (không theo index); ô `#N/A`/trống → `None`.
- `gap` và `pct_gap` **tự tính** trong parser (`sjc_sell - world_gold_vnd`), KHÔNG đọc cột Gap của file (đầy `#N/A`).
- Test: kiểu plain-assert, chạy `python tests/test_<name>.py` (project KHÔNG dùng pytest). Mỗi file test có `if __name__ == "__main__":` gọi các hàm test.
- Repo GitHub **private**. Không commit secret; `config.json` đã nằm trong `.gitignore`.
- Chuỗi Telegram session chỉ nằm ở GitHub Secrets; login do user tự làm.
- File Excel mẫu thật (dùng cho smoke test local): `D:\BP\Bros Partners\Tickers\PNJ\giá vàng\gold_prices_all.xlsx`.
- gold_type đại diện mỗi hãng (map cố định): SJC=`sjc_mieng`, DOJI=`doji_hn`, BTMC=`btmc_sjc`, BTMH=`btmh_mieng`, PHUQUY=`phuquy_sjc`, PNJ=`sjc_at_pnj_hn`.

---

## File Structure

- Create `core/gold_parse.py` — `parse_gold_xlsx(path) -> dict{latest, history, brands}`.
- Create `core/gold_sink.py` — `write_gold_outputs(data, data_dir)` → 3 file trong `data/`.
- Create `crawl_gold.py` — CLI: `--file PATH` (local) hoặc kéo Telegram (mặc định).
- Create `login.py` — chạy 1 lần tạo StringSession + liệt kê group id.
- Create `tests/test_gold_parse.py` — test parser trên fixture xlsx tổng hợp.
- Create `tests/make_gold_fixture.py` — dựng fixture xlsx nhỏ đúng cấu trúc 4 sheet.
- Modify `scripts/build_static.py` — nhúng 3 nguồn gold.
- Modify `web/index.html` — tab + pane "Giá vàng" + JS.
- Modify `requirements.txt` — thêm `telethon`, `openpyxl`.
- Create `.github/workflows/gold.yml` — cron Actions.
- Create `vercel.json` — serve tĩnh `dist/`.

---

## Task 1: Parser `core/gold_parse.py`

**Files:**
- Create: `core/gold_parse.py`
- Create: `tests/make_gold_fixture.py`
- Test: `tests/test_gold_parse.py`

**Interfaces:**
- Produces: `parse_gold_xlsx(path: str) -> dict` với khoá:
  - `latest`: `{as_of:str, world_gold_usd:float|None, world_gold_vnd:float|None, sjc_sell:float|None, gap:float|None, pct_gap:float|None, usd_vnd:float|None, brands:[{company:str, buy:float|None, sell:float|None}]}`
  - `history`: list `{date:str "YYYY-MM-DD", world_gold_usd, world_gold_vnd, sjc_sell, usd_vnd, gap, pct_gap}` (sort tăng theo date)
  - `brands`: list `{date:str, company:str, buy:float|None, sell:float|None}`
- Module-level: `BRAND_GOLD_TYPE: dict`, `BRAND_ORDER: list`.

- [ ] **Step 1: Viết fixture builder** `tests/make_gold_fixture.py`

```python
"""Dựng file xlsx nhỏ mô phỏng đúng cấu trúc gold_prices_all.xlsx để test parser."""
import openpyxl


def build(path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Gia TG (USD_oz)")
    ws.append(["Nguồn: ..."])
    ws.append(["date", "open_usd", "high_usd", "low_usd", "close_usd", "source"])
    ws.append(["2026-07-10", 4122.3, 4125.8, 4090.6, 4104.1, "yf"])
    ws.append(["2026-07-13", 4106.6, 4111.6, 4069.4, 4076.4, "yf"])

    ws = wb.create_sheet("Gia TG (VND-luong)")
    ws.append(["Nguồn: ..."])
    ws.append(["date", "close_usd", "usd_vnd", "close_vnd", "Gia SJC", "Gap giá vàng", "% gap giá vàng"])
    ws.append(["2026-07-13", 4076.4, 26260, 128000000, "#N/A", "#N/A", "#N/A"])
    ws.append([None, None, None, None, "#N/A", "#N/A", "#N/A"])  # hàng rác cuối

    ws = wb.create_sheet("Ty gia USD-VND")
    ws.append(["Nguồn: ..."])
    ws.append(["date", "usd_vnd", "source"])
    ws.append(["2026-07-10", 26290, "yf"])
    ws.append(["2026-07-13", 26260, "yf"])

    ws = wb.create_sheet("SJC")
    ws.append(["Nguồn: ..."])
    ws.append(["date", "sjc_mieng_buy_price", "sjc_mieng_1c_buy_price", "sjc_mieng_1l_buy_price",
               "sjc_mieng_5c_buy_price", "sjc_nhan_1c_buy_price", "sjc_nutrang_75_buy_price",
               "sjc_nutrang_99_buy_price", "sjc_nutrang_9999_buy_price", "sjc_mieng_sell_price"])
    ws.append(["2026-07-13", 145900000, None, None, None, None, None, None, None, 148900000])

    ws = wb.create_sheet("Gia VN (tat ca)")
    ws.append(["Nguồn: ..."])
    ws.append(["id", "date", "company", "gold_type", "purity", "buy_price", "sell_price", "unit", "source"])
    rows = [
        (1, "2026-07-13", "SJC", "sjc_mieng", 999.9, 145900000, 148900000, "luong", "24h"),
        (2, "2026-07-13", "SJC", "sjc_nhan_1c", 999.9, 145400000, 148400000, "luong", "24h"),
        (3, "2026-07-13", "DOJI", "doji_hn", 999.9, 145900000, 148900000, "luong", "24h"),
        (4, "2026-07-13", "BTMC", "btmc_sjc", 999.9, 145000000, 149900000, "luong", "24h"),
        (5, "2026-07-13", "BTMH", "btmh_mieng", 999.9, 144000000, 148000000, "luong", "24h"),
        (6, "2026-07-13", "PHUQUY", "phuquy_sjc", 999.9, 145500000, 148900000, "luong", "24h"),
        (7, "2026-07-13", "PNJ", "sjc_at_pnj_hn", 999.9, 145900000, 148900000, "luong", "24h"),
        (8, "2026-07-13", "PNJ", "vang_15k", 999.9, 85000000, 94900000, "luong", "24h"),
    ]
    for r in rows:
        ws.append(list(r))

    wb.save(path)


if __name__ == "__main__":
    build("tests/_gold_fixture.xlsx")
    print("OK fixture -> tests/_gold_fixture.xlsx")
```

- [ ] **Step 2: Viết test thất bại** `tests/test_gold_parse.py`

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tests.make_gold_fixture import build
from core.gold_parse import parse_gold_xlsx, BRAND_ORDER

FIX = os.path.join(os.path.dirname(__file__), "_gold_fixture.xlsx")


def _data():
    build(FIX)
    return parse_gold_xlsx(FIX)


def test_latest():
    d = _data()
    lt = d["latest"]
    assert lt["as_of"] == "2026-07-13"
    assert lt["sjc_sell"] == 148900000
    assert lt["world_gold_usd"] == 4076.4
    assert lt["usd_vnd"] == 26260
    assert lt["world_gold_vnd"] == 128000000
    # gap tự tính = 148900000 - 128000000
    assert lt["gap"] == 20900000
    assert abs(lt["pct_gap"] - (20900000 / 128000000)) < 1e-9


def test_brands():
    d = _data()
    comps = [b["company"] for b in d["latest"]["brands"]]
    # đủ 6 hãng, đúng thứ tự BRAND_ORDER
    assert comps == [c for c in BRAND_ORDER if c in comps]
    assert len(comps) == 6
    sjc = next(b for b in d["latest"]["brands"] if b["company"] == "SJC")
    assert sjc["sell"] == 148900000
    # PNJ phải lấy sjc_at_pnj_hn (148.9M) KHÔNG phải vang_15k (94.9M)
    pnj = next(b for b in d["latest"]["brands"] if b["company"] == "PNJ")
    assert pnj["sell"] == 148900000


def test_history_skips_junk():
    d = _data()
    # hàng rác cuối (date=None) không lọt vào history
    assert all(r["date"] for r in d["history"])
    # có ngày 2026-07-13
    assert any(r["date"] == "2026-07-13" for r in d["history"])


if __name__ == "__main__":
    test_latest()
    test_brands()
    test_history_skips_junk()
    print("Tất cả test PASS")
```

- [ ] **Step 3: Chạy test để xác nhận FAIL**

Run: `set PYTHONIOENCODING=utf-8 && python tests/test_gold_parse.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.gold_parse'`

- [ ] **Step 4: Viết `core/gold_parse.py`**

```python
"""Parse gold_prices_all.xlsx (do bot Telegram tạo) -> dữ liệu cho dashboard.

Đọc theo TÊN sheet/cột (không theo index). Ô '#N/A'/trống -> None.
gap / pct_gap TỰ TÍNH (sjc_sell - world_gold_vnd) để né '#N/A' trong file.
"""
from __future__ import annotations

import openpyxl

# Mỗi hãng chọn 1 loại vàng "miếng SJC-tương đương" để so sánh công bằng.
BRAND_GOLD_TYPE = {
    "SJC": "sjc_mieng",
    "DOJI": "doji_hn",
    "BTMC": "btmc_sjc",
    "BTMH": "btmh_mieng",
    "PHUQUY": "phuquy_sjc",
    "PNJ": "sjc_at_pnj_hn",
}
BRAND_ORDER = ["SJC", "DOJI", "PNJ", "BTMC", "BTMH", "PHUQUY"]


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _date_str(v):
    if v is None:
        return None
    try:
        return v.strftime("%Y-%m-%d")
    except AttributeError:
        s = str(v).strip()
        return s[:10] if s else None


def _sheet_map(ws, val_cols):
    """Trả {date_str: {col: number}} đọc theo tên cột, header ở hàng 2."""
    it = ws.iter_rows(min_row=2, values_only=True)
    header = list(next(it))
    if "date" not in header:
        return {}
    di = header.index("date")
    idx = {c: header.index(c) for c in val_cols if c in header}
    out = {}
    for r in it:
        d = _date_str(r[di])
        if not d:
            continue
        out[d] = {c: _num(r[i]) for c, i in idx.items()}
    return out


def parse_gold_xlsx(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    usd = _sheet_map(wb["Gia TG (USD_oz)"], ["close_usd"])
    vnd = _sheet_map(wb["Gia TG (VND-luong)"], ["close_vnd"])
    fx = _sheet_map(wb["Ty gia USD-VND"], ["usd_vnd"])
    sjc = _sheet_map(wb["SJC"], ["sjc_mieng_sell_price"])

    all_dates = sorted(set(usd) | set(vnd) | set(fx) | set(sjc))
    history = []
    for d in all_dates:
        wg_usd = usd.get(d, {}).get("close_usd")
        wg_vnd = vnd.get(d, {}).get("close_vnd")
        sjc_sell = sjc.get(d, {}).get("sjc_mieng_sell_price")
        rate = fx.get(d, {}).get("usd_vnd")
        gap = pct = None
        if wg_vnd and sjc_sell:
            gap = sjc_sell - wg_vnd
            pct = gap / wg_vnd
        history.append({
            "date": d, "world_gold_usd": wg_usd, "world_gold_vnd": wg_vnd,
            "sjc_sell": sjc_sell, "usd_vnd": rate, "gap": gap, "pct_gap": pct,
        })

    ws = wb["Gia VN (tat ca)"]
    it = ws.iter_rows(min_row=2, values_only=True)
    h = list(next(it))
    ci = {n: h.index(n) for n in ("date", "company", "gold_type", "buy_price", "sell_price")}
    brands = []
    for r in it:
        comp = r[ci["company"]]
        if comp not in BRAND_GOLD_TYPE:
            continue
        if r[ci["gold_type"]] != BRAND_GOLD_TYPE[comp]:
            continue
        d = _date_str(r[ci["date"]])
        if not d:
            continue
        brands.append({"date": d, "company": comp,
                       "buy": _num(r[ci["buy_price"]]), "sell": _num(r[ci["sell_price"]])})

    return {"latest": _build_latest(history, brands), "history": history, "brands": brands}


def _build_latest(history, brands):
    def last_non_null(field):
        for row in reversed(history):
            if row.get(field) is not None:
                return row
        return {}

    sjc_row = last_non_null("sjc_sell")
    gap_row = last_non_null("gap")
    bmax = {}
    for b in brands:
        cur = bmax.get(b["company"])
        if cur is None or b["date"] > cur["date"]:
            bmax[b["company"]] = b
    brand_list = [{"company": c, "buy": bmax[c]["buy"], "sell": bmax[c]["sell"]}
                  for c in BRAND_ORDER if c in bmax]
    return {
        "as_of": (history[-1]["date"] if history else None),
        "world_gold_usd": last_non_null("world_gold_usd").get("world_gold_usd"),
        "world_gold_vnd": last_non_null("world_gold_vnd").get("world_gold_vnd"),
        "sjc_sell": sjc_row.get("sjc_sell"),
        "gap": gap_row.get("gap"),
        "pct_gap": gap_row.get("pct_gap"),
        "usd_vnd": last_non_null("usd_vnd").get("usd_vnd"),
        "brands": brand_list,
    }
```

- [ ] **Step 5: Chạy test để xác nhận PASS**

Run: `set PYTHONIOENCODING=utf-8 && python tests/test_gold_parse.py`
Expected: `Tất cả test PASS`

- [ ] **Step 6: Smoke test trên file thật**

Run:
```
set PYTHONIOENCODING=utf-8 && python -c "from core.gold_parse import parse_gold_xlsx; d=parse_gold_xlsx(r'D:\BP\Bros Partners\Tickers\PNJ\giá vàng\gold_prices_all.xlsx'); print(d['latest'])"
```
Expected: in ra `as_of` gần hôm nay, `sjc_sell` ~148900000, `world_gold_usd` ~4076, `usd_vnd` ~26260, `brands` 6 hãng. (Chỉ eyeball, không assert.)

- [ ] **Step 7: Commit**

```bash
git add core/gold_parse.py tests/test_gold_parse.py tests/make_gold_fixture.py
git commit -m "feat(gold): parser gold_prices_all.xlsx -> latest/history/brands"
```

---

## Task 2: Sink `core/gold_sink.py`

**Files:**
- Create: `core/gold_sink.py`
- Test: `tests/test_gold_sink.py`

**Interfaces:**
- Consumes: `parse_gold_xlsx()` output dict (Task 1).
- Produces: `write_gold_outputs(data: dict, data_dir: str) -> None`. Ghi 3 file:
  - `gold_latest.json` — dump `data["latest"]` (UTF-8, indent 2).
  - `gold_history.csv` — long format header `date,series_key,value` (series_key ∈ world_gold_usd, world_gold_vnd, sjc_sell, gap, pct_gap, usd_vnd; bỏ ô None).
  - `gold_brands.csv` — header `date,company,buy,sell` (ô None → rỗng).

- [ ] **Step 1: Viết test thất bại** `tests/test_gold_sink.py`

```python
import csv
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tests.make_gold_fixture import build
from core.gold_parse import parse_gold_xlsx
from core.gold_sink import write_gold_outputs

FIX = os.path.join(os.path.dirname(__file__), "_gold_fixture.xlsx")


def test_writes_three_files():
    build(FIX)
    data = parse_gold_xlsx(FIX)
    d = tempfile.mkdtemp()
    write_gold_outputs(data, d)

    with open(os.path.join(d, "gold_latest.json"), encoding="utf-8") as f:
        lt = json.load(f)
    assert lt["sjc_sell"] == 148900000

    with open(os.path.join(d, "gold_history.csv"), encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["date", "series_key", "value"]
    # không có ô rỗng cho value
    assert all(r[2] != "" for r in rows[1:])

    with open(os.path.join(d, "gold_brands.csv"), encoding="utf-8") as f:
        brows = list(csv.reader(f))
    assert brows[0] == ["date", "company", "buy", "sell"]
    assert any(r[1] == "PNJ" and r[3] == "148900000.0" for r in brows[1:])


if __name__ == "__main__":
    test_writes_three_files()
    print("Tất cả test PASS")
```

- [ ] **Step 2: Chạy test xác nhận FAIL**

Run: `set PYTHONIOENCODING=utf-8 && python tests/test_gold_sink.py`
Expected: FAIL — `No module named 'core.gold_sink'`

- [ ] **Step 3: Viết `core/gold_sink.py`**

```python
"""Ghi output giá vàng cho dashboard: latest.json + history.csv (long) + brands.csv."""
from __future__ import annotations

import csv
import json
import os

HIST_KEYS = ["world_gold_usd", "world_gold_vnd", "sjc_sell", "gap", "pct_gap", "usd_vnd"]


def write_gold_outputs(data, data_dir):
    os.makedirs(data_dir, exist_ok=True)

    with open(os.path.join(data_dir, "gold_latest.json"), "w", encoding="utf-8") as f:
        json.dump(data["latest"], f, ensure_ascii=False, indent=2)

    with open(os.path.join(data_dir, "gold_history.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "series_key", "value"])
        for row in data["history"]:
            for k in HIST_KEYS:
                v = row.get(k)
                if v is not None:
                    w.writerow([row["date"], k, v])

    with open(os.path.join(data_dir, "gold_brands.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "company", "buy", "sell"])
        for b in data["brands"]:
            w.writerow([b["date"], b["company"],
                        "" if b["buy"] is None else b["buy"],
                        "" if b["sell"] is None else b["sell"]])
```

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `set PYTHONIOENCODING=utf-8 && python tests/test_gold_sink.py`
Expected: `Tất cả test PASS`

- [ ] **Step 5: Commit**

```bash
git add core/gold_sink.py tests/test_gold_sink.py
git commit -m "feat(gold): sink ghi latest.json + history.csv + brands.csv"
```

---

## Task 3: CLI `crawl_gold.py` + deps

**Files:**
- Create: `crawl_gold.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `parse_gold_xlsx`, `write_gold_outputs`.
- Produces: chạy được `python crawl_gold.py --file <path>` (ghi vào `data/`) và `python crawl_gold.py` (kéo Telegram qua env `TG_API_ID/TG_API_HASH/TG_SESSION/TG_CHAT`).
- Hàm `fetch_from_telegram(dest: str) -> str` (tải file, trả path).

- [ ] **Step 1: Thêm deps vào `requirements.txt`**

Thêm 2 dòng cuối file:
```
openpyxl>=3.1
telethon>=1.36
```

- [ ] **Step 2: Viết `crawl_gold.py`**

```python
"""Thu thập giá vàng: tải gold_prices_all.xlsx mới nhất từ Telegram group -> JSON/CSV.

  python crawl_gold.py --file "C:/path/gold_prices_all.xlsx"   # dùng file local (test)
  python crawl_gold.py                                          # kéo từ Telegram (mặc định)

Env (chế độ Telegram): TG_API_ID, TG_API_HASH, TG_SESSION, TG_CHAT
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.gold_parse import parse_gold_xlsx
from core.gold_sink import write_gold_outputs

_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_ROOT, "data")
FILENAME = "gold_prices_all.xlsx"


def fetch_from_telegram(dest):
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"]
    chat = os.environ["TG_CHAT"]
    try:
        chat = int(chat)
    except ValueError:
        pass
    with TelegramClient(StringSession(session), api_id, api_hash) as client:
        for msg in client.iter_messages(chat, limit=60):
            if not msg.document:
                continue
            name = next((a.file_name for a in msg.document.attributes
                         if getattr(a, "file_name", None)), None)
            if name == FILENAME:
                client.download_media(msg, dest)
                return dest
    raise RuntimeError(f"Không thấy {FILENAME} trong 60 tin gần nhất của chat {chat}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Dùng file xlsx local thay vì kéo Telegram")
    args = ap.parse_args()

    path = args.file or os.path.join(tempfile.gettempdir(), FILENAME)
    if not args.file:
        fetch_from_telegram(path)

    data = parse_gold_xlsx(path)
    write_gold_outputs(data, DATA_DIR)
    lt = data["latest"]
    print(f"OK gold: as_of={lt['as_of']} SJC bán={lt['sjc_sell']} "
          f"vàng TG(USD)={lt['world_gold_usd']} USD/VND={lt['usd_vnd']} "
          f"{len(data['history'])} ngày, {len(lt['brands'])} hãng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Chạy chế độ --file trên file thật (verify ghi data)**

Run:
```
set PYTHONIOENCODING=utf-8 && python crawl_gold.py --file "D:\BP\Bros Partners\Tickers\PNJ\giá vàng\gold_prices_all.xlsx"
```
Expected: in dòng `OK gold: as_of=... SJC bán=148900000.0 ... 6 hãng`; tồn tại `data/gold_latest.json`, `data/gold_history.csv`, `data/gold_brands.csv`.

- [ ] **Step 4: Verify nội dung file**

Run: `python -c "import json;print(json.load(open('data/gold_latest.json',encoding='utf-8'))['brands'])"`
Expected: list 6 hãng với sell hợp lý (SJC/DOJI/PNJ ~148.9M).

- [ ] **Step 5: Commit**

```bash
git add crawl_gold.py requirements.txt data/gold_latest.json data/gold_history.csv data/gold_brands.csv
git commit -m "feat(gold): crawl_gold.py (Telegram + --file) và deps"
```

---

## Task 4: Nhúng gold vào `scripts/build_static.py`

**Files:**
- Modify: `scripts/build_static.py`

**Interfaces:**
- Consumes: `data/gold_latest.json`, `data/gold_history.csv`, `data/gold_brands.csv` (Task 3); các fetch call trong `web/index.html` (Task 5 sẽ thêm — nhưng build_static phải xử lý an toàn nếu chưa có).
- Produces: `dist/dashboard.html` có nhúng `__EMBED_GOLD_LATEST__`, `__EMBED_GOLD_HISTORY__`, `__EMBED_GOLD_BRANDS__` và đã thay các fetch gold.

> Lưu ý thứ tự: Task 5 thêm fetch gold vào index.html. Nếu thực thi Task 4 trước Task 5, các `re.sub` gold sẽ không khớp (count=0) — CHẤP NHẬN (không lỗi, chỉ là chưa thay). Bước verify của Task 4 chạy SAU khi Task 5 xong, hoặc đơn giản làm Task 5 trước rồi quay lại verify Task 4. Đề nghị executor làm Task 5 xong mới verify Task 4 (2 task này ghép đôi).

- [ ] **Step 1: Đọc 3 file gold trong `main()`**

Sau khối đọc `mkt_history` (ngay trước comment `# ── Ưu tiên NGUỒN GỐC...`), thêm:

```python
    def _read(name, default):
        p = os.path.join(_ROOT, "data", name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return fh.read().strip()
        return default

    gold_latest = _read("gold_latest.json", "null")
    gold_history = _read("gold_history.csv", "")
    gold_brands = _read("gold_brands.csv", "")
```

- [ ] **Step 2: Thêm 3 `re.sub` thay fetch gold**

Ngay sau khối `# 3. Thay 2 fetch market...` (trước `# 4. Chèn data...`), thêm:

```python
    # 3b. Thay các fetch gold bằng data nhúng (count=0 nếu index.html chưa có — OK)
    html = re.sub(
        r'fetch\("\.\./data/gold_latest\.json"\)\s*\.then\(r => r\.json\(\)\)',
        "Promise.resolve(__EMBED_GOLD_LATEST__)", html, count=1)
    html = re.sub(
        r'fetch\("\.\./data/gold_history\.csv"\)\s*'
        r'\.then\(r => \{ if \(!r\.ok\) throw new Error\("x"\); return r\.text\(\); \}\)',
        "Promise.resolve(__EMBED_GOLD_HISTORY__)", html, count=1)
    html = re.sub(
        r'fetch\("\.\./data/gold_brands\.csv"\)\s*'
        r'\.then\(r => \{ if \(!r\.ok\) throw new Error\("x"\); return r\.text\(\); \}\)',
        "Promise.resolve(__EMBED_GOLD_BRANDS__)", html, count=1)
```

- [ ] **Step 3: Thêm 3 const vào block embed**

Trong biến `embed`, thêm 3 dòng trước dấu đóng (sau dòng `__EMBED_MKT_HISTORY__`):

```python
        f"const __EMBED_GOLD_LATEST__ = {gold_latest};\n"
        f"const __EMBED_GOLD_HISTORY__ = {json.dumps(gold_history, ensure_ascii=False)};\n"
        f"const __EMBED_GOLD_BRANDS__ = {json.dumps(gold_brands, ensure_ascii=False)};\n"
```

- [ ] **Step 4: (Verify — chạy sau Task 5)** Build và kiểm tra nhúng

Run: `set PYTHONIOENCODING=utf-8 && python scripts/build_static.py --no-sheet`
Expected: `OK -> ...dist\dashboard.html`. Sau đó:
Run: `grep -c "__EMBED_GOLD_LATEST__ =" dist/dashboard.html` → `1`; `grep -c "Promise.resolve(__EMBED_GOLD_LATEST__)" dist/dashboard.html` → `1` (fetch đã bị thay).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_static.py
git commit -m "feat(gold): build_static nhúng gold latest/history/brands"
```

---

## Task 5: Tab "Giá vàng" trong `web/index.html`

**Files:**
- Modify: `web/index.html`

**Interfaces:**
- Consumes: helper sẵn có `interactiveLineChart(canvasId, dates, series, drawFn)`, `drawLineChart(canvas, dates, series, height)`, hàm `setTab(name)`; markup class `.mkt-wrap/.mkt-grid/.mkt-card/.mkt-label/.mkt-val/.mkt-unit/.mkt-asof/.mkt-section-title/.panel/.panel-title/.ts-legend`. Data qua fetch (dev) / `__EMBED_GOLD_*__` (prod).
- Produces: tab `data-tab="vang"`, pane `data-pane="vang"`, các hàm JS `loadGold()`, `renderGold()`, `renderGoldCharts()`.

- [ ] **Step 1: Thêm nút tab**

Trong `<div class="tabs" id="tabNav">`, sau nút `data-tab="tygia"`, thêm:
```html
  <button class="tab-btn" data-tab="vang">Giá vàng</button>
```

- [ ] **Step 2: Thêm pane "vang"**

Ngay sau `</section>` của pane `data-pane="tygia"`, thêm:
```html
<section class="tabpane" data-pane="vang">
  <div class="summary" id="goldKpi"></div>
  <div class="mkt-wrap">
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">SJC bán vs vàng thế giới quy đổi (VND/lượng)</div>
        <div class="ts-legend" id="goldPriceLegend"></div>
      </div>
      <canvas id="goldPriceChart"></canvas>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Chênh lệch với thế giới (%)</div>
        <div class="ts-legend" id="goldGapLegend"></div>
      </div>
      <canvas id="goldGapChart"></canvas>
    </div>
    <div class="mkt-section-title">Giá bán các hãng (mới nhất)</div>
    <div class="mkt-grid" id="goldBrandGrid"></div>
    <div class="mkt-note" id="goldNote"></div>
  </div>
</section>
```

- [ ] **Step 3: Thêm data loaders + render (dev fetch, prod embed)**

Ngay sau khối `Promise.resolve(fetch("../data/market_history.csv")...)` (kết thúc `.catch(() => {});`), thêm:

```javascript
  // ── Giá vàng ─────────────────────────────────────────────────────────
  let GOLD = null, GOLD_HIST = [], GOLD_BRANDS = [];

  fetch("../data/gold_latest.json").then(r => r.json())
    .then(d => { GOLD = d; renderGold(); })
    .catch(() => {
      const b = document.querySelector('.tab-btn[data-tab="vang"]');
      if (b) b.style.display = "none";
    });

  fetch("../data/gold_history.csv")
    .then(r => { if (!r.ok) throw new Error("x"); return r.text(); })
    .then(text => { GOLD_HIST = parseMktCSV(text); renderGoldCharts(); })
    .catch(() => {});

  fetch("../data/gold_brands.csv")
    .then(r => { if (!r.ok) throw new Error("x"); return r.text(); })
    .then(text => { GOLD_BRANDS = text; })
    .catch(() => {});

  const GOLD_LABELS = {
    sjc_sell: "SJC bán", world_gold_vnd: "Vàng TG quy đổi",
    pct_gap: "% chênh lệch", world_gold_usd: "Vàng TG (USD/oz)", usd_vnd: "USD/VND",
  };
  const GOLD_COLORS = { sjc_sell: "#E8A030", world_gold_vnd: "#3B82F6", pct_gap: "#EF4444" };

  function fmtVnd(v) { return v == null ? "—" : Math.round(v).toLocaleString("vi-VN"); }

  function renderGold() {
    if (!GOLD) return;
    const kpi = [
      ["SJC bán", fmtVnd(GOLD.sjc_sell), "VND/lượng"],
      ["Vàng TG (USD)", GOLD.world_gold_usd == null ? "—" : GOLD.world_gold_usd.toLocaleString("vi-VN"), "USD/oz"],
      ["Vàng TG quy đổi", fmtVnd(GOLD.world_gold_vnd), "VND/lượng"],
      ["Chênh lệch", fmtVnd(GOLD.gap), "VND"],
      ["% chênh lệch", GOLD.pct_gap == null ? "—" : (GOLD.pct_gap * 100).toFixed(2) + "%", ""],
      ["USD/VND", fmtVnd(GOLD.usd_vnd), ""],
    ];
    document.getElementById("goldKpi").innerHTML = kpi.map(([l, v, s]) =>
      `<div class="stat"><div class="stat-label">${l}</div><div class="stat-value">${v}</div><div class="stat-sub">${s}</div></div>`).join("");

    const brands = (GOLD.brands || []);
    document.getElementById("goldBrandGrid").innerHTML = brands.map(b =>
      `<div class="mkt-card"><div class="mkt-label">${b.company}</div>
       <div class="mkt-val">${fmtVnd(b.sell)}<span class="mkt-unit">bán</span></div>
       <div class="mkt-asof">mua ${fmtVnd(b.buy)}</div></div>`).join("");

    document.getElementById("goldNote").innerHTML =
      `Nguồn: bot giá vàng (SJC/DOJI/PNJ/BTMC/BTMH/PhuQuy, vàng TG Yahoo GC=F). Cập nhật ${GOLD.as_of || ""}.`;
  }

  function renderGoldCharts() {
    drawGoldSeries("goldPriceChart", "goldPriceLegend", ["sjc_sell", "world_gold_vnd"]);
    drawGoldSeries("goldGapChart", "goldGapLegend", ["pct_gap"]);
  }

  function drawGoldSeries(canvasId, legendId, keys) {
    if (!GOLD_HIST.length) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas || !canvas.parentElement.clientWidth) return;  // tab ẩn -> bỏ
    const dates = [...new Set(GOLD_HIST.filter(r => keys.includes(r.key)).map(r => r.date))].sort();
    document.getElementById(legendId).innerHTML = keys.map(k =>
      `<span class="lg"><span class="sw" style="background:${GOLD_COLORS[k]}"></span>${GOLD_LABELS[k]}</span>`).join("");
    const series = keys.map(k => {
      const pts = GOLD_HIST.filter(r => r.key === k).sort((a, b) => a.date < b.date ? -1 : 1);
      let pi = 0, last = null;
      const vals = dates.map(d => { while (pi < pts.length && pts[pi].date <= d) { last = pts[pi].value; pi++; } return last; });
      return { color: GOLD_COLORS[k], name: GOLD_LABELS[k] || k, vals };
    });
    interactiveLineChart(canvasId, dates, series, (c, d, s) => drawLineChart(c, d, s, 220));
  }
```

- [ ] **Step 4: Gọi vẽ chart khi mở tab + khi resize**

Tìm hàm `setTab(name)` (gần cuối `<script>`). Ngay trước khi kết thúc thân hàm (sau dòng toggle `.tabpane`), thêm:
```javascript
    if (name === "vang") renderGoldCharts();
```
Và trong handler `window.addEventListener("resize", () => { render(); renderMktChart(); });` đổi thành:
```javascript
  window.addEventListener("resize", () => { render(); renderMktChart(); renderGoldCharts(); });
```

- [ ] **Step 5: Verify trong dev (mở web/index.html qua server tĩnh)**

Vì `web/index.html` fetch `../data/*.csv|json`, cần chạy từ web root. Dùng preview:
- `preview_start` với `{url: "..."}` không phục vụ file local; thay vào đó chạy static server:
Run (background): `python -m http.server 8099` từ thư mục gốc project.
Sau đó `preview_start {url: "http://localhost:8099/web/index.html"}`.
Kiểm tra: click tab "Giá vàng" → thấy 6 KPI, 2 chart vẽ, grid 6 hãng. Dùng `read_console_messages` xác nhận không lỗi JS.

- [ ] **Step 6: Verify prod build (ghép với Task 4)**

Run: `set PYTHONIOENCODING=utf-8 && python scripts/build_static.py --no-sheet`
Rồi `preview_start {url: "http://localhost:8099/dist/dashboard.html"}` → tab "Giá vàng" hiển thị đúng (data nhúng, không cần fetch). Chụp screenshot làm bằng chứng.

- [ ] **Step 7: Commit**

```bash
git add web/index.html
git commit -m "feat(gold): tab Giá vàng (KPI + chart SJC vs TG + %gap + 6 hãng)"
```

---

## Task 6 (Phase 1): Khởi tạo git + repo GitHub private + push

**Files:** (không có file code; thao tác hạ tầng)

**Interfaces:** Sau task này, project là git repo có remote GitHub private, đã push toàn bộ.

> **Việc user làm:** tạo repo (nếu không dùng gh CLI). Claude chuẩn bị commit sẵn.

- [ ] **Step 1: Kiểm tra `.gitignore` che token**

Run: `cat .gitignore`
Expected: có `config.json`. Nếu chưa có `dist/` thì KHÔNG thêm (ta cần commit `dist/dashboard.html` cho Vercel). Đảm bảo `data/*.log` không bắt buộc — có thể thêm `data/crawl.log` vào .gitignore.

- [ ] **Step 2: git init + commit đầu**

```bash
cd "D:/BP/Bros Partners/AI Task/liquidity-crawler"
git init
git add -A
git commit -m "chore: khởi tạo repo liquidity-crawler + tính năng giá vàng"
```

- [ ] **Step 3: Tạo repo GitHub private (2 cách)**

- Nếu có gh CLI: `gh repo create liquidity-crawler --private --source=. --remote=origin --push`
- Nếu KHÔNG: **User** tạo repo trống private tên `liquidity-crawler` trên github.com, rồi:
```bash
git remote add origin https://github.com/<user>/liquidity-crawler.git
git branch -M main
git push -u origin main
```

- [ ] **Step 4: Verify**

Run: `git remote -v` và `git log --oneline -1`
Expected: remote `origin` trỏ GitHub; commit mới nhất đã push (kiểm tra trên github.com).

---

## Task 7 (Phase 1): Vercel deploy tĩnh `dist/`

**Files:**
- Create: `vercel.json`

**Interfaces:** Dashboard hiện tại (kèm tab giá vàng) chạy trên link Vercel; mỗi push → auto-deploy.

- [ ] **Step 1: Build dist mới nhất (có data thật)**

Chạy `python crawl_gold.py --file "D:\BP\Bros Partners\Tickers\PNJ\giá vàng\gold_prices_all.xlsx"` rồi `python scripts/build_static.py` (có sheet nếu config, nếu không `--no-sheet`). Commit `dist/dashboard.html` + `data/gold_*`.

- [ ] **Step 2: Tạo `vercel.json`**

```json
{
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/dashboard.html" }]
}
```

- [ ] **Step 3: Commit + push**

```bash
git add vercel.json dist/dashboard.html data/gold_latest.json data/gold_history.csv data/gold_brands.csv
git commit -m "chore: vercel.json phục vụ dist tĩnh"
git push
```

- [ ] **Step 4: Nối Vercel với repo (User + Claude)**

Trên vercel.com (team `bros-partners`): New Project → Import repo `liquidity-crawler` → Framework Preset **Other** → Build Command **để trống** → Output Directory `dist` → Deploy.
(Vì `dist/dashboard.html` đã commit sẵn, Vercel chỉ phục vụ tĩnh, không cần build.)

- [ ] **Step 5: Verify**

Mở URL Vercel bằng `preview_start {url: "<vercel-url>"}` → dashboard hiển thị, click tab "Giá vàng" OK. `read_console_messages` không lỗi.

---

## Task 8 (Phase 2): `login.py` + session Telegram + GitHub Secrets

**Files:**
- Create: `login.py`

**Interfaces:** Có đủ 4 secret trên GitHub: `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `TG_CHAT` (+ tuỳ chọn `SHEET_ID`).

> **Việc user làm (Claude KHÔNG tự nhập vì liên quan tài khoản):** chạy login.py nhập mã Telegram, dán secrets.

- [ ] **Step 1: Viết `login.py`**

```python
"""Chạy 1 LẦN trên máy local để tạo TG_SESSION (StringSession) cho GitHub Secrets.

    pip install telethon
    python login.py

Nhập API_ID, API_HASH (lấy tại my.telegram.org), rồi số điện thoại + mã Telegram gửi.
In ra chuỗi session (dán vào Secret TG_SESSION) và danh sách group (lấy id cho TG_CHAT).
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n=== TG_SESSION (copy toàn bộ dòng dưới, dán vào GitHub Secret) ===")
    print(client.session.save())
    print("\n=== Group/Channel của bạn — tìm 'Giá vàng PNJ' lấy id cho TG_CHAT ===")
    for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            print(d.id, "|", d.name)
```

- [ ] **Step 2: Commit `login.py`**

```bash
git add login.py
git commit -m "chore(gold): login.py tạo Telegram session (chạy 1 lần)"
git push
```

- [ ] **Step 3: (User) Lấy API_ID/API_HASH + chạy login**

Hướng dẫn user: vào my.telegram.org → API development tools → tạo app → lấy `api_id`, `api_hash`. Rồi:
```
pip install telethon
python login.py
```
Nhập số điện thoại + mã Telegram. Lưu lại: chuỗi session, và id của group "Giá vàng PNJ".

- [ ] **Step 4: (User) Thêm GitHub Secrets**

Repo → Settings → Secrets and variables → Actions → New repository secret, thêm:
`TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `TG_CHAT` (id group), và `SHEET_ID` (id sheet "Banking AI" — để build đọc data bank; xem [[liquidity-crawler-project]]).

- [ ] **Step 5: Verify (local, tạm thời)**

Trên máy local, set 4 biến env tạm rồi chạy `python crawl_gold.py` (không `--file`) để xác nhận session kéo được file thật từ Telegram:
Expected: in `OK gold: as_of=<hôm nay> ...`. (Đây là kiểm chứng session hợp lệ trước khi giao cho Actions.)

---

## Task 9 (Phase 2): GitHub Actions cron

**Files:**
- Create: `.github/workflows/gold.yml`

**Interfaces:** Mỗi ngày 09:20 VN, Actions kéo giá vàng → build → commit → Vercel auto-deploy.

- [ ] **Step 1: Viết `.github/workflows/gold.yml`**

```yaml
name: gold-daily
on:
  schedule:
    - cron: "20 2 * * *"   # 02:20 UTC = 09:20 giờ VN
  workflow_dispatch: {}
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install telethon openpyxl httpx
      - name: Crawl giá vàng từ Telegram
        env:
          TG_API_ID: ${{ secrets.TG_API_ID }}
          TG_API_HASH: ${{ secrets.TG_API_HASH }}
          TG_SESSION: ${{ secrets.TG_SESSION }}
          TG_CHAT: ${{ secrets.TG_CHAT }}
        run: python crawl_gold.py
      - name: Build dashboard (đọc bank/market từ Google Sheet nếu có SHEET_ID)
        env:
          SHEET_ID: ${{ secrets.SHEET_ID }}
        run: python scripts/build_static.py || python scripts/build_static.py --no-sheet
      - name: Commit data + dist
        run: |
          git config user.name "gold-bot"
          git config user.email "actions@users.noreply.github.com"
          git add data/gold_latest.json data/gold_history.csv data/gold_brands.csv dist/dashboard.html
          git diff --cached --quiet || git commit -m "chore: cập nhật giá vàng $(date -u +%F)"
          git push
```

- [ ] **Step 2: Commit + push**

```bash
git add .github/workflows/gold.yml
git commit -m "ci(gold): Actions cron kéo giá vàng + build + deploy"
git push
```

- [ ] **Step 3: Chạy thử thủ công**

Trên GitHub: Actions → `gold-daily` → Run workflow (workflow_dispatch).
Expected: job xanh; log bước Crawl in `OK gold: ...`; có commit mới `chore: cập nhật giá vàng ...` do gold-bot tạo.

- [ ] **Step 4: Verify end-to-end**

Sau khi Actions push commit → Vercel auto-deploy. Mở URL Vercel → tab "Giá vàng" hiển thị data mới nhất. `read_console_messages` không lỗi. Chụp screenshot làm bằng chứng.

- [ ] **Step 5: (Dọn) Xác nhận lịch**

Kiểm tra tab Actions cho thấy lịch cron đã đăng ký. Ghi chú: cron GitHub có thể trễ vài phút — chấp nhận với tần suất ngày.

---

## Self-Review (đã thực hiện khi viết plan)

- **Spec coverage:** parser (§5.1/5.2 → Task 1,2), crawl_gold Telethon+file (§5.1 → Task 3), build_static embed (§5.3 → Task 4), tab web (§5.4 → Task 5), GitHub+Vercel (§5.5 → Task 6,7), login+secrets (§5.6 → Task 8), Actions (§6 → Task 9). Rủi ro §7 phản ánh trong guard parser (`#N/A`/hàng rác), idempotent (`git diff --cached --quiet`), lấy document mới nhất theo tên. Phase 3 (§8) ngoài phạm vi — không có task, đúng chủ ý.
- **Placeholder scan:** không có TBD/TODO; mọi step có lệnh/mã cụ thể.
- **Type consistency:** `parse_gold_xlsx` trả `{latest,history,brands}` dùng nhất quán ở Task 2/3; series_key trong gold_history.csv (`sjc_sell/world_gold_vnd/pct_gap/...`) khớp `GOLD_LABELS`/`GOLD_COLORS`/`drawGoldSeries` ở Task 5; `parseMktCSV` (long format date,series_key,value) tái dùng đúng cho gold_history.
