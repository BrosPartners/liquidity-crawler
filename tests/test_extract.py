"""Test nhanh bộ trích bảng + chuẩn hoá với bảng HTML mô phỏng bank VN."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.extract import extract_rates
from core.normalize import parse_term, parse_rate

SAMPLE = """
<html><body>
<h2>Tỷ giá</h2>
<table><tr><th>Ngoại tệ</th><th>Mua</th><th>Bán</th></tr>
<tr><td>USD</td><td>25.100</td><td>25.400</td></tr></table>

<h2>Biểu lãi suất tiền gửi VND</h2>
<table>
  <tr><th>Kỳ hạn</th><th>Tại quầy (%/năm)</th><th>Online (%/năm)</th></tr>
  <tr><td>Không kỳ hạn</td><td>0,10</td><td>0,10</td></tr>
  <tr><td>1 tháng</td><td>2,60</td><td>2,80</td></tr>
  <tr><td>3 tháng</td><td>2,90</td><td>3,10</td></tr>
  <tr><td>6 tháng</td><td>3,90</td><td>4,10</td></tr>
  <tr><td>12 tháng</td><td>4,70</td><td>4,90</td></tr>
  <tr><td>24 tháng</td><td>4,80</td><td>5,00</td></tr>
</table>
</body></html>
"""


def test_normalize():
    assert parse_term("12 tháng") == "12M"
    assert parse_term("Không kỳ hạn") == "KKH"
    assert parse_term("1 tuần") == "1W"
    assert parse_rate("6,60 %/năm") == 6.6
    assert parse_rate("-") is None
    assert parse_rate("99") is None  # ngoài ngưỡng hợp lệ


def test_extract_picks_rate_table():
    rows = extract_rates(SAMPLE)
    # Không được dính bảng tỷ giá USD
    assert all(t in {"KKH","1M","3M","6M","12M","24M"} for t, _, _ in rows)
    quay = {t: r for t, p, r in rows if p == "quay"}
    online = {t: r for t, p, r in rows if p == "online"}
    assert quay["12M"] == 4.7 and online["12M"] == 4.9
    assert quay["KKH"] == 0.10
    print(f"OK: trích {len(rows)} mức; 12M quầy={quay['12M']} online={online['12M']}")


if __name__ == "__main__":
    test_normalize()
    test_extract_picks_rate_table()
    print("Tất cả test PASS")
