@echo off
rem Chạy hàng TUẦN — crawl + đẩy lên Google Sheet + build dashboard.
rem Được gọi bởi Windows Task Scheduler (mặc định: Thứ Sáu 17:00).
set PYTHONUTF8=1
cd /d "%~dp0"
echo ===== [%date% %time%] WEEKLY start ===== >> data\crawl.log
python run.py >> data\crawl.log 2>&1
python crawl_market.py >> data\crawl.log 2>&1
python push_to_sheet.py >> data\crawl.log 2>&1
python scripts\build_static.py >> data\crawl.log 2>&1
echo [%date% %time%] WEEKLY exit=%errorlevel% >> data\crawl.log
