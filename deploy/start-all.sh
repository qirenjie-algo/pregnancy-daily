#!/bin/sh
# 容器内同时启动：网页服务 + 每日定时推送
set -e

python app.py serve &
SERVE_PID=$!

python app.py daemon &
DAEMON_PID=$!

# 任一进程退出则整体退出，交给容器重启策略
wait $SERVE_PID $DAEMON_PID
