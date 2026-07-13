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
