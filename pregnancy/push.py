"""推送通道适配器。

所有通道都通过标准库 urllib 发送 HTTP 请求，无需安装第三方依赖。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .content import DailyCard, markdown, plain_text
from .store import log_record, pushed_today

USER_AGENT = "PregnancyDaily/1.0 (+local)"
TIMEOUT = 12
ASSET_DIR = Path(__file__).resolve().parent.parent / "web" / "assets"

# 企业微信 markdown 上限 4096 字节，预留余量
WECOM_LIMIT = 3800
# 企业微信图片消息 base64 上限 2MB，留安全余量
WECOM_IMAGE_LIMIT = 1_400_000


@dataclass
class Message:
    title: str
    markdown: str
    text: str
    url: str = ""
    week: int = 0

    def clipped_markdown(self, limit: int = WECOM_LIMIT) -> str:
        raw = self.markdown
        suffix = "\n\n…（内容过长，点击链接查看完整版）"
        if len(raw.encode("utf-8")) + len(suffix.encode("utf-8")) <= limit:
            return raw
        budget = max(limit - len(suffix.encode("utf-8")), 0)
        out, total = [], 0
        for ch in raw:
            size = len(ch.encode("utf-8"))
            if total + size > budget:
                break
            out.append(ch)
            total += size
        return "".join(out) + suffix

    def markdown_without_images(self, limit: int = WECOM_LIMIT) -> str:
        """企业微信 markdown 不渲染图片语法，先把图片行去掉。"""
        return re.sub(r"!\[[^\]]*\]\([^)]*\)\s*", "", self.clipped_markdown(limit))

    def chunks(self, limit: int = WECOM_LIMIT) -> List[str]:
        """按行切分，保证每条 markdown 不超过企业微信字节上限。"""
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)\s*", "", self.markdown)
        if len(text.encode("utf-8")) <= limit:
            return [text]
        result: List[str] = []
        buffer: List[str] = []
        size = 0
        for line in text.split("\n"):
            line_size = len((line + "\n").encode("utf-8"))
            if buffer and size + line_size > limit:
                result.append("\n".join(buffer))
                buffer = [line]
                size = line_size
            else:
                buffer.append(line)
                size += line_size
        if buffer:
            result.append("\n".join(buffer))
        return result


def build_message(card: DailyCard, config: Dict, url: str = "") -> Message:
    return Message(
        title=card.subject,
        markdown=markdown(card, url, config),
        text=plain_text(card, url),
        url=url,
        week=card.g.week,
    )


def _week_image(week: int) -> Optional[bytes]:
    """取本周配图：优先把 WebP 首帧转成 PNG（720×405），否则退回缩略图。"""
    webp = ASSET_DIR / ("week-%02d.webp" % week)
    thumb = ASSET_DIR / ("week-%02d.png" % week)
    try:
        from PIL import Image

        if webp.exists():
            with Image.open(webp) as img:
                img.seek(0)
                buffer = io.BytesIO()
                img.convert("RGB").save(buffer, "PNG", optimize=True)
            data = buffer.getvalue()
            if len(data) <= WECOM_IMAGE_LIMIT:
                return data
    except Exception:
        pass
    if thumb.exists():
        return thumb.read_bytes()
    return None


def _post_json(url: str, payload: Dict) -> Tuple[bool, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            return True, body[:300]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return False, "HTTP %s: %s" % (exc.code, detail)
    except Exception as exc:  # 网络异常、DNS 失败等
        return False, "%s: %s" % (type(exc).__name__, exc)


def _post_form(url: str, payload: Dict) -> Tuple[bool, str]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True, resp.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as exc:
        return False, "HTTP %s: %s" % (exc.code, exc.read().decode("utf-8", "replace")[:300])
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def _done(payload: str, code_key: str = "code") -> Tuple[bool, str]:
    """解析常见返回体，判断是否成功。"""
    try:
        data = json.loads(payload)
    except Exception:
        return True, payload
    for key in (code_key, "errcode", "status", "code"):
        if key in data:
            value = data[key]
            ok = value in (0, 200, "0", "200", True, "success", "ok")
            return ok, payload
    if data.get("success") is False:
        return False, payload
    return True, payload


# ---------------- 各通道 ----------------
def send_serverchan(channel: Dict, msg: Message) -> Tuple[bool, str]:
    key = channel.get("sendkey", "")
    if not key:
        return False, "缺少 sendkey"
    endpoint = channel.get("endpoint", "https://sctapi.ftqq.com")
    url = "%s/%s.send" % (endpoint.rstrip("/"), key)
    ok, body = _post_form(url, {"title": msg.title, "desp": msg.markdown})
    return _done(body)


def send_pushplus(channel: Dict, msg: Message) -> Tuple[bool, str]:
    token = channel.get("token", "")
    if not token:
        return False, "缺少 token"
    payload = {
        "token": token,
        "title": msg.title,
        "content": msg.markdown,
        "template": "markdown",
    }
    if channel.get("topic"):
        payload["topic"] = channel["topic"]
    ok, body = _post_json("https://www.pushplus.plus/send", payload)
    return _done(body)


def send_bark(channel: Dict, msg: Message) -> Tuple[bool, str]:
    key = channel.get("key", "")
    if not key:
        return False, "缺少 key"
    server = channel.get("server", "https://api.day.app").rstrip("/")
    url = "%s/%s" % (server, key)
    payload = {
        "title": msg.title,
        "body": msg.text[:1200],
        "group": channel.get("group", "孕期"),
        "sound": channel.get("sound", "alarm"),
        "icon": channel.get("icon", ""),
        "url": msg.url,
    }
    ok, body = _post_json(url, payload)
    return _done(body)


def send_telegram(channel: Dict, msg: Message) -> Tuple[bool, str]:
    token = channel.get("token", "")
    chat_id = channel.get("chat_id", "")
    if not token or not chat_id:
        return False, "缺少 token 或 chat_id"
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = {
        "chat_id": chat_id,
        "text": msg.text,
        "disable_web_page_preview": False,
    }
    ok, body = _post_json(url, payload)
    return _done(body)


def send_wecom(channel: Dict, msg: Message) -> Tuple[bool, str]:
    url = channel.get("webhook") or ""
    if not url and channel.get("key"):
        url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=%s" % channel["key"]
    if not url:
        return False, "缺少 webhook 或 key"

    # 企业微信 markdown 不支持图片，先单独发一条图片消息
    image_note = ""
    if channel.get("image", True) and msg.week:
        data = _week_image(msg.week)
        if data:
            ok, body = _post_json(
                url,
                {
                    "msgtype": "image",
                    "image": {
                        "base64": base64.b64encode(data).decode("ascii"),
                        "md5": hashlib.md5(data).hexdigest(),
                    },
                },
            )
            if not ok or not _done(body)[0]:
                image_note = "（配图发送失败：%s）" % body[:80]

    content_parts = msg.chunks()
    if msg.url:
        content_parts[-1] += "\n\n[查看完整卡片](%s)" % msg.url
    last_body = ""
    for index, content in enumerate(content_parts):
        title = "（%d/%d）" % (index + 1, len(content_parts)) if len(content_parts) > 1 else ""
        if title:
            content = title + "\n" + content
        ok, last_body = _post_json(url, {"msgtype": "markdown", "markdown": {"content": content}})
        if not ok or not _done(last_body)[0]:
            return False, last_body + image_note
    return True, last_body + image_note


def send_dingtalk(channel: Dict, msg: Message) -> Tuple[bool, str]:
    url = channel.get("webhook") or ""
    if not url and channel.get("access_token"):
        url = "https://oapi.dingtalk.com/robot/send?access_token=%s" % channel["access_token"]
    if not url:
        return False, "缺少 webhook 或 access_token"
    secret = channel.get("secret")
    if secret:
        ts = str(int(time.time() * 1000))
        string_to_sign = "%s\n%s" % (ts, secret)
        digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        sep = "&" if "?" in url else "?"
        url = "%s%stimestamp=%s&sign=%s" % (url, sep, ts, sign)
    payload = {"msgtype": "markdown", "markdown": {"title": msg.title, "text": msg.clipped_markdown()}}
    ok, body = _post_json(url, payload)
    return _done(body)


def send_feishu(channel: Dict, msg: Message) -> Tuple[bool, str]:
    url = channel.get("webhook") or ""
    if not url and channel.get("token"):
        url = "https://open.feishu.cn/open-apis/bot/v2/hook/%s" % channel["token"]
    if not url:
        return False, "缺少 webhook 或 token"
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": msg.title}, "template": "orange"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": msg.clipped_markdown(3000)}}],
        },
    }
    ok, body = _post_json(url, payload)
    return _done(body)


def send_webhook(channel: Dict, msg: Message) -> Tuple[bool, str]:
    url = channel.get("url", "")
    if not url:
        return False, "缺少 url"
    payload = {"title": msg.title, "markdown": msg.markdown, "text": msg.text, "url": msg.url}
    ok, body = _post_json(url, payload)
    return _done(body)


SENDERS = {
    "serverchan": send_serverchan,
    "pushplus": send_pushplus,
    "bark": send_bark,
    "telegram": send_telegram,
    "wecom": send_wecom,
    "dingtalk": send_dingtalk,
    "feishu": send_feishu,
    "webhook": send_webhook,
}


def dispatch(config: Dict, msg: Message, dry_run: bool = False, force: bool = False, date=None) -> List[Dict]:
    """向所有已配置通道推送，返回每个通道的结果。"""
    results: List[Dict] = []
    channels = [c for c in config.get("channels", []) if c.get("enabled", True)]
    for channel in channels:
        kind = channel.get("type", "")
        name = channel.get("name") or kind
        if kind not in SENDERS:
            results.append({"channel": name, "type": kind, "ok": False, "detail": "未知通道类型"})
            continue
        if dry_run:
            results.append({"channel": name, "type": kind, "ok": True, "detail": "dry-run，未真正发送"})
            continue
        if date is not None and not force and pushed_today(date, name):
            results.append({"channel": name, "type": kind, "ok": True, "detail": "今天已推送，跳过"})
            continue
        ok, detail = SENDERS[kind](channel, msg)
        results.append({"channel": name, "type": kind, "ok": ok, "detail": detail[:300]})
        log_record(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "date": date.isoformat() if date else "",
                "channel": name,
                "type": kind,
                "ok": ok,
                "detail": detail[:300],
            }
        )
    return results


def preview_payload(config: Dict, msg: Message) -> Dict:
    """不发送，只展示将要发送的内容，便于自查。"""
    return {
        "title": msg.title,
        "url": msg.url,
        "markdown": msg.markdown,
        "text": msg.text,
        "channels": [
            {"name": c.get("name") or c.get("type"), "type": c.get("type")}
            for c in config.get("channels", [])
        ],
    }
