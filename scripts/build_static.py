"""Build dashboard tĩnh: nhúng data/latest.json + data/history.csv vào web/index.html.

Output 1 file HTML tự chứa (không cần server) — dùng để deploy artifact/share.

    python scripts/build_static.py                    # -> dist/dashboard.html
    python scripts/build_static.py --out path.html
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(_ROOT, "web", "index.html")
LATEST = os.path.join(_ROOT, "data", "latest.json")
HISTORY = os.path.join(_ROOT, "data", "history.csv")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_ROOT, "dist", "dashboard.html"))
    ap.add_argument("--no-sheet", action="store_true",
                    help="Bỏ qua Google Sheet, chỉ dùng file cục bộ")
    args = ap.parse_args()

    with open(WEB, encoding="utf-8") as f:
        html = f.read()
    with open(LATEST, encoding="utf-8") as f:
        latest = f.read().strip()
    history = ""
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as f:
            history = f.read()

    mkt_latest = "null"
    mkt_path = os.path.join(_ROOT, "data", "market_latest.json")
    if os.path.exists(mkt_path):
        with open(mkt_path, encoding="utf-8") as f:
            mkt_latest = f.read().strip()
    mkt_history = ""
    mkt_hist_path = os.path.join(_ROOT, "data", "market_history.csv")
    if os.path.exists(mkt_hist_path):
        with open(mkt_hist_path, encoding="utf-8") as f:
            mkt_history = f.read()

    # ── Ưu tiên NGUỒN GỐC là Google Sheet (nếu cấu hình sheet_id) ──────────
    if not args.no_sheet:
        try:
            from core.sheet_client import load_config
            from scripts import sheet_source as ss
            cfg = load_config()
            if cfg.sheet_id:
                dep = ss.deposit_from_sheet(cfg)
                if dep:
                    latest, history = dep[0], dep[1]
                    print("[sheet] deposit: lấy từ 'Auto - Deposit'")
                mkt = ss.assemble_market(cfg, mkt_latest, mkt_history)
                if mkt:
                    mkt_latest, mkt_history = mkt[0], mkt[1]
                    print("[sheet] market: ghép local + 'Auto - Market' + lịch sử 'ON rate'")
        except Exception as e:
            print(f"[sheet] bỏ qua, dùng file cục bộ: {type(e).__name__}: {e}",
                  file=sys.stderr)

    # 1. Thay fetch(DATA_URL) chain bằng data nhúng
    latest_fetch = re.compile(
        r'fetch\(DATA_URL\)\s*\.then\(r => r\.json\(\)\)\s*\.then\(d => \{',
    )
    if not latest_fetch.search(html):
        print("[ERR] không tìm thấy fetch(DATA_URL) trong web/index.html", file=sys.stderr)
        return 1
    html = latest_fetch.sub("Promise.resolve(__EMBED_LATEST__).then(d => {", html, count=1)

    # 2. Thay fetch history.csv bằng text nhúng
    hist_fetch = re.compile(
        r'fetch\("\.\./data/history\.csv"\)\s*'
        r'\.then\(r => \{ if \(!r\.ok\) throw new Error\("HTTP " \+ r\.status\); return r\.text\(\); \}\)\s*'
        r'\.then\(text => \{'
    )
    if not hist_fetch.search(html):
        print("[ERR] không tìm thấy fetch history.csv trong web/index.html", file=sys.stderr)
        return 1
    html = hist_fetch.sub("Promise.resolve(__EMBED_HISTORY__).then(text => {", html, count=1)

    # 3. Thay 2 fetch market bằng data nhúng
    html = re.sub(
        r'fetch\("\.\./data/market_latest\.json"\)\s*\.then\(r => r\.json\(\)\)',
        "Promise.resolve(__EMBED_MKT_LATEST__)", html, count=1)
    html = re.sub(
        r'fetch\("\.\./data/market_history\.csv"\)\s*'
        r'\.then\(r => \{ if \(!r\.ok\) throw new Error\("x"\); return r\.text\(\); \}\)',
        "Promise.resolve(__EMBED_MKT_HISTORY__)", html, count=1)

    # 4. Chèn data ngay đầu <script>
    embed = (
        "<script>\n"
        f"const __EMBED_LATEST__ = {latest};\n"
        f"const __EMBED_HISTORY__ = {json.dumps(history, ensure_ascii=False)};\n"
        f"const __EMBED_MKT_LATEST__ = {mkt_latest};\n"
        f"const __EMBED_MKT_HISTORY__ = {json.dumps(mkt_history, ensure_ascii=False)};\n"
    )
    html = html.replace("<script>", embed, 1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK -> {args.out}  ({len(html)//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
