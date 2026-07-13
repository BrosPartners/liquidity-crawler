# Tích hợp Google Sheet (nguồn dữ liệu dashboard)

Sheet gốc: **Banking AI** — `1Y58PsyulZ3c60F0yKf-xDrrjuZe2UDnVvXZAILUrq_U`

Luồng: `crawl (weekly) → push_to_sheet.py → Google Sheet → build_static (đọc sheet) → dashboard`

Crawler ghi vào 3 tab:
| Tab | Nội dung | Ghi chú |
|-----|----------|---------|
| `Auto - Deposit` | Lãi suất huy động dạng long: date, bank_code, bank_name, term, rate, product | Tự tạo. 8 bank crawl được (VCB, CTG, BID, VPB, TCB, ACB, STB, HDB) |
| `Auto - Market` | Liên NH đủ kỳ hạn, OMO/tín phiếu/chiết khấu/tái cấp vốn, tỷ giá, vĩ mô | Tự tạo |
| `ON rate` | Append 1 điểm ON rate/tuần vào tab lịch sử daily sẵn có (2014→nay) | Không đụng chart/định dạng cũ |

Tab `Dep rates - Group` (bảng phân tích tay) **được giữ nguyên**, không ghi tự động.

---

## Cần bạn làm 2 việc (1 lần) để kích hoạt ghi + đọc

### 1. Deploy Apps Script Web App (đường GHI vào sheet)
1. Mở sheet → **Extensions → Apps Script**.
2. Xoá code mẫu, dán toàn bộ [`apps_script.gs`](apps_script.gs).
3. Sửa dòng `var TOKEN = 'DOI_TOKEN_NAY';` thành 1 chuỗi bí mật của bạn.
4. **Deploy → New deployment → Web app**:
   - *Execute as*: **Me**
   - *Who has access*: **Anyone**
   - → **Deploy** → Authorize → copy **Web app URL** (dạng `.../exec`).
5. Điền vào `config.json` (copy từ `config.example.json`):
   ```json
   {
     "sheet_id": "1Y58PsyulZ3c60F0yKf-xDrrjuZe2UDnVvXZAILUrq_U",
     "web_app_url": "<URL .../exec vừa copy>",
     "token": "<TOKEN vừa đặt>",
     "deposit_product": "online"
   }
   ```

### 2. Publish sheet để dashboard đọc công khai (đường ĐỌC)
- **File → Share → Publish to web** → Publish.
- (Việc đọc qua gviz CSV đã hoạt động sẵn vì sheet chia sẻ link; publish để chắc chắn ổn định.)

---

## Chạy thử
```bash
python push_to_sheet.py        # đẩy data mới nhất lên sheet (nếu chưa cấu hình -> [SKIP])
python scripts/build_static.py # build dashboard, tự đọc nguồn từ sheet
```

## Lịch tự động
- **Windows**: task `LiquidityCrawler-Weekly` chạy `run_weekly.bat` (Thứ Sáu 17:00): crawl + push + build.
  Task `LiquidityCrawler-Daily` vẫn refresh dashboard hàng ngày.
- **GitHub Actions** (`.github/workflows/cron.yml`): bước push chỉ chạy Thứ Sáu. Cần đặt secrets:
  `SHEET_ID`, `SHEET_WEB_APP_URL`, `SHEET_TOKEN` (không commit token — `config.json` đã nằm trong `.gitignore`).

## Bảo mật
- `config.json` chứa token → đã ignore khỏi git. Trên CI dùng biến môi trường
  `SHEET_WEB_APP_URL` / `SHEET_TOKEN` / `SHEET_ID` (override `config.json`).
