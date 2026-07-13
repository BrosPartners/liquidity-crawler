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


def test_brand_none_becomes_empty():
    data = {"latest": {}, "history": [], "brands": [
        {"date": "2026-07-13", "company": "SJC", "buy": None, "sell": None},
    ]}
    d = tempfile.mkdtemp()
    write_gold_outputs(data, d)
    with open(os.path.join(d, "gold_brands.csv"), encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["date", "company", "buy", "sell"]
    assert rows[1] == ["2026-07-13", "SJC", "", ""]


if __name__ == "__main__":
    test_writes_three_files()
    test_brand_none_becomes_empty()
    print("Tất cả test PASS")
