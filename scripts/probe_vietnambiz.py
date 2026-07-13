"""Probe cấu trúc __NEXT_DATA__ của data.vietnambiz.vn/currency-interest-rate."""
import json, re, sys
import httpx

URL = "https://data.vietnambiz.vn/currency-interest-rate"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Accept-Language": "vi-VN,vi;q=0.9"}

r = httpx.get(URL, headers=HDR, follow_redirects=True, timeout=30)
print("HTTP", r.status_code, "len", len(r.text), file=sys.stderr)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
if not m:
    print("NO __NEXT_DATA__", file=sys.stderr); sys.exit(1)
data = json.loads(m.group(1))

# Đi đệ quy tìm mọi object có 'value' + ('title' hoặc 'name')
found = []
def walk(o, path=""):
    if isinstance(o, dict):
        keys = set(o.keys())
        if "value" in keys and (keys & {"title", "name", "label"}):
            found.append((path, o))
        for k, v in o.items():
            walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]")

walk(data.get("props", {}), "props")
print(f"Tìm thấy {len(found)} series-like objects\n")
seen_titles = set()
for path, o in found:
    title = o.get("title") or o.get("name") or o.get("label")
    if title in seen_titles:
        continue
    seen_titles.add(title)
    print(f"  {title!r:55} value={o.get('value')!r:10} prev={o.get('pre_value')!r:8} "
          f"ngay={o.get('ngay')!r} unit={o.get('unit')!r}")
