"""Chạy crawler: nạp adapter theo config -> fetch -> ghi data/ (+Sheet nếu cấu hình).

    python run.py                      # tất cả bank enabled
    python run.py --banks VCB,TCB      # chỉ vài bank
    python run.py --headful            # mở trình duyệt thật để debug selector
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import os
import sys

import yaml

from core import sink

# Windows console mặc định cp1252 -> ép UTF-8 để in tiếng Việt không vỡ.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

CONFIG = os.path.join(os.path.dirname(__file__), "config", "banks.yaml")


def load_banks(only: set[str] | None):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for b in cfg.get("banks", []):
        if only is not None:
            if b["code"] not in only:
                continue
        elif not b.get("enabled"):
            continue
        yield b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", help="Danh sách code, vd VCB,TCB")
    ap.add_argument("--headful", action="store_true", help="Mở trình duyệt thật")
    args = ap.parse_args()

    only = {c.strip().upper() for c in args.banks.split(",")} if args.banks else None

    all_rows = []
    for b in load_banks(only):
        code = b["code"]
        try:
            mod = importlib.import_module(f"adapters.{b['module']}")
            adapter = mod.Adapter(headful=args.headful)
            rows = adapter.fetch()
            print(f"[OK]   {code}: {len(rows)} mức lãi suất")
            all_rows.extend(rows)
        except Exception as e:  # 1 bank lỗi không kéo đổ cả hệ thống
            print(f"[FAIL] {code}: {type(e).__name__}: {e}", file=sys.stderr)

    if not all_rows:
        print("Không thu được dữ liệu nào.", file=sys.stderr)
        return 1

    now = _dt.datetime.now().isoformat(timespec="seconds")
    sink.write_json(all_rows, generated_at=now)
    n_changed = sink.append_history_on_change(all_rows)
    try:
        sink.write_sheet(all_rows)
    except Exception as e:
        print(f"[warn] ghi Google Sheet lỗi (bỏ qua): {e}", file=sys.stderr)

    print(f"Tổng {len(all_rows)} mức từ {len({r.bank_code for r in all_rows})} bank. "
          f"{n_changed} mức thay đổi -> ghi history.csv. Xem data/latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
