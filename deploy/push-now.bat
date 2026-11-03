@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 正在推送今日孕期卡片...
python app.py push
echo.
pause
