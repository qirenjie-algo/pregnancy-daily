#!/usr/bin/env python3
"""孕期每日推送 —— 服务入口。

用法：
    python app.py init                 生成 config.json
    python app.py today                在终端打印今天的推送内容
    python app.py serve                启动手机端网页（默认 8787 端口）
    python app.py push --dry-run       模拟推送，不真正发送
    python app.py push                 向已配置的通道推送今天的内容
    python app.py daemon               每天到点自动推送
    python app.py preview              导出静态 HTML / Markdown 预览
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import sys
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pregnancy.content import (
    build_card,
    history_days,
    is_public_url,
    load_checkups,
    load_meals,
    load_weeks,
    markdown,
    plain_text,
    timeline,
    week_entry,
)
from pregnancy.gestation import Gestation, parse_date
from pregnancy.push import build_message, dispatch, preview_payload
from pregnancy.render import (
    APP_NAME,
    render_about,
    render_day,
    render_error,
    render_history,
    render_pager,
    render_timeline,
    render_week,
)
from pregnancy.store import (
    CHANNEL_LABELS,
    DEFAULT_CONFIG,
    channel_label,
    load_config,
    save_config,
)

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
ASSET_DIR = WEB_DIR / "assets"
OUT_DIR = ROOT / "out"
ASSET_RE = re.compile(r"^week-\d{2}\.(webp|png)$")

STATIC_TYPES = {
    ".json": "application/json; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".css": "text/css; charset=utf-8",
}


def make_gestation(config: dict, date: dt.date = None) -> Gestation:
    lmp = parse_date(config["lmp"])
    today = date or dt.date.today()
    return Gestation(lmp, today)


def today_url(config: dict) -> str:
    base = (config.get("base_url") or "").strip()
    if not base:
        base = "http://127.0.0.1:%s" % config.get("port", 8787)
    return base.rstrip("/") + "/"


# --------------------------------------------------------------------------
# HTTP 服务
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "PregnancyDaily/1.0"
    config = None  # 由 serve() 注入

    def log_message(self, fmt, *args):  # 安静一点
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------- 工具 ----------
    def _send(self, body: bytes, status: HTTPStatus = HTTPStatus.OK, content_type="text/html; charset=utf-8", cache="no-cache"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _html(self, text: str, status: HTTPStatus = HTTPStatus.OK):
        self._send(text.encode("utf-8"), status)

    def _json(self, data, status: HTTPStatus = HTTPStatus.OK):
        self._send(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), status, "application/json; charset=utf-8")

    # ---------- 路由 ----------
    def do_GET(self):
        try:
            self._route()
        except Exception:
            traceback.print_exc()
            self._html(render_error("服务器开了个小差，请刷新重试", 500), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_HEAD(self):
        self.do_GET()

    def _route(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        config = self.config
        g = make_gestation(config)

        if path == "/health":
            self._json({"ok": True, "app": APP_NAME, "version": "1.0.0", "today": g.today.isoformat()})
            return

        if path == "/manifest.json":
            self._send((WEB_DIR / "manifest.json").read_bytes(), content_type=STATIC_TYPES[".json"])
            return
        if path == "/sw.js":
            self._send((WEB_DIR / "sw.js").read_bytes(), content_type=STATIC_TYPES[".js"])
            return
        if path == "/icon.svg":
            self._send((WEB_DIR / "icon.svg").read_bytes(), content_type=STATIC_TYPES[".svg"])
            return

        if path.startswith("/assets/"):
            name = path.rsplit("/", 1)[-1]
            if not ASSET_RE.match(name):
                self._html(render_error("素材不存在", 404), HTTPStatus.NOT_FOUND)
                return
            file_path = ASSET_DIR / name
            if not file_path.exists():
                self._html(render_error("素材不存在", 404), HTTPStatus.NOT_FOUND)
                return
            ctype = "image/webp" if name.endswith(".webp") else "image/png"
            self._send(file_path.read_bytes(), content_type=ctype, cache="public, max-age=86400")
            return

        if path == "/api/today":
            card = build_card(g, config)
            self._json(card.to_dict())
            return
        if path == "/api/timeline":
            self._json(timeline(g, load_weeks()))
            return
        if path == "/api/history":
            self._json(history_days(g, load_weeks()))
            return

        if path.startswith("/week/"):
            try:
                week = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._html(render_error("周数不对哦", 404), HTTPStatus.NOT_FOUND)
                return
            if not 1 <= week <= 42:
                self._html(render_error("只能查看第 1~42 周", 404), HTTPStatus.NOT_FOUND)
                return
            entry = week_entry(load_weeks(), week)
            self._html(render_week(g, week, entry))
            return

        if path == "/timeline":
            self._html(render_timeline(g, timeline(g, load_weeks())))
            return
        if path == "/history":
            self._html(render_history(g, history_days(g, load_weeks())))
            return
        if path.startswith("/day/"):
            raw = path.rsplit("/", 1)[-1]
            try:
                day = dt.date.fromisoformat(raw)
            except ValueError:
                self._html(render_error("日期格式不对，应形如 2026-11-03", 404), HTTPStatus.NOT_FOUND)
                return
            if day < g.lmp or day > g.today:
                self._html(render_error("这一期还不存在哦", 404), HTTPStatus.NOT_FOUND)
                return
            card = build_card(Gestation(g.lmp, day), config)
            self._html(render_day(card, config, pager=render_pager(g, day)))
            return
        if path == "/about":
            self._html(render_about(g, dict(config, channel_label=channel_label(config))))
            return

        card = build_card(g, config)
        self._html(render_day(card, config, share_url="", pager=render_pager(g, g.today)))

    # 简单兼容 POST（表单触发推送可在后续扩展）
    def do_POST(self):
        self._json({"ok": False, "error": "暂不支持 POST"}, HTTPStatus.METHOD_NOT_ALLOWED)


def lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def serve(config: dict, port: int = None):
    port = int(port or config.get("port", 8787))
    Handler.config = config
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("=" * 56)
    print("  孕期日历已启动 · %s" % APP_NAME)
    print("  电脑访问：http://127.0.0.1:%d" % port)
    print("  手机访问：http://%s:%d  （需同一 Wi-Fi）" % (lan_ip(), port))
    print("  正在推送：%s" % channel_label(config))
    print("  预产期：%s" % make_gestation(config).due.strftime("%Y-%m-%d"))
    if not any(ASSET_DIR.glob("*.webp")):
        print("  提示：还没有动态配图，运行 `python app.py assets` 生成（需 Pillow）")
    print("  Ctrl+C 停止")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


# --------------------------------------------------------------------------
# 命令行动作
# --------------------------------------------------------------------------
def cmd_init(config: dict) -> int:
    from pregnancy.store import CONFIG_PATH, save_config

    if CONFIG_PATH.exists():
        print("config.json 已存在，未覆盖：%s" % CONFIG_PATH)
        return 0
    save_config(dict(DEFAULT_CONFIG, channels=[]))
    print("已生成 %s" % CONFIG_PATH)
    print("下一步：编辑它填写推送通道，然后运行 `python app.py push --dry-run` 预览。")
    return 0


def cmd_today(config: dict, date: dt.date = None) -> int:
    g = make_gestation(config, date)
    card = build_card(g, config)
    print(markdown(card, today_url(config), config))
    return 0


def cmd_push(config: dict, dry_run: bool = False, force: bool = False, date: dt.date = None) -> int:
    g = make_gestation(config, date)
    card = build_card(g, config)
    url = today_url(config)
    # 本地地址手机打不开，推送里就不放死链和图片
    if not is_public_url(url):
        url = ""
    msg = build_message(card, config, url)
    if not config.get("channels"):
        print("还没有配置推送通道。先看效果：python app.py today")
        print("配置方法见 README 的「推送通道」一节。")
        if dry_run:
            print(json.dumps(preview_payload(config, msg), ensure_ascii=False, indent=2)[:4000])
        return 1 if not dry_run else 0
    if dry_run:
        print(json.dumps(preview_payload(config, msg), ensure_ascii=False, indent=2))
        print("\n（dry-run：以上内容未真正发送）")
        return 0
    results = dispatch(config, msg, dry_run=False, force=force, date=g.today)
    failed = [r for r in results if not r["ok"]]
    for r in results:
        print("%s  %-18s %s" % ("✅" if r["ok"] else "❌", r["channel"], r["detail"]))
    return 0 if not failed else 2


def cmd_preview(config: dict, date: dt.date = None, out_dir: Path = OUT_DIR) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    g = make_gestation(config, date)
    card = build_card(g, config)
    day_html = render_day(card, config, pager=render_pager(g, g.today))
    (out_dir / "today.html").write_text(day_html, encoding="utf-8")
    (out_dir / "timeline.html").write_text(render_timeline(g, timeline(g, load_weeks())), encoding="utf-8")
    (out_dir / "history.html").write_text(render_history(g, history_days(g, load_weeks())), encoding="utf-8")
    (out_dir / "push.md").write_text(markdown(card, "", config), encoding="utf-8")
    (out_dir / "push.txt").write_text(plain_text(card, ""), encoding="utf-8")
    print("已导出：%s" % out_dir)
    for name in ("today.html", "timeline.html", "history.html", "push.md"):
        print("  - %s" % (out_dir / name))
    return 0


def cmd_assets(force: bool = False, style: str = None) -> int:
    from pregnancy.assets import generate_all

    style = style or "city"
    stats = generate_all(ASSET_DIR, force=force, style=style)
    print("素材完成（%s）：新增 %d 周，跳过 %d 周 -> %s" % (style, stats["made"], stats["skipped"], ASSET_DIR))
    return 0


def cmd_export(config: dict, out: str = "site", date: dt.date = None) -> int:
    from pregnancy.site import export_site

    target = Path(out)
    if not target.is_absolute():
        target = ROOT / target
    stats = export_site(config, target, today=date)
    size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1024 / 1024
    print("静态站点已导出：%s" % target)
    print("  页面 %d 个，素材 %d 个，共 %.1f MB" % (stats["pages"], stats.get("assets", 0), size_mb))
    print("  本地预览：python -m http.server 8080 -d %s" % target)
    return 0


def cmd_daemon(config: dict, force: bool = False) -> int:
    hh, mm = (config.get("push_time") or "07:30").split(":")
    push_at = dt.time(int(hh), int(mm))
    print("定时推送已启动，每天 %s 推送。Ctrl+C 停止。" % push_at.strftime("%H:%M"))
    while True:
        now = dt.datetime.now()
        target = now.replace(hour=push_at.hour, minute=push_at.minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        wait = (target - now).total_seconds()
        print("下次推送：%s（%.1f 小时后）" % (target.strftime("%Y-%m-%d %H:%M"), wait / 3600))
        try:
            time.sleep(max(1, min(wait, 3600)))
        except KeyboardInterrupt:
            print("\n已停止。")
            return 0
        # 到点后重新计算，避免长时间 sleep 漂移
        if dt.datetime.now() >= target:
            print("开始推送：%s" % target.strftime("%Y-%m-%d %H:%M"))
            try:
                cmd_push(config, force=force, date=target.date())
            except Exception:
                traceback.print_exc()
            time.sleep(90)  # 避免同一分钟内重复触发


def cmd_check(config: dict, date: dt.date = None) -> int:
    g = make_gestation(config, date)
    card = build_card(g, config)
    print("末次月经：%s" % g.lmp)
    print("今天：%s（%s）" % (g.today, g.label))
    print("预产期：%s（剩余 %d 天）" % (g.due, g.remaining_days))
    print("阶段：%s｜进度 %.1f%%" % (g.trimester_name, g.progress * 100))
    print("本周主题：%s" % card.title)
    print("今日饮食：%s" % card.diet.meals[0][1])
    print("推送通道：%s" % channel_label(config))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.py", description="孕期每日推送")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 ./config.json")
    parser.add_argument("--lmp", default=None, help="临时覆盖末次月经日期 YYYY-MM-DD")
    parser.add_argument("--date", default=None, help="模拟某一天 YYYY-MM-DD（预览用）")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="启动手机端网页")
    p_serve.add_argument("--port", type=int, default=None)

    sub.add_parser("init", help="生成 config.json")
    sub.add_parser("today", help="在终端打印今日推送内容")
    sub.add_parser("check", help="自检：打印孕周与配置")
    sub.add_parser("daemon", help="每天定时推送")
    sub.add_parser("preview", help="导出静态预览 HTML")

    p_push = sub.add_parser("push", help="立即推送")
    p_push.add_argument("--dry-run", action="store_true", help="只打印将要发送的内容")
    p_push.add_argument("--force", action="store_true", help="忽略当日去重，强制推送")

    p_assets = sub.add_parser("assets", help="生成/补齐 40 周动态图")
    p_assets.add_argument("--force", action="store_true", help="全部重新生成")
    p_assets.add_argument("--style", choices=("city", "fruit"), default="city", help="city=动物城风格（默认），fruit=水果隐喻")

    p_export = sub.add_parser("export", help="导出静态站点（可部署 GitHub Pages）")
    p_export.add_argument("--out", default="site", help="输出目录，默认 site/")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(Path(args.config) if args.config else None)
    if args.lmp:
        config["lmp"] = args.lmp
    date = parse_date(args.date) if args.date else None

    command = args.command or "today"
    if command == "init":
        return cmd_init(config)
    if command == "serve":
        port = args.port or getattr(args, "port", None)
        serve(config, port)
        return 0
    if command == "today":
        return cmd_today(config, date)
    if command == "check":
        return cmd_check(config, date)
    if command == "push":
        return cmd_push(config, dry_run=args.dry_run, force=args.force, date=date)
    if command == "preview":
        return cmd_preview(config, date)
    if command == "assets":
        return cmd_assets(force=args.force, style=getattr(args, "style", "city"))
    if command == "export":
        return cmd_export(config, args.out, date)
    if command == "daemon":
        return cmd_daemon(config)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
