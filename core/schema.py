"""Schema chuẩn cho 1 dòng lãi suất huy động — dùng chung cho JSON, CSV, Sheet, DB."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional


# Kỳ hạn chuẩn hoá (canonical). Thứ tự này dùng để sort khi hiển thị.
TERM_ORDER = [
    "KKH",  # không kỳ hạn
    "1W", "2W", "3W",
    "1M", "2M", "3M", "4M", "5M", "6M", "7M", "8M", "9M", "10M", "11M",
    "12M", "13M", "15M", "18M", "24M", "36M", "60M",
]


@dataclass
class RateRow:
    date: str               # YYYY-MM-DD (ngày áp dụng / ngày crawl)
    bank_code: str          # VCB, TCB, VPB ...
    bank_name: str
    term: str               # đã chuẩn hoá: KKH, 1M, 12M ...
    rate: Optional[float]   # %/năm; None nếu bank không niêm yết kỳ hạn đó
    product: str = "quay"   # "quay" (tại quầy) | "online"
    method: str = "cuoi_ky" # cách trả lãi; mặc định lĩnh lãi cuối kỳ
    currency: str = "VND"
    source_url: str = ""
    crawled_at: str = ""    # ISO timestamp

    def key(self) -> str:
        """Khoá định danh 1 mức lãi suất — dùng để phát hiện thay đổi."""
        return f"{self.bank_code}|{self.term}|{self.product}|{self.method}|{self.currency}"

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def term_rank(self) -> int:
        return TERM_ORDER.index(self.term) if self.term in TERM_ORDER else 999
