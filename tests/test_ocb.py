"""Adapter OCB — sau khi URL cũ (/vi/cong-cu/lai-suat) bị 404, chuyển sang
widget rút gọn trên trang chủ /vi/ca-nhan (2026-09-12). Header/nhãn ở dạng
KHOÁ i18n chưa dịch (SAVING_TYPE, SHORT_1_MONTH, NORMALLY, Online...) — đây
là fixture RÚT GỌN từ HTML thật lấy về ngày 2026-09-12, để chặn regression
nếu ai lỡ sửa lại parser theo văn bản tiếng Việt (server không dịch, luôn trả
khoá thô cho crawler tĩnh không chạy JS)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from adapters.ocb import Adapter

# Rút gọn từ HTML thật — giữ nguyên cấu trúc bảng + 1 bảng nhiễu (tỷ giá) để
# test luôn việc chỉ lấy đúng 1 bảng tiết kiệm, bỏ qua bảng khác.
SAMPLE_UNTRANSLATED = """
<html><body>
<table>
  <tr><td>SAVING_TYPE</td><td>SHORT_1_MONTH</td><td>SHORT_6_MONTH</td><td>SHORT_12_MONTH</td></tr>
  <tr><td>PERIOD</td><td>4.75</td><td>6.4</td><td>6.7</td></tr>
  <tr><td>NORMALLY</td><td>4.75</td><td>6.4</td><td>6.7</td></tr>
  <tr><td>Online</td><td>4.75</td><td>6.5</td><td>6.8</td></tr>
  <tr><td></td><td></td><td></td><td></td></tr>
</table>
<table>
  <tr><td>CURRENCY</td><td>CASH_BUYING</td><td>TRANSFER_BUYING</td><td>SELL</td></tr>
  <tr><td>USD100</td><td>25,680</td><td>25,730</td><td>26,130</td></tr>
</table>
</body></html>
"""

# Nếu OCB đổi sang server-render đã dịch tiếng Việt thì phải vẫn ra kết quả
# giống hệt — parser có fallback qua parse_term()/norm_text().
SAMPLE_TRANSLATED = """
<html><body>
<table>
  <tr><th>Loại tiết kiệm</th><th>1 tháng</th><th>6 tháng</th><th>12 tháng</th></tr>
  <tr><td>Kỳ hạn</td><td>4.75</td><td>6.4</td><td>6.7</td></tr>
  <tr><td>Thông thường</td><td>4.75</td><td>6.4</td><td>6.7</td></tr>
  <tr><td>Online</td><td>4.75</td><td>6.5</td><td>6.8</td></tr>
</table>
</body></html>
"""

EXPECTED = {
    ("1M", "quay"): 4.75, ("6M", "quay"): 6.4, ("12M", "quay"): 6.7,
    ("1M", "online"): 4.75, ("6M", "online"): 6.5, ("12M", "online"): 6.8,
}


def _as_dict(rows):
    return {(term, product): rate for term, product, rate in rows}


def test_parse_untranslated_i18n_keys():
    a = Adapter()
    rows = a._parse(SAMPLE_UNTRANSLATED)
    assert _as_dict(rows) == EXPECTED


def test_parse_translated_vietnamese_fallback():
    a = Adapter()
    rows = a._parse(SAMPLE_TRANSLATED)
    assert _as_dict(rows) == EXPECTED


def test_period_row_not_double_counted():
    """'PERIOD' ('Tiền gửi có kỳ hạn') trùng giá trị NORMALLY — không tính 2 lần."""
    a = Adapter()
    rows = a._parse(SAMPLE_UNTRANSLATED)
    assert len(rows) == 6  # đúng 3 kỳ hạn x 2 sản phẩm, không x3


def test_only_savings_table_picked_not_fx_table():
    """Bảng tỷ giá (CURRENCY/CASH_BUYING...) đứng sau — không được lẫn vào."""
    a = Adapter()
    rows = a._parse(SAMPLE_UNTRANSLATED)
    for term, product, rate in rows:
        assert product in ("quay", "online")
        assert rate <= 15  # loại nếu lỡ đọc nhầm số tỷ giá (25,680 v.v.)


def test_no_table_returns_empty_not_error():
    a = Adapter()
    assert a._parse("<html><body>Không có bảng nào</body></html>") == []
