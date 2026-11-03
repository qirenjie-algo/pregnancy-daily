"""把「孕周 + 日期」合成为一张每日推送卡片。"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .gestation import Gestation, cn_weekday, friendly_date

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

WEEK_LABELS = {
    "title": "本周主题",
    "baby": "宝宝的变化",
    "mom": "妈妈的变化",
    "focus": "本周重点",
    "nutrition": "营养重点",
    "precautions": "注意事项",
    "tip": "小贴士",
    "checkup": "产检提醒",
}

MEAL_ORDER = [
    ("breakfast", "早餐"),
    ("morning_snack", "上午加餐"),
    ("lunch", "午餐"),
    ("afternoon_snack", "下午加餐"),
    ("dinner", "晚餐"),
    ("evening_snack", "睡前加餐"),
]

DAD_TASKS = [
    "今天主动承担一次晚餐或洗碗，让她少站 10 分钟。",
    "睡前帮她按揉小腿 5 分钟，预防夜间抽筋。",
    "陪她散步 20 分钟，路上不聊工作，只聊开心的事。",
    "把产检日期写进两个人的日历，并设好提醒。",
    "今晚由你负责倒水和递零食，让她安心躺着。",
    "学会一句夸奖：今天的你很好看，真的。",
    "检查一下家里的防滑垫、夜灯和门槛，减少绊倒风险。",
    "帮她剪一次脚趾甲——她已经弯不下腰了。",
    "把手机调成静音，陪她看一集喜欢的剧。",
    "主动问一句：今天身体哪里不舒服吗？然后认真听完。",
    "提前查好去医院的路线和急诊入口，存在手机里。",
    "给她拍一张孕肚照，记录今天的样子。",
    "周末做一顿她爱吃的菜，少油少盐版本。",
    "把待产包清单打印出来，两个人一起打勾。",
]

QUOTES = [
    "你已经做得很好了，不必每天都完美。",
    "身体在悄悄努力，你只需要好好吃饭、好好睡觉。",
    "孕育是一场长跑，慢一点没关系，方向对就好。",
    "每一次胎动，都是宝宝在说「我在这里」。",
    "允许自己情绪化，激素在替你加班。",
    "今天的任务只有一件：照顾好自己。",
    "不必和别人比肚子大小，每个人的节奏都不同。",
    "你正在完成一件非常了不起的事。",
]


def _load_json(name: str):
    with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_weeks() -> Dict[int, dict]:
    """合并 data/weeks-*.json，key 为孕周。"""
    weeks: Dict[int, dict] = {}
    for path in sorted(DATA_DIR.glob("weeks-*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        for key, value in raw.items():
            try:
                weeks[int(key)] = value
            except ValueError:
                continue
    return weeks


def load_checkups() -> List[dict]:
    return _load_json("checkups.json")["schedule"]


def load_meals() -> dict:
    return _load_json("meals.json")


def week_entry(weeks: Dict[int, dict], week: int) -> dict:
    """取某一周的内容；41/42 周或缺失时回退到最近的一周。"""
    if week in weeks:
        return weeks[week]
    keys = sorted(weeks)
    if not keys:
        return {}
    nearest = min(keys, key=lambda k: abs(k - week))
    return weeks[nearest]


@dataclass
class DietPlan:
    trimester: int
    tag: str
    focus: str
    meals: List[tuple]  # [(label, text)]
    highlights: List[str]
    note: str
    water_ml: int
    salt_g: float
    avoid: List[str]
    supplements: List[str]
    tips: List[str]


@dataclass
class CheckupInfo:
    name: str
    tag: str
    detail: str
    start_week: int
    end_week: int
    status: str  # done / now / upcoming
    date: Optional[dt.date] = None
    days_left: Optional[int] = None


@dataclass
class DailyCard:
    g: Gestation
    week: dict
    diet: DietPlan
    checkup_now: List[CheckupInfo] = field(default_factory=list)
    checkup_next: Optional[CheckupInfo] = None
    dad_task: str = ""
    quote: str = ""
    weight_text: str = ""
    kick_text: str = ""
    week_note: str = ""
    tips_extra: List[str] = field(default_factory=list)

    # ---------- 派生 ----------
    @property
    def size(self) -> dict:
        return self.week.get("size") or {"len": 0, "weight": 0, "like": "小宝宝"}

    @property
    def title(self) -> str:
        return self.week.get("title") or "孕期日常"

    @property
    def subject(self) -> str:
        return "%s｜%s" % (self.g.label, self.title)

    def to_dict(self) -> dict:
        return {
            "gestation": self.g.as_dict(),
            "week": self.week,
            "diet": {
                "trimester": self.diet.trimester,
                "tag": self.diet.tag,
                "focus": self.diet.focus,
                "meals": [{"label": l, "text": t} for l, t in self.diet.meals],
                "highlights": self.diet.highlights,
                "note": self.diet.note,
                "water_ml": self.diet.water_ml,
                "salt_g": self.diet.salt_g,
                "avoid": self.diet.avoid,
                "supplements": self.diet.supplements,
                "tips": self.diet.tips,
            },
            "checkup_now": [_checkup_dict(c) for c in self.checkup_now],
            "checkup_next": _checkup_dict(self.checkup_next) if self.checkup_next else None,
            "dad_task": self.dad_task,
            "quote": self.quote,
            "weight_text": self.weight_text,
            "kick_text": self.kick_text,
            "week_note": self.week_note,
            "tips_extra": self.tips_extra,
            "subject": self.subject,
        }


def _checkup_dict(info: Optional[CheckupInfo]) -> dict:
    if info is None:
        return {}
    data = dict(info.__dict__)
    if isinstance(data.get("date"), dt.date):
        data["date"] = data["date"].isoformat()
    return data


def _bmi(height_cm: Optional[float], weight_kg: Optional[float]) -> Optional[float]:
    if not height_cm or not weight_kg:
        return None
    return weight_kg / ((height_cm / 100.0) ** 2)


def weight_advice(height_cm: Optional[float], weight_kg: Optional[float], g: Gestation) -> str:
    bmi = _bmi(height_cm, weight_kg)
    if bmi is None:
        if g.trimester == 1:
            return "孕早期增重 0.5~2kg 即可，重点是叶酸和优质蛋白，不必刻意多吃；中晚期每周 0.3~0.5kg。在配置里填身高体重可得到个体化建议。"
        return "孕中晚期每周增重 0.3~0.5kg 比较理想；在配置里填身高体重可得到个体化建议。"
    if bmi < 18.5:
        total, rate = "12.5~18kg", "0.4~0.6kg"
        band = "偏瘦"
    elif bmi < 24:
        total, rate = "11.5~16kg", "0.3~0.5kg"
        band = "正常"
    elif bmi < 28:
        total, rate = "7~11.5kg", "0.2~0.3kg"
        band = "偏胖"
    else:
        total, rate = "5~9kg", "0.2~0.3kg"
        band = "肥胖"
    if g.trimester == 1:
        return "孕前 BMI %.1f（%s），整个孕期建议增重 %s；孕早期增重 0.5~2kg 即可，不用刻意多吃。" % (bmi, band, total)
    return "孕前 BMI %.1f（%s），整个孕期建议增重 %s，目前每周增重 %s 为宜。" % (bmi, band, total, rate)


def _pick(pool: List[str], seed: int) -> str:
    if not pool:
        return ""
    rng = random.Random(seed)
    return pool[rng.randrange(len(pool))]


def build_diet(g: Gestation, meals: dict, weeks: Dict[int, dict]) -> DietPlan:
    t = g.trimester
    notes = meals["trimester_notes"][str(t)]
    pool = meals["menus"][str(t)]
    chosen = pool[g.today.toordinal() % len(pool)]
    entry = week_entry(weeks, g.week)
    meal_items = [(label, chosen.get(key, "")) for key, label in MEAL_ORDER if chosen.get(key)]
    week_note = meals.get("week_notes", {}).get(str(g.week), "")
    note = chosen.get("note", "")
    if week_note:
        note = (note + " " + week_note).strip() if note else week_note
    return DietPlan(
        trimester=t,
        tag=notes["tag"],
        focus=notes["focus"],
        meals=meal_items,
        highlights=list(dict.fromkeys(chosen.get("highlights", []) + _nutrition_keywords(entry))),
        note=note,
        water_ml=meals["meta"]["water_ml"][str(t)],
        salt_g=meals["meta"]["salt_g"],
        avoid=list(notes["avoid"]),
        supplements=list(notes["supplement"]),
        tips=list(notes["tips"]),
    )


def _nutrition_keywords(entry: dict) -> List[str]:
    """从本周营养重点里抽出 1~2 个关键词，方便饮食卡片展示。"""
    text = entry.get("nutrition", "")
    keys = ["叶酸", "铁", "钙", "DHA", "蛋白质", "碘", "膳食纤维", "维生素 C"]
    return [k for k in keys if k in text][:2]


def checkup_status(g: Gestation, schedule: List[dict], week: int) -> List[CheckupInfo]:
    result: List[CheckupInfo] = []
    for item in schedule:
        if week > item["end_week"]:
            status = "done"
        elif item["start_week"] <= week <= item["end_week"]:
            status = "now"
        else:
            status = "upcoming"
        date = g.lmp + dt.timedelta(days=(item["start_week"] - 1) * 7)
        result.append(
            CheckupInfo(
                name=item["name"],
                tag=item["tag"],
                detail=item["detail"],
                start_week=item["start_week"],
                end_week=item["end_week"],
                status=status,
                date=date,
                days_left=(date - g.today).days,
            )
        )
    return result


def build_card(
    g: Gestation,
    config: Optional[dict] = None,
    weeks: Optional[Dict[int, dict]] = None,
    checkups: Optional[List[dict]] = None,
    meals: Optional[dict] = None,
) -> DailyCard:
    config = config or {}
    weeks = weeks if weeks is not None else load_weeks()
    checkups = checkups if checkups is not None else load_checkups()
    meals = meals if meals is not None else load_meals()

    entry = week_entry(weeks, g.week)
    diet = build_diet(g, meals, weeks)
    statuses = checkup_status(g, checkups, g.week)

    now = [c for c in statuses if c.status == "now"]
    upcoming = [c for c in statuses if c.status == "upcoming" and c.start_week > g.week]
    nxt = min(upcoming, key=lambda c: c.start_week) if upcoming else None

    seed = g.today.toordinal()
    card = DailyCard(
        g=g,
        week=entry,
        diet=diet,
        checkup_now=now,
        checkup_next=nxt,
        dad_task=_pick(DAD_TASKS, seed * 7 + 3),
        quote=_pick(QUOTES, seed * 13 + 5),
        weight_text=weight_advice(
            config.get("height_cm"), config.get("pre_weight_kg"), g
        ),
        kick_text="今天别忘了数胎动：早、中、晚各 1 小时，3 次相加 ×4 ≥ 30 次为正常。"
        if g.week >= 28
        else "",
        week_note=diet.note,
    )
    card.tips_extra = _extra_tips(g)
    return card


def _extra_tips(g: Gestation) -> List[str]:
    tips = []
    if g.week >= 28:
        tips.append("左侧卧位睡觉，双腿间夹枕头，能改善胎盘供血。")
    if g.week >= 36:
        tips.append("手机充满电、身份证产检本放门口，随时可以出发。")
    if g.week >= 32:
        tips.append("每天散步 20~30 分钟，有助于分娩，但别走到气喘。")
    if g.trimester == 2:
        tips.append("这是孕期最舒服的阶段，适合安排一次短途放松。")
    if g.trimester == 1:
        tips.append("叶酸每天固定时间吃，设个手机闹钟最不容易忘。")
    return tips


def timeline(g: Gestation, weeks: Dict[int, dict]) -> List[dict]:
    """40 周时间轴，标记已过 / 当前 / 未来。"""
    rows = []
    for week in range(1, 41):
        entry = weeks.get(week, {})
        start = g.lmp + dt.timedelta(days=(week - 1) * 7)
        if week < g.week:
            state = "past"
        elif week == g.week:
            state = "now"
        else:
            state = "future"
        rows.append(
            {
                "week": week,
                "title": entry.get("title", ""),
                "baby": entry.get("baby", ""),
                "start": start.isoformat(),
                "end": (start + dt.timedelta(days=6)).isoformat(),
                "state": state,
            }
        )
    return rows


def history_days(g: Gestation, weeks: Dict[int, dict]) -> List[dict]:
    """从末次月经到今天，每一期的索引（用于往期页面）。"""
    rows = []
    day = g.lmp
    while day <= g.today:
        item = Gestation(g.lmp, day)
        entry = week_entry(weeks, item.week)
        rows.append(
            {
                "date": day.isoformat(),
                "date_cn": "%d月%d日" % (day.month, day.day),
                "weekday": cn_weekday(day),
                "week": item.week,
                "label": item.label,
                "title": entry.get("title", ""),
                "is_today": day == g.today,
            }
        )
        day += dt.timedelta(days=1)
    return rows


def is_public_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    host = url.split("//", 1)[-1].split("/", 1)[0]
    return not (
        host.startswith("127.0.0.1")
        or host.startswith("localhost")
        or host.startswith("192.168.")
        or host.startswith("10.")
        or host.startswith("172.16.")
    )


def markdown(card: DailyCard, url: str = "", config: Optional[dict] = None) -> str:
    """生成微信/Telegram/企微通用的 Markdown 摘要。"""
    config = config or {}
    g = card.g
    size = card.size
    lines = []
    lines.append("## %s" % card.subject)
    lines.append("")
    if url and is_public_url(url) and config.get("push_image", True):
        lines.append("![今日配图](%sassets/week-%02d.webp)" % (url.rstrip("/") + "/", g.week))
        lines.append("")
    lines.append("%s ｜ %s ｜ 预产期 %s（%s）" % (
        friendly_date(g.today), g.trimester_name, g.due.strftime("%Y-%m-%d"),
        _countdown(g),
    ))
    lines.append("")
    lines.append("**宝宝现在**：约 %scm、%sg，大小像%s。" % (size.get("len"), size.get("weight"), size.get("like")))
    lines.append("")
    lines.append("### 本周重点")
    lines.append("> %s" % card.week.get("focus", ""))
    lines.append("")
    lines.append("### 今日饮食（%s）" % card.diet.tag)
    for label, text in card.diet.meals:
        lines.append("- **%s**：%s" % (label, text))
    lines.append("")
    lines.append("> 重点营养素：%s｜饮水 %sml｜盐 <%sg" % (
        "、".join(card.diet.highlights) or "均衡饮食", card.diet.water_ml, card.diet.salt_g,
    ))
    if card.week_note:
        lines.append("> 今日提醒：%s" % card.week_note)
    lines.append("")
    lines.append("### 今日注意")
    for item in card.week.get("precautions", [])[:4]:
        lines.append("- %s" % item)
    lines.append("")
    if card.checkup_now:
        lines.append("### 产检提醒")
        for c in card.checkup_now:
            lines.append("- **%s**（%d~%d 周）：%s" % (c.name, c.start_week, c.end_week, c.detail))
        lines.append("")
    elif card.checkup_next:
        lines.append("### 下一次产检")
        lines.append("- %s：%d 周起（约 %s，还有 %d 天）" % (
            card.checkup_next.name, card.checkup_next.start_week,
            card.checkup_next.date.strftime("%m月%d日"), card.checkup_next.days_left,
        ))
        lines.append("")
    if card.kick_text:
        lines.append("### 胎动")
        lines.append("- %s" % card.kick_text)
        lines.append("")
    lines.append("### 给爸爸的小任务")
    lines.append("- %s" % card.dad_task)
    lines.append("")
    if url:
        lines.append("[查看完整今日卡片](%s)" % url)
        lines.append("")
        lines.append("### 往期")
        yesterday = g.today - dt.timedelta(days=1)
        if yesterday >= g.lmp:
            lines.append(
                "- [昨天的卡片](%sday/%s) ｜ [全部往期](%shistory)"
                % (url.rstrip("/") + "/", yesterday.isoformat(), url.rstrip("/") + "/")
            )
        else:
            lines.append("- [全部往期](%shistory)" % (url.rstrip("/") + "/"))
        lines.append("")
    lines.append("---")
    lines.append("内容仅供健康参考，具体请遵医嘱。")
    return "\n".join(lines)


def plain_text(card: DailyCard, url: str = "") -> str:
    """纯文本摘要（短信 / 不支持 markdown 的通道）。"""
    g = card.g
    size = card.size
    parts = [
        "【%s】" % card.subject,
        "%s，%s，预产期 %s。" % (friendly_date(g.today), _countdown(g), g.due.strftime("%Y-%m-%d")),
        "",
        "宝宝约 %scm、%sg，大小像%s。" % (size.get("len"), size.get("weight"), size.get("like")),
        "",
        "本周重点：%s" % card.week.get("focus", ""),
        "",
        "今日饮食：",
    ]
    for label, text in card.diet.meals:
        parts.append("· %s：%s" % (label, text))
    parts.append("")
    parts.append("今日注意：")
    for item in card.week.get("precautions", [])[:4]:
        parts.append("· %s" % item)
    if card.checkup_now:
        parts.append("")
        parts.append("产检提醒：" + "；".join("%s（%d~%d周）" % (c.name, c.start_week, c.end_week) for c in card.checkup_now))
    parts.append("")
    parts.append("给爸爸：%s" % card.dad_task)
    if url:
        parts.append("详情：%s" % url)
    parts.append("——内容仅供参考，请遵医嘱。")
    return "\n".join(parts)


def _countdown(g: Gestation) -> str:
    if g.remaining_days > 0:
        return "距预产期 %d 天" % g.remaining_days
    if g.remaining_days == 0:
        return "今天是预产期"
    return "已过预产期 %d 天" % (-g.remaining_days)
