"""Schema cho dữ liệu thị trường tiền tệ vĩ mô (không phải lãi suất huy động per-bank).

Gồm: lãi suất liên ngân hàng qua đêm, lãi suất điều hành SBV (OMO, tín phiếu,
chiết khấu, tái cấp vốn), tỷ giá, tăng trưởng tín dụng/M2, dự trữ ngoại hối.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


# Nhóm hiển thị (category) → thứ tự
CATEGORY_ORDER = ["lien_nh", "dieu_hanh", "huy_dong", "ty_gia", "tang_truong", "khac"]

# Map tên series ở nguồn (VietnamBiz) → (series_key chuẩn, category, unit)
SERIES_MAP = {
    "Lãi suất liên ngân hàng _ON":              ("interbank_on",   "lien_nh",     "%/năm"),
    # Kỳ hạn liên NH đầy đủ (nguồn Vietstock VNIBOR) — chỉ để tham chiếu, adapter tự set:
    "Lãi suất liên ngân hàng _1W":              ("interbank_1w",   "lien_nh",     "%/năm"),
    "Lãi suất liên ngân hàng _2W":              ("interbank_2w",   "lien_nh",     "%/năm"),
    "Lãi suất liên ngân hàng _1M":              ("interbank_1m",   "lien_nh",     "%/năm"),
    "Lãi suất liên ngân hàng _3M":              ("interbank_3m",   "lien_nh",     "%/năm"),
    "Lãi suất OMO":                             ("omo_rate",       "dieu_hanh",   "%/năm"),
    "Lãi suất tín phiếu":                       ("tin_phieu_rate", "dieu_hanh",   "%/năm"),
    "Lãi suất chiết khấu":                      ("discount_rate",  "dieu_hanh",   "%/năm"),
    "Lãi suất tái cấp vốn":                     ("refi_rate",      "dieu_hanh",   "%/năm"),
    "Lãi suất huy động 1-3 tháng nhóm NHTM lớn":("dep_1_3m",       "huy_dong",    "%/năm"),
    "Lãi suất huy động 6-9 tháng nhóm NHTM lớn":("dep_6_9m",       "huy_dong",    "%/năm"),
    "Lãi suất huy động 12 tháng nhóm NHTM lớn": ("dep_12m",        "huy_dong",    "%/năm"),
    "Tỷ giá trung tâm":                         ("fx_central",     "ty_gia",      "VND/USD"),
    "Tỷ giá USD NHTM bán ra":                   ("fx_bank_sell",   "ty_gia",      "VND/USD"),
    "Tỷ giá USD tự do bán ra":                  ("fx_free_sell",   "ty_gia",      "VND/USD"),
    "Tăng trưởng cung tiền M2 (YoY)":           ("m2_yoy",         "tang_truong", "%"),
    "Tăng trưởng huy động (YoY)":               ("deposit_yoy",    "tang_truong", "%"),
    "Tăng trưởng tín dụng (YoY)":               ("credit_yoy",     "tang_truong", "%"),
    "Dự trữ ngoại hối (Triệu USD)":             ("fx_reserves",    "khac",        "Triệu USD"),
}


@dataclass
class MarketRow:
    date: str               # ngày crawl (YYYY-MM-DD)
    series_key: str         # interbank_on, omo_rate, ...
    label: str              # tên hiển thị tiếng Việt
    value: Optional[float]
    unit: str = ""
    category: str = "khac"  # lien_nh | dieu_hanh | huy_dong | ty_gia | tang_truong | khac
    as_of: str = ""         # ngày nguồn công bố (chuỗi gốc, vd "Ngày 02/07/2026")
    source_url: str = ""
    crawled_at: str = ""

    def key(self) -> str:
        return self.series_key

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def cat_rank(self) -> int:
        return CATEGORY_ORDER.index(self.category) if self.category in CATEGORY_ORDER else 999
