# Liquidity Crawler — Thanh khoản hệ thống ngân hàng VN

Tool crawl & visualize tình hình thanh khoản hệ thống ngân hàng Việt Nam.

## Module
- **Lãi suất huy động** (MVP — đang làm): crawl trực tiếp từng bank.
- _Liên ngân hàng (qua đêm…)_ — sẽ thêm: nguồn SBV.
- _Bơm/rút OMO của SBV_ — sẽ thêm: SBV + LLM trích số.

## Kiến trúc
```
config/banks.yaml      # registry: bank nào, URL, kiểu crawl
core/                  # schema, chuẩn hoá, trích bảng, sink (ghi dữ liệu)
adapters/              # mỗi bank 1 file, cùng interface fetch() -> List[RateRow]
run.py                 # chạy tất cả adapter -> gom -> ghi sink
data/                  # latest.json + history.csv (nguồn cho website visualize)
web/                   # dashboard tĩnh, fetch data/latest.json
.github/workflows/     # cron chạy mỗi sáng
```

## Cài đặt
```bash
pip install -r requirements.txt
playwright install chromium          # cho các bank render bằng JS
```

## Chạy
```bash
python run.py                        # crawl tất cả bank trong config, ghi data/
python run.py --banks VCB,TCB        # chỉ vài bank
python run.py --headful              # mở trình duyệt thật để debug selector
```

## Quy trình thêm 1 bank mới
1. Mở trang lãi suất của bank → F12 → tab **Network/XHR**.
2. Nếu thấy request trả **JSON** bảng lãi suất → dùng `mode: json` trong `banks.yaml`, điền endpoint.
3. Nếu không → để `mode: render` (Playwright). Bộ trích bảng tổng quát sẽ tự dò.
4. Kiểm tra: `python run.py --banks <CODE> --headful` rồi soi `data/latest.json`.

## Visualize
`data/latest.json` là nguồn cho `web/`. Deploy `web/` lên GitHub Pages/Vercel,
hoặc commit `data/` để website fetch trực tiếp từ raw GitHub.
