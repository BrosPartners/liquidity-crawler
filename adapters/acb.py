"""Adapter ACB — HTML tĩnh, parse_html tùy chỉnh.

Trang acb.com.vn/lai-suat-tien-gui có 6 bảng; ta lấy:
  - Bảng index 2: lãi suất tại quầy VND — hàng = kỳ hạn, cột 1 = lãi cuối kỳ
  - Bảng index 4: lãi suất Online VND — cột = kỳ hạn, hàng = mức gửi (lấy dòng '< 200')
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup

from adapters.base import BankAdapter
from core.normalize import parse_term, parse_rate


def _cells(tr) -> List[str]:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


class Adapter(BankAdapter):
    code = "ACB"
    name = "ACB"
    url = "https://acb.com.vn/lai-suat-tien-gui"
    mode = "html"

    def parse_html(self, html: str) -> List[Tuple[str, str, float]]:
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        out: List[Tuple[str, str, float]] = []

        # ── Bảng 2: tại quầy VND ──────────────────────────────────────────
        # Bảng có số ô KHÔNG đều giữa các hàng: ô USD chỉ xuất hiện ở vài hàng
        # (rowspan/blank collapse), nên KHÔNG thể dùng index cột cố định.
        # May mắn: USD luôn là 0,00 và parse_rate() trả None cho 0 → lấy
        # rate ĐẦU TIÊN parse được sau cột kỳ hạn = VND lãi cuối kỳ.
        # (Đã đối chiếu web 2026-07: 1T=4.00, 2T=4.20 ... 12T=5.30, 36T=5.40.)
        if len(tables) > 2:
            for tr in tables[2].find_all("tr"):
                cells = _cells(tr)
                if not cells:
                    continue
                term = parse_term(cells[0])
                if term is None:
                    continue
                rate = None
                for cell in cells[1:]:
                    rate = parse_rate(cell)
                    if rate is not None:
                        break
                if rate:
                    out.append((term, "quay", rate))

        # ── Bảng 4: Online VND ───────────────────────────────────────────
        # Row 0: header ["Mức gửi/ TK", "Tiền gửi Online"]
        # Row 1: ["(triệu VND)", "1 – 3 tuần", "1 tháng", "2 tháng", ...]
        # Row 2+: dữ liệu theo mức gửi; lấy dòng đầu tiên (< 200 triệu).
        if len(tables) > 4:
            rows = tables[4].find_all("tr")
            # Tìm dòng header chứa kỳ hạn
            term_header: List[str] = []
            data_row: List[str] = []
            for tr in rows:
                cells = _cells(tr)
                if not cells:
                    continue
                # Dòng header kỳ hạn: ô đầu không parse được thành kỳ hạn
                # nhưng các ô sau thì parse được ("1 – 3 tuần", "1 tháng"...)
                parsed = [parse_term(c) for c in cells[1:]]
                if sum(1 for x in parsed if x) >= 3:
                    term_header = cells
                    continue
                # Dòng dữ liệu đầu tiên sau khi đã có header
                if term_header and not data_row:
                    data_row = cells
            if term_header and data_row:
                for col, header_cell in enumerate(term_header[1:], start=1):
                    term = parse_term(header_cell)
                    if term is None:
                        continue
                    rate = parse_rate(data_row[col]) if col < len(data_row) else None
                    if rate:
                        out.append((term, "online", rate))

        return out
