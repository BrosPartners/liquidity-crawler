"""Thu thập giá vàng: tải gold_prices_all.xlsx mới nhất từ Telegram group -> JSON/CSV.

  python crawl_gold.py --file "C:/path/gold_prices_all.xlsx"   # dùng file local (test)
  python crawl_gold.py                                          # kéo từ Telegram (mặc định)

Env (chế độ Telegram): TG_API_ID, TG_API_HASH, TG_SESSION, TG_CHAT
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.gold_parse import parse_gold_xlsx
from core.gold_sink import write_gold_outputs

_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_ROOT, "data")
FILENAME = "gold_prices_all.xlsx"


def fetch_from_telegram(dest, candidates=5):
    """Tải gold_prices_all.xlsx mới nhất từ Telegram group.

    Có 1 bot CŨ (cùng token, chạy ở máy/VPS khác chưa xác định) vẫn gửi file
    trùng tên vào cùng group mỗi ngày với dữ liệu CŨ (cache/lỗi phía nó) — nếu
    chỉ lấy tin nhắn gửi GẦN ĐÂY NHẤT theo thời gian, có ngày sẽ ăn nhầm bản
    cũ này (as_of bị kẹt lại). Vì cả 2 file đều tên "gold_prices_all.xlsx" nên
    không phân biệt được qua sender — phải tải vài bản gần nhất, PARSE THỬ
    từng bản và chọn bản có as_of (nội dung thực) MỚI NHẤT, bất kể thứ tự gửi.
    """
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"]
    chat = os.environ["TG_CHAT"]
    try:
        chat_id = int(chat)
    except ValueError:
        chat_id = None
    with TelegramClient(StringSession(session), api_id, api_hash) as client:
        # StringSession không cache entity giữa các process (vd GitHub Actions),
        # nên resolve nhóm qua danh sách hội thoại trước (theo id, fallback theo tên).
        target = None
        for d in client.iter_dialogs():
            if chat_id is not None and d.id == chat_id:
                target = d.entity
                break
            if chat_id is None and (d.name or "") == chat:
                target = d.entity
                break
        if target is None:
            target = chat_id if chat_id is not None else chat

        best_path = None
        best_as_of = None
        n_checked = 0
        for msg in client.iter_messages(target, limit=60):
            if not msg.document:
                continue
            name = next((a.file_name for a in msg.document.attributes
                         if getattr(a, "file_name", None)), None)
            if name != FILENAME:
                continue
            n_checked += 1
            cand = f"{dest}.cand{n_checked}"
            saved = client.download_media(msg, cand)
            as_of = None
            if not saved or not os.path.exists(cand) or os.path.getsize(cand) == 0:
                print(f"[tg] tin #{n_checked} (msg {msg.id}, {msg.date}): "
                      f"download_media tra ve {saved!r}, file ton tai={os.path.exists(cand)}",
                      file=sys.stderr)
            else:
                try:
                    as_of = parse_gold_xlsx(cand)["latest"]["as_of"]
                except Exception as e:
                    print(f"[tg] tin #{n_checked}: loi parse ({os.path.getsize(cand)} bytes): "
                          f"{type(e).__name__}: {e}", file=sys.stderr)
            print(f"[tg] tin #{n_checked} (msg {msg.id}, {msg.date}): as_of={as_of}")
            if as_of and (best_as_of is None or as_of > best_as_of):
                best_as_of, best_path = as_of, cand
            if n_checked >= candidates:
                break
        if best_path is None:
            raise RuntimeError(f"Không thấy {FILENAME} trong 60 tin gần nhất của chat {chat}")
        print(f"[tg] chọn bản as_of={best_as_of} (mới nhất theo NỘI DUNG, không theo thời gian gửi)")
        for i in range(1, n_checked + 1):
            cand = f"{dest}.cand{i}"
            if cand != best_path and os.path.exists(cand):
                os.remove(cand)
        os.replace(best_path, dest)
        return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Dùng file xlsx local thay vì kéo Telegram")
    args = ap.parse_args()

    path = args.file or os.path.join(tempfile.gettempdir(), FILENAME)
    if not args.file:
        fetch_from_telegram(path)

    data = parse_gold_xlsx(path)
    write_gold_outputs(data, DATA_DIR)
    lt = data["latest"]
    print(f"OK gold: as_of={lt['as_of']} SJC bán={lt['sjc_sell']} "
          f"vàng TG(USD)={lt['world_gold_usd']} USD/VND={lt['usd_vnd']} "
          f"{len(data['history'])} ngày, {len(lt['brands'])} hãng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
