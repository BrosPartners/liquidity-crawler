"""Adapter OCB (Ngân hàng Phương Đông) — HTML tĩnh (SSR / Angular Universal).

⚠️ SỬA 2026-09-12: URL cũ `https://www.ocb.com.vn/vi/cong-cu/lai-suat` giờ trả
về TRANG 404 (nhưng HTTP status vẫn 200/302, không raise lỗi) cho MỌI request
trực tiếp (đã kiểm tra: httpx, curl, và cả Playwright/browser thật — không
phải do bị chặn IP của CI). Trang đó chỉ còn vào được qua điều hướng nội bộ
của SPA (bấm link trong app), không còn route trực tiếp nào cho nó.

Fix: widget lãi suất TIẾT KIỆM rút gọn (3 kỳ hạn: 1/6/12 tháng, thay vì 5 kỳ
hạn của trang cũ) nằm NGAY TRÊN TRANG CHỦ cá nhân — `/vi/ca-nhan` — vẫn server-
render bình thường (không 404), lấy được qua httpx.

Trang chưa hydrate JS nên header/nhãn ở dạng KHOÁ i18n CHƯA DỊCH (vd
"SHORT_1_MONTH", "NORMALLY", "Online") thay vì tiếng Việt — đây thực ra là lợi
thế: các khoá này ổn định hơn văn bản dịch (không đổi theo bản dịch/A-B test),
nên _parse() ưu tiên nhận diện qua khoá, có fallback tiếng Việt qua
core.normalize.parse_term() phòng khi OCB đổi cách server-render.

Bảng lấy được (2026-09-12), đúng 3 dòng dữ liệu + 1 dòng header:
    SAVING_TYPE | SHORT_1_MONTH | SHORT_6_MONTH | SHORT_12_MONTH
    PERIOD      | 4.75          | 6.4           | 6.7             ← bỏ (trùng NORMALLY, xem dưới)
    NORMALLY    | 4.75          | 6.4           | 6.7             → product="quay"
    Online      | 4.75          | 6.5           | 6.8             → product="online"

Hàng "PERIOD" ("Tiền gửi có kỳ hạn") trùng giá trị với "NORMALLY" ("Tiết kiệm
thông thường") — giữ nguyên quyết định cũ: bỏ qua, không tính 2 lần.

Đánh đổi đã biết: chỉ còn 3 kỳ hạn (1M/6M/12M) thay vì 5 (1M/3M/6M/12M/36M) của
trang cũ — trang chủ không có kỳ hạn 3M/36M. Chấp nhận được vì mục tiêu chính
là không để OCB biến mất khỏi dashboard; có kỳ hạn còn hơn không có dữ liệu.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from adapters.base import _HEADERS
from core.schema import RateRow
from core.normalize import parse_term, parse_rate, norm_text

URL = "https://ocb.com.vn/vi/ca-nhan"

# Khoá i18n CHƯA DỊCH cho 3 kỳ hạn hiện có trên widget trang chủ.
_SHORT_MONTH_RE = re.compile(r"short_(\d+)_month")


def _cells(tr) -> List[str]:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


def _term_from_header(raw: str) -> str | None:
    """Nhận khoá i18n ('SHORT_12_MONTH') LẪN văn bản tiếng Việt ('12 tháng')."""
    m = _SHORT_MONTH_RE.search(norm_text(raw))
    if m:
        return f"{int(m.group(1))}M"
    return parse_term(raw)


class Adapter:
    code = "OCB"
    name = "OCB"

    def __init__(self, headful: bool = False):
        pass  # headful không dùng, giữ tương thích interface

    def _get_html(self) -> str:
        last = None
        with httpx.Client(http2=False, follow_redirects=True, timeout=90) as client:
            for _ in range(3):
                try:
                    r = client.get(URL, headers=_HEADERS)
                    r.raise_for_status()
                    return r.text
                except Exception as e:  # trang OCB thỉnh thoảng timeout — thử lại
                    last = e
        raise last

    def _parse(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        out: List[Tuple[str, str, float]] = []

        for tb in soup.find_all("table"):
            rows = tb.find_all("tr")
            if not rows:
                continue
            header = _cells(rows[0])
            if not header:
                continue
            hnorm = [norm_text(h) for h in header]
            # Nhận diện đúng bảng tiết kiệm: cột đầu là "saving_type" (khoá)
            # HOẶC chứa "tiet kiem"/"ky han" (nếu đã dịch).
            if not (hnorm[0] == "saving_type" or "tiet kiem" in hnorm[0] or "ky han" in hnorm[0]):
                continue

            term_cols = [(i, _term_from_header(h)) for i, h in enumerate(header) if i > 0]
            term_cols = [(i, t) for i, t in term_cols if t is not None]
            if not term_cols:
                continue

            for tr in rows[1:]:
                cells = _cells(tr)
                if not cells or not cells[0]:
                    continue
                label = norm_text(cells[0])
                if label == "period":               # trùng "normally" — bỏ
                    continue
                if label == "normally" or "thong thuong" in label:
                    product = "quay"
                elif label == "online":
                    product = "online"
                else:
                    continue

                for col, term in term_cols:
                    if col >= len(cells):
                        continue
                    rate = parse_rate(cells[col])  # loại 0 và ngoài (0,15]
                    if rate:
                        out.append((term, product, rate))
            break  # chỉ có 1 bảng tiết kiệm trên trang này

        return out

    def fetch(self) -> List[RateRow]:
        today = _dt.date.today().isoformat()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        html = self._get_html()
        rows: List[RateRow] = []
        seen: set = set()
        for term, product, rate in self._parse(html):
            r = RateRow(
                date=today, bank_code=self.code, bank_name=self.name,
                term=term, rate=rate, product=product,
                source_url=URL, crawled_at=now,
            )
            if r.key() not in seen:
                seen.add(r.key())
                rows.append(r)
        return rows
