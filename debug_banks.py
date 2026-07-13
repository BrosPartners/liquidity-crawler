"""Inspect CTG, AGR, VPB, HDB table structure — UTF-8 safe."""
import sys, httpx, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,*/*",
}
client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20, http2=False)

for code, url in [
    ("CTG", "https://www.vietinbank.vn/ca-nhan/cong-cu-tien-ich/lai-suat-khcn"),
    ("AGR", "https://www.agribank.com.vn/en/lai-suat"),
]:
    print(f"\n=== {code} ===")
    r = client.get(url)
    soup = BeautifulSoup(r.text, "lxml")
    for i, t in enumerate(soup.find_all("table")[:3]):
        rows = t.find_all("tr")
        print(f"  [Bang {i}] {len(rows)} rows")
        for tr in rows[:7]:
            cells = [c.get_text(" ", strip=True)[:30] for c in tr.find_all(["td","th"])]
            print(f"    {cells}")

client.close()
