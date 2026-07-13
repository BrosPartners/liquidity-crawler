"""Chạy 1 LẦN trên máy local để tạo TG_SESSION (StringSession) cho GitHub Secrets.

    pip install telethon
    python login.py

Nhập API_ID, API_HASH (lấy tại https://my.telegram.org → API development tools),
rồi số điện thoại + mã Telegram gửi cho bạn.
In ra:
  - chuỗi session  -> dán vào GitHub Secret TG_SESSION
  - danh sách group -> lấy id của "Giá vàng PNJ" cho TG_CHAT
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n=== TG_SESSION (copy TOÀN BỘ dòng dưới, dán vào GitHub Secret) ===")
    print(client.session.save())
    print("\n=== Group/Channel của bạn — tìm 'Giá vàng PNJ' lấy id cho TG_CHAT ===")
    for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            print(d.id, "|", d.name)
