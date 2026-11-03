@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 正在启动孕期日历服务...
echo 手机请访问终端里显示的局域网地址（同一 Wi-Fi）
python app.py serve
pause
