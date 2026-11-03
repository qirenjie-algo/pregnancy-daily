"""配置与推送日志（本地 JSON，默认不落任何云端）。"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
LOG_PATH = ROOT / "data" / "push_log.jsonl"

DEFAULT_CONFIG: Dict = {
    "lmp": "2026-09-02",
    "wife_name": "老婆",
    "baby_nickname": "宝宝",
    "push_time": "07:30",
    "timezone": "Asia/Shanghai",
    "port": 8787,
    "base_url": "",
    "height_cm": None,
    "pre_weight_kg": None,
    "channels": [],
}

CHANNEL_LABELS = {
    "serverchan": "微信（Server酱）",
    "pushplus": "微信（PushPlus）",
    "bark": "iPhone（Bark）",
    "telegram": "Telegram",
    "wecom": "企业微信",
    "dingtalk": "钉钉",
    "feishu": "飞书",
    "webhook": "自定义 Webhook",
}


def load_config(path: Optional[Path] = None) -> Dict:
    path = Path(path) if path else CONFIG_PATH
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        if not isinstance(user, dict):
            raise ValueError("config.json 必须是一个 JSON 对象")
        config.update(user)
    # 环境变量覆盖（方便 GitHub Actions / Docker）
    for key, env in (("lmp", "PREGNANCY_LMP"), ("push_time", "PREGNANCY_PUSH_TIME"), ("port", "PREGNANCY_PORT")):
        if os.environ.get(env):
            config[key] = os.environ[env]
    if os.environ.get("PREGNANCY_BASE_URL"):
        config["base_url"] = os.environ["PREGNANCY_BASE_URL"]
    return config


def save_config(config: Dict, path: Optional[Path] = None) -> Path:
    path = Path(path) if path else CONFIG_PATH
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    return path


def channel_label(config: Dict) -> str:
    names = [CHANNEL_LABELS.get(c.get("type", ""), c.get("type", "")) for c in config.get("channels", [])]
    names = [n for n in names if n]
    return "、".join(names) if names else "未配置（可先用网页查看）"


def log_record(record: Dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log(limit: int = 100) -> List[Dict]:
    if not LOG_PATH.exists():
        return []
    rows = []
    with open(LOG_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def pushed_today(date: dt.date, channel: str) -> bool:
    iso = date.isoformat()
    for row in read_log():
        if row.get("date") == iso and row.get("channel") == channel and row.get("ok"):
            return True
    return False
