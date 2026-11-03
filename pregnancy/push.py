"""推送通道适配器。

所有通道都通过标准库 urllib 发送 HTTP 请求，无需安装第三方依赖。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .content import DailyCard, markdown, plain_text
from .store import log_record, pushed_today

USER_AGENT = "PregnancyDaily/1.0 (+local)"
TIMEOUT = 12

# 企业微信 markdown 上限 4096 字节，预留余量
WECOM_LIMIT = 3800


@dataclass
class Message:
    title: str
    markdown: str
    text: str
    url: str = ""

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


def build_message(card: DailyCard, config: Dict, url: str = "") -> Message:
    return Message(
        title=card.subject,
        markdown=markdown(card, url, config),
        text=plain_text(card, url),
        url=url,
    )


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
    content = msg.clipped_markdown()
    if msg.url:
        content += "\n\n[查看完整卡片](%s)" % msg.url
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    ok, body = _post_json(url, payload)
    return _done(body)


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
