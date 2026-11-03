FROM python:3.11-slim

WORKDIR /app
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

COPY . /app

RUN chmod +x /app/deploy/start-all.sh

EXPOSE 8787
VOLUME ["/app/data"]

# 同时提供手机网页（8787）与每天定时推送
CMD ["/app/deploy/start-all.sh"]
