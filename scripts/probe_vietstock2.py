"""Probe 2: đọc inline JS quanh vùng load data liên NH của Vietstock."""
import re, sys
import httpx

PAGE = "https://finance.vietstock.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang-vnibor-66"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Accept-Language": "vi-VN,vi;q=0.9"}

with httpx.Client(headers=HDR, follow_redirects=True, timeout=30, http2=False) as c:
    html = c.get(PAGE).text

# In các đoạn chứa từ khoá quan trọng
for kw in ["GetData", "vimo", "ViMo", "ajax", "ContentId", "contentId", "url:", ".ashx", "GetTemplateByName", "st-api"]:
    print(f"\n===== '{kw}' =====")
    for m in re.finditer(re.escape(kw), html):
        s = max(0, m.start()-120); e = min(len(html), m.end()+160)
        snippet = html[s:e].replace("\n", " ").replace("\t", " ")
        snippet = re.sub(r"\s+", " ", snippet)
        print("  …" + snippet + "…")
        break  # 1 ví dụ mỗi kw
