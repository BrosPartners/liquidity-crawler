"""Probe Vietstock vnibor-66: tìm AJAX endpoint + token cho lãi suất liên NH."""
import re, sys
import httpx

PAGE = "https://finance.vietstock.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang-vnibor-66"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Accept-Language": "vi-VN,vi;q=0.9"}

with httpx.Client(headers=HDR, follow_redirects=True, timeout=30, http2=False) as c:
    r = c.get(PAGE)
    print("PAGE", r.status_code, "len", len(r.text), file=sys.stderr)
    html = r.text

    # 1. Tìm request verification token
    tok = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
    print("TOKEN:", (tok.group(1)[:40] + "...") if tok else "NONE")

    # 2. Tìm mọi URL api.vietstock / /data/ trong HTML + inline JS
    urls = set(re.findall(r'["\']((?:https?://[^"\']*vietstock[^"\']*|/data/[^"\']*|/vi-mo/[^"\']*))["\']', html))
    print("\n-- Candidate endpoints --")
    for u in sorted(urls):
        if any(k in u.lower() for k in ["data", "chart", "list", "api", "vimo", "getdata"]):
            print(" ", u)

    # 3. Tìm ID chỉ tiêu (thường dạng normCode / id trong JS)
    print("\n-- id / normCode patterns --")
    for m in re.findall(r'(normCode|NormId|normId|IndicatorId|indicatorId|catId|CatID)["\']?\s*[:=]\s*["\']?(\w+)', html)[:20]:
        print(" ", m)

    # 4. Cookies sau khi GET
    print("\nCookies:", list(c.cookies.keys()))
