@echo off
rem Chạy crawler hàng ngày — được gọi bởi Windows Task Scheduler lúc 17:00.
set PYTHONUTF8=1
cd /d "%~dp0"
python run.py >> data\crawl.log 2>&1
python crawl_market.py >> data\crawl.log 2>&1
python scripts\build_static.py >> data\crawl.log 2>&1
echo [%date% %time%] exit=%errorlevel% >> data\crawl.log
