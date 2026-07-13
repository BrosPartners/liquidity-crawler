"""Chuẩn hoá chuỗi tiếng Việt về schema: kỳ hạn, lãi suất, loại sản phẩm."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def norm_text(s: str) -> str:
    """Bỏ dấu, lowercase, gọn khoảng trắng — để so khớp header/nhãn ổn định."""
    return re.sub(r"\s+", " ", _strip_accents(s or "").lower()).strip()


def parse_term(raw: str) -> Optional[str]:
    """'12 tháng' -> '12M', '1 tuần' -> '1W', 'Không kỳ hạn' -> 'KKH'."""
    t = norm_text(raw)
    if not t:
        return None
    if "khong ky han" in t or t in {"kkh", "ko ky han"}:
        return "KKH"
    m = re.search(r"(\d+)\s*(tuan|week|w)\b", t)
    if m:
        return f"{int(m.group(1))}W"
    m = re.search(r"(\d+)\s*(ngay|day|d)\b", t)
    if m:
        return f"{int(m.group(1))}D"
    m = re.search(r"(\d+)\s*(thang|month|m)\b", t)
    if m:
        return f"{int(m.group(1))}M"
    # Viết tắt không dấu cách: "1t", "12t", "6t" (ACB, nhiều bank dùng)
    m = re.fullmatch(r"(\d{1,2})t", t)
    if m:
        return f"{int(m.group(1))}M"
    # Chuỗi chỉ có số (cột kỳ hạn đã ngầm hiểu là tháng)
    m = re.fullmatch(r"(\d{1,2})", t)
    if m:
        return f"{int(m.group(1))}M"
    return None


def parse_rate(raw) -> Optional[float]:
    """'6,60 %/năm' -> 6.6 ; '-' / '' / 'NA' -> None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "--", "n/a", "na", "x"}:
        return None
    # Reject label cells: string starts with letters before any digit (e.g. "LS12\nloại 1")
    if re.match(r"^[A-Za-z]", s):
        return None
    s = s.replace("%", "").replace("/nam", "").replace("/năm", "")
    s = s.replace(",", ".").strip()
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    val = float(m.group(0))
    # Lọc nhiễu: lãi suất huy động VND hợp lệ ~ (0, 15]
    return val if 0 < val <= 15 else None


def detect_product(label: str) -> str:
    """Đoán 'online' vs 'quay' từ nhãn cột/tiêu đề."""
    t = norm_text(label)
    if "online" in t or "truc tuyen" in t or "ebank" in t or "digital" in t:
        return "online"
    return "quay"
