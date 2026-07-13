"""Adapter MSB (Maritime Bank) — HTML tĩnh, dữ liệu nhúng JSON (httpx, không Playwright).

Trang lãi suất tiết kiệm KHCN chạy WordPress + shortcode 'msb-saving-rate-table'.
Bảng lãi suất KHÔNG render ra <table> trong HTML tĩnh, nhưng TOÀN BỘ dữ liệu được
nhúng sẵn trong thuộc tính `data-config` (JSON) của <div class="msb-saving-rate-table">.

Cấu trúc data-config:
  ratesTableVND: {
    tai_quay:   [{ky_han, LAI_SUAT_CAO_NHAT, ROT_GOC_TUNG_PHAN, DINH_KY_SINH_LOI,
                  TRA_LAI_NGAY, ONG_VANG, HOP_DONG_TIEN_GUI, MANG_NON}, ...],
    truc_tuyen: [ ...cùng cấu trúc... ],
  }
  ky_han: 'RUT_TRUOC_HAN', '1D', '1M', ... '12M', '36M' ...

Ta lấy cột LAI_SUAT_CAO_NHAT (biểu lãi suất niêm yết chuẩn — "Lãi suất cao nhất")
cho cả hai hình thức:
  - tai_quay   -> product='quay'
  - truc_tuyen -> product='online'
Chỉ VND, tiết kiệm cá nhân. Reject rate <=0 hoặc >15.
Đối chiếu web 2026-07: quầy 3M=4.50, 12M=6.50 ; online 3M=4.75, 12M=6.80.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import List

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term

URL = "https://www.msb.com.vn/khach-hang-ca-nhan/lai-suat-tiet-kiem/"

# Cột lãi suất niêm yết chuẩn (headline). Nếu vắng, fallback sang tiền gửi có kỳ hạn.
_RATE_KEYS = ("LAI_SUAT_CAO_NHAT", "ROT_GOC_TUNG_PHAN", "HOP_DONG_TIEN_GUI")

_FORMS = {"tai_quay": "quay", "truc_tuyen": "online"}


class Adapter:
    code = "MSB"
    name = "MSB"

    def __init__(self, headful: bool = False):
        pass  # không cần trình duyệt

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")

        with httpx.Client(http2=False, follow_redirects=True, timeout=20) as client:
            r = client.get(URL, headers=_HEADERS)
            r.raise_for_status()
            html = r.text

        soup = BeautifulSoup(html, "lxml")
        rows: List[RateRow] = []
        seen: set = set()

        for div in soup.select("div.msb-saving-rate-table"):
            raw = div.get("data-config")
            if not raw:
                continue
            try:
                cfg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            table = cfg.get("ratesTableVND") or {}
            for form_key, product in _FORMS.items():
                for entry in table.get(form_key, []):
                    term = parse_term(entry.get("ky_han", ""))
                    if term is None:
                        continue
                    rate = None
                    for k in _RATE_KEYS:
                        v = entry.get(k)
                        if v is not None:
                            rate = v
                            break
                    if rate is None:
                        continue
                    try:
                        rate = round(float(rate), 4)
                    except (TypeError, ValueError):
                        continue
                    if not (0 < rate <= 15):
                        continue
                    row = RateRow(
                        date=today, bank_code=self.code, bank_name=self.name,
                        term=term, rate=rate, product=product,
                        source_url=URL, crawled_at=now,
                    )
                    if row.key() not in seen:
                        seen.add(row.key())
                        rows.append(row)
        return rows
