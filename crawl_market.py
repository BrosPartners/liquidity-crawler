"""Crawl data thị trường tiền tệ vĩ mô (liên NH, điều hành SBV, tỷ giá...).

    python crawl_market.py

Ghi data/market_latest.json + append data/market_history.csv (khi đổi).
Chạy chung lịch 17:00 với run.py (xem run_daily.bat).
"""
from __future__ import annotations

import datetime as _dt
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from adapters.vietnambiz_market import Adapter
from adapters.vietstock_interbank import Adapter as VniborAdapter
from core import market_sink, vnindex_sink


def main() -> int:
    # Nguồn chính: VietnamBiz (OMO/tín phiếu/tỷ giá/vĩ mô + interbank_on).
    try:
        rows = Adapter().fetch()
    except Exception as e:
        print(f"[FAIL] MARKET (VietnamBiz): {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # Nguồn bổ sung: Vietstock VNIBOR đủ kỳ hạn liên NH (ON/1W/2W/1M/3M).
    # Ưu tiên hơn VietnamBiz cho category lien_nh; lỗi/timeout thì bỏ qua, không đổ cả.
    try:
        vnibor_rows = VniborAdapter().fetch()
    except Exception as e:
        print(f"[WARN] Vietstock VNIBOR bỏ qua: {type(e).__name__}: {e}", file=sys.stderr)
        vnibor_rows = []

    if vnibor_rows:
        override = {r.series_key for r in vnibor_rows}
        # bỏ các key liên NH mà Vietstock đã cung cấp (vd interbank_on trùng)
        rows = [r for r in rows if r.series_key not in override]
        rows.extend(vnibor_rows)
        print(f"[OK]   Vietstock VNIBOR: {len(vnibor_rows)} kỳ hạn liên NH "
              f"({', '.join(sorted(override))})", file=sys.stderr)

    if not rows:
        print("Không thu được series nào.", file=sys.stderr)
        return 1

    for r in sorted(rows, key=lambda r: (r.cat_rank, r.series_key)):
        print(f"[OK]   {r.series_key:16} {r.value!s:10} {r.unit:9} ({r.as_of})")

    now = _dt.datetime.now().isoformat(timespec="seconds")
    market_sink.write_json(rows, generated_at=now)
    n = market_sink.append_history_on_change(rows)
    print(f"\nTổng {len(rows)} chỉ tiêu. {n} đổi -> market_history.csv. Xem data/market_latest.json")

    # VN-Index (Vietstock) — merge tăng dần, không liên quan MarketRow ở trên.
    try:
        total, changed = vnindex_sink.update()
        print(f"[OK]   VN-Index: {total} phiên trong file, {changed} phiên mới/đổi")
    except Exception as e:
        print(f"[WARN] VN-Index bỏ qua: {type(e).__name__}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
