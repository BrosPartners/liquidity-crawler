# Thiết kế: Tích hợp giá vàng vào dashboard liquidity-crawler + đưa lên Vercel

**Ngày:** 2026-07-13
**Project:** `liquidity-crawler` (`D:\BP\Bros Partners\AI Task\liquidity-crawler`)
**Trạng thái:** Đã chốt thiết kế, chờ user review trước khi viết plan.

## 1. Mục tiêu

Đưa dữ liệu giá vàng (do một bot có sẵn thu thập, gửi file Excel hàng ngày qua Telegram)
lên website để cập nhật liên tục, hiển thị dưới dạng một **section/tab "Giá vàng"** trong
dashboard của project `liquidity-crawler` (bot cào tin banking).

Không xây bot scrape mới — tận dụng bot giá vàng đang chạy. Không dùng Google Sheet cho
luồng giá vàng. Chỉ dùng dữ liệu bot cung cấp.

## 2. Bối cảnh & các quyết định đã chốt

- **Nguồn dữ liệu:** file `gold_prices_all.xlsx` do bot "Giá vàng PNJ" đăng vào một Telegram
  group lúc ~9:00 sáng mỗi ngày. File chứa lịch sử từ 2020, đã cập nhật đến hôm nay.
- **Chỉ dùng data của bot** — bỏ 3 tỷ giá riêng (VCB/chợ tự do/SBV) mà sheet gốc từng track;
  file bot chỉ có 1 tỷ giá USD/VND (Yahoo). (Lưu ý: dashboard banking đã có sẵn tab "Tỷ giá
  & vĩ mô" với tỷ giá trung tâm/NHTM/tự do từ VietnamBiz — độc lập với luồng giá vàng này.)
- **Nguồn sự thật cho web = file bot** (không đổ vào Google Sheet).
- **Ingestion:** Telegram bot KHÔNG đọc được tin do bot khác gửi (giới hạn cứng của Telegram).
  → phải đọc bằng **phiên tài khoản người dùng (MTProto/Telethon)**, không phải bot.
- **Nơi chạy:** GitHub Actions (cron cloud). Repo **private**. Session Telegram lưu ở
  **GitHub Secrets**.
- **Deploy:** Vercel (link cố định, ai có link cũng xem), auto-deploy mỗi commit.
- **Phasing:** làm **Phase 1 + Phase 2** trước; Phase 3 (migrate crawler bank/market lên
  Actions) tách riêng làm sau.

## 3. Cấu trúc file `gold_prices_all.xlsx` (đã verify 2026-07-13)

10 sheet. Các sheet dùng cho web (header ở **hàng 2**, hàng 1 là dòng ghi nguồn):

| Sheet | Cột dùng | Ý nghĩa |
|-------|----------|---------|
| `Gia TG (USD_oz)` | `date`, `close_usd` | Giá vàng thế giới USD/oz (Yahoo GC=F) |
| `Gia TG (VND-luong)` | `date`, `close_vnd`, `Gia SJC`, `Gap giá vàng`, `% gap giá vàng` | Vàng TG quy đổi VND/lượng + gap vs SJC (đã tính sẵn) |
| `Ty gia USD-VND` | `date`, `usd_vnd` | Tỷ giá USD/VND (Yahoo USDVND=X) |
| `Gia VN (tat ca)` | `date`, `company`, `gold_type`, `buy_price`, `sell_price` | Long format 6 hãng: SJC/DOJI/BTMC/BTMH/PNJ/PHUQUY |

- Hàng đầu mỗi sheet có `#N/A` ở cột `Gia SJC`/gap cho các ngày cũ (trước khi có SJC) → parse
  thành `null`, không để lọt vào chart.
- Toàn bộ xlsx ~3MB, parse bằng `openpyxl` (đã có sẵn trong môi trường).

## 4. Kiến trúc

```
Bot giá vàng (giữ nguyên) ─ 9:00 đăng gold_prices_all.xlsx ─► Telegram group
                                                                    │
        (Telethon đọc bằng session tài khoản user — GitHub Secret)  │
                                                                    ▼
GitHub Actions (cron ~09:20 VN = 02:20 UTC, private repo)
   1. crawl_gold.py: connect Telethon → tìm document mới nhất tên
      gold_prices_all.xlsx trong group → tải về temp
   2. parse openpyxl → data/gold_latest.json + data/gold_history.csv
   3. build_static.py → dist/dashboard.html (nhúng data giá vàng)
   4. git commit data + dist  ──►  Vercel auto-deploy từ repo
                                                                    ▼
                                            Vercel (link cố định) phục vụ dist/
```

Phần crawler bank/market hiện tại **vẫn chạy local** (Windows Task Scheduler 17:00) trong
Phase 1+2 — không đụng tới. Điểm mấu chốt: `build_static.py` **đọc lãi suất/market từ Google
Sheet "Banking AI" ngay lúc build** (gviz CSV công khai, xem [[liquidity-crawler-project]]),
KHÔNG từ file commit. Nghĩa là khi Actions chạy build hàng ngày, nó tự lấy dữ liệu bank mới
nhất từ sheet (do crawler local push lên theo lịch sẵn có) → **dữ liệu bank trên web vẫn tươi**
mà không cần local push code lên GitHub. Actions chỉ thêm luồng giá vàng (từ JSON do chính
Actions tạo) rồi build + deploy.

→ Hệ quả: Actions phải có thêm secrets đọc sheet (`SHEET_ID`, và web-app URL/token nếu cần)
để `build_static.py` lấy được bank/market. Nếu không cấu hình sheet, build sẽ fallback file
cục bộ đã commit (bank data khi đó là ảnh chụp tĩnh — chấp nhận được nhưng cũ dần).

## 5. Thành phần & interface

### 5.1 `crawl_gold.py` (mới, ở gốc project)
- **Input:** env `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` (StringSession), `TG_CHAT`
  (id hoặc @username của group).
- **Xử lý:** `TelegramClient(StringSession(...))` → `iter_messages(chat, limit=~50)` → lấy
  message mới nhất có `document` với `attributes` filename == `gold_prices_all.xlsx` → download
  ra file tạm.
- **Parse:** hàm `parse_gold_xlsx(path) -> (latest: dict, history_rows: list)` dùng openpyxl,
  đọc 4 sheet ở mục 3, chuẩn hoá số (bỏ `#N/A` → null), sort theo ngày.
- **Output:** ghi đè hoàn toàn `data/gold_latest.json` + `data/gold_history.csv` mỗi lần chạy
  (idempotent — không cần dedup vì xlsx đã chứa full lịch sử).
- **Lỗi:** nếu không tìm thấy file/parse fail → exit non-zero + log rõ, KHÔNG ghi đè data cũ
  (giữ dashboard ở trạng thái ngày hôm trước).

### 5.2 Schema output

`data/gold_latest.json`:
```json
{
  "as_of": "2026-07-13",
  "world_gold_usd": 4076.4,
  "world_gold_vnd": 131288591,
  "gap": 17711409,
  "pct_gap": 0.1189,
  "usd_vnd": 26260,
  "brands": [
    {"company": "SJC", "buy": 145900000, "sell": 148900000},
    {"company": "DOJI", "buy": 145900000, "sell": 148900000},
    ...
  ]
}
```

`data/gold_history.csv` (wide, 1 dòng/ngày, cho line chart):
```
date,world_gold_usd,world_gold_vnd,sjc_sell,gap,pct_gap,usd_vnd
2020-01-02,1524.5,42588683,,,,23171
...
```
(Lịch sử per-brand: nếu cần chart lịch sử từng hãng, thêm `data/gold_brands.csv`
long format `date,company,buy,sell` — quyết định ở bước plan tùy nhu cầu chart.)

### 5.3 `scripts/build_static.py` (sửa)
Thêm nhúng song song với data hiện có:
- Đọc `data/gold_latest.json` → `__EMBED_GOLD_LATEST__`
- Đọc `data/gold_history.csv` → `__EMBED_GOLD_HISTORY__`
- Thêm 2 dòng `const __EMBED_GOLD_*__ = ...` vào block embed (giống `__EMBED_MKT_*__`).
- Thay `fetch(...gold...)` trong index.html bằng `Promise.resolve(__EMBED_GOLD_*__)` (regex,
  giống pattern latest/history/mkt hiện tại).

### 5.4 `web/index.html` (sửa)
- Thêm nút tab: `<button class="tab-btn" data-tab="vang">Giá vàng</button>` vào `#tabNav`.
- Thêm `<section class="tabpane" data-pane="vang">` chứa:
  - **KPI cards** (dùng class `.stat` sẵn có): SJC bán, vàng TG (USD/oz), vàng TG quy đổi
    (VND/lượng), Gap, %Gap, USD/VND.
  - **Canvas line chart**: SJC bán vs vàng TG quy đổi theo thời gian (+ vùng Gap).
  - **Canvas line chart**: %Gap theo thời gian.
  - **So sánh 6 hãng**: bar giá mua/bán mới nhất (+ tùy chọn chọn hãng xem lịch sử).
  - **Bảng** dữ liệu mới nhất + nút xuất CSV.
- JS: hàm load data giá vàng (dev: `fetch('../data/gold_latest.json')`; prod: token embed),
  hàm vẽ Canvas tái dùng helper chart sẵn có trong file.
- Style: dùng lại CSS token/`.mkt-*`/`.stat` hiện có — không thêm CDN (giữ nguyên tắc dự án).

### 5.5 Phase 1 — GitHub + Vercel
- `git init` project (hiện chưa phải git repo), dùng `.gitignore` sẵn có (đã loại `config.json`
  chứa token). Tạo repo **private** trên GitHub, push.
- **Secrets GitHub:** `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `TG_CHAT` (+ các secret sheet
  đã dùng nếu cần: `SHEET_ID`/`SHEET_WEB_APP_URL`/`SHEET_TOKEN`).
- **Vercel:** nối repo, framework "Other". Vì Actions commit sẵn `dist/dashboard.html` (data đã
  nhúng), Vercel chỉ cần **phục vụ tĩnh** thư mục `dist/` — không cần build step. Cấu hình
  `vercel.json` để entry = `dashboard.html` (rewrite `/` → `/dashboard.html`).
- Mỗi commit của Actions → Vercel auto-deploy → web cập nhật.

### 5.6 Việc user làm 1 lần (Claude hướng dẫn, KHÔNG tự nhập vì liên quan tài khoản)
1. Lấy `API_ID` + `API_HASH` tại my.telegram.org.
2. Chạy `login.py` (Claude cung cấp) trên máy local, nhập mã Telegram gửi cho anh → in ra
   StringSession.
3. Tạo repo GitHub private (Claude chuẩn bị sẵn toàn bộ file) + dán các Secret.
4. Nối Vercel với repo.

## 6. GitHub Actions workflow (Phase 2)
- File `.github/workflows/gold.yml` (hoặc gộp vào cron.yml sẵn có).
- Trigger: `schedule: cron '20 2 * * *'` (09:20 VN) + `workflow_dispatch` (chạy tay bù).
- Steps: checkout → setup Python → `pip install -r requirements.txt` (thêm `telethon`) →
  `python crawl_gold.py` → `python scripts/build_static.py` → commit `data/` + `dist/` nếu đổi.
- Idempotent: chạy lại cùng ngày chỉ ghi đè, không tạo trùng.
- Cuối tuần/nghỉ: nếu bot không đăng file mới, `crawl_gold.py` vẫn lấy file mới nhất (không
  đổi) → build không tạo commit mới → không tốn deploy.

## 7. Rủi ro & xử lý
- **Session Telegram = quyền truy cập tài khoản user.** Chỉ nằm trong GitHub Secrets (mã hoá,
  không lộ ra log/tree). Login do user tự làm.
- **Telethon trên Actions:** kết nối MTProto từ IP cloud hoạt động bình thường (khác với các
  adapter bank nhạy WAF ở Phase 3).
- **Đổi cấu trúc file bot:** parse theo TÊN sheet/cột, không theo index; thiếu cột → null + log.
- **Actions cron trễ vài phút:** chấp nhận được với tần suất ngày.
- **Bot đăng nhiều bản/ngày** (bản đầy đủ + bản fix): luôn lấy document mới nhất theo tên file.

## 8. Ngoài phạm vi (Phase 3 — làm sau)
- Chuyển crawler bank (`run.py` adapters) + market (`crawl_market.py`) từ Task Scheduler local
  lên GitHub Actions; test từng adapter trên IP cloud; vá WAF; bỏ lịch local. **Rủi ro cao** —
  tách riêng để không kẹt tính năng giá vàng.
- Đẩy giá vàng vào Google Sheet (nếu sau này muốn).
- Chart lịch sử chi tiết theo từng loại sản phẩm SJC (sheet `SJC` wide format).
```
