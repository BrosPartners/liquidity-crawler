"""Client đẩy data lên Google Sheet qua Apps Script Web App.

Đọc cấu hình từ config.json (xem config.example.json). Nếu chưa cấu hình thì
các hàm push sẽ raise RuntimeError để caller bỏ qua/cảnh báo rõ ràng.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional, Sequence

import httpx

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_ROOT, "config.json")

# gviz CSV endpoint dùng để ĐỌC lại 1 tab (build dashboard từ sheet).
GVIZ = "https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet}"


class SheetConfig:
    def __init__(self, data: dict):
        self.sheet_id: str = data.get("sheet_id", "")
        self.web_app_url: str = data.get("web_app_url", "")
        self.token: str = data.get("token", "")
        self.deposit_product: str = data.get("deposit_product", "online")

    @property
    def can_push(self) -> bool:
        return bool(self.web_app_url) and "DAN_WEB_APP_URL" not in self.web_app_url \
            and bool(self.token) and self.token != "DOI_TOKEN_NAY"


def load_config() -> SheetConfig:
    data = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    # Biến môi trường override (dùng cho GitHub Actions secrets — không commit token)
    for env, key in (("SHEET_ID", "sheet_id"),
                     ("SHEET_WEB_APP_URL", "web_app_url"),
                     ("SHEET_TOKEN", "token")):
        if os.environ.get(env):
            data[key] = os.environ[env]
    return SheetConfig(data)


def push_rows(cfg: SheetConfig, sheet: str, rows: List[Sequence],
              header: Optional[Sequence[str]] = None,
              key_cols: Optional[Sequence[int]] = None,
              timeout: float = 60.0) -> dict:
    """POST 1 batch lên Web App. Trả về dict phản hồi ({ok, appended, updated})."""
    if not cfg.can_push:
        raise RuntimeError("Chưa cấu hình web_app_url/token trong config.json")
    payload = {"token": cfg.token, "sheet": sheet, "rows": [list(r) for r in rows]}
    if header is not None:
        payload["header"] = list(header)
    if key_cols is not None:
        payload["keyCols"] = list(key_cols)
    # Apps Script /exec redirect sang googleusercontent -> follow_redirects
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        resp = c.post(cfg.web_app_url, json=payload)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"ok": False, "error": "non-json response", "text": resp.text[:300]}


def read_tab_csv(cfg: SheetConfig, sheet: str, timeout: float = 60.0) -> str:
    """Đọc 1 tab dưới dạng CSV (yêu cầu sheet đã public/chia sẻ link đọc)."""
    from urllib.parse import quote
    if not cfg.sheet_id:
        raise RuntimeError("Chưa có sheet_id trong config.json")
    url = GVIZ.format(sheet_id=cfg.sheet_id, sheet=quote(sheet))
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.text
