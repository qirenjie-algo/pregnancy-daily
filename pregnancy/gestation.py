"""孕周计算引擎。

所有计算都以「末次月经第一天（LMP）」为基准：
    - 预产期 EDD = LMP + 280 天（40 周）
    - 孕龄 GA（天）= 今天 - LMP
    - 孕周 week = GA // 7，不足一周的天数 day = GA % 7
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

GESTATION_DAYS = 280  # 40 周
# 三个孕期按「已满周数」划分：T1 0~13w6d，T2 14w0d~27w6d，T3 28w0d 起
TRIMESTER_LIMITS = (14 * 7 - 1, 28 * 7 - 1)  # 97, 195（含）

TRIMESTER_NAMES = {1: "孕早期", 2: "孕中期", 3: "孕晚期"}


def parse_date(value) -> dt.date:
    """接受 date / datetime / 'YYYY-MM-DD' / 'YYYY/MM/DD'。"""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        text = value.strip().replace("/", "-").replace(".", "-")
        return dt.date.fromisoformat(text)
    raise TypeError("无法识别的日期: %r" % (value,))


def due_date(lmp: dt.date) -> dt.date:
    """内格勒法则：LMP + 280 天。"""
    return lmp + dt.timedelta(days=GESTATION_DAYS)


def week_of(days: int) -> int:
    """孕龄天数 -> 孕周（向下取整，第 1 周为 0~6 天）。"""
    if days < 0:
        return 0
    return days // 7 + 1


@dataclass(frozen=True)
class Gestation:
    """某一时刻的孕期状态。"""

    lmp: dt.date
    today: dt.date

    # ---------- 基础量 ----------
    @property
    def days(self) -> int:
        """孕龄天数（可为负，表示还没到末次月经）。"""
        return (self.today - self.lmp).days

    @property
    def due(self) -> dt.date:
        return due_date(self.lmp)

    @property
    def week(self) -> int:
        """当前孕周，1 起算；超过 42 周按 42 计。"""
        return min(max(week_of(self.days), 1), 42)

    @property
    def day(self) -> int:
        """本周内第几天，0~6。"""
        if self.days < 0:
            return 0
        return self.days % 7

    @property
    def trimester(self) -> int:
        if self.days <= TRIMESTER_LIMITS[0]:
            return 1
        if self.days <= TRIMESTER_LIMITS[1]:
            return 2
        return 3

    @property
    def trimester_name(self) -> str:
        return TRIMESTER_NAMES[self.trimester]

    @property
    def remaining_days(self) -> int:
        """距预产期天数，可为负（已过预产期）。"""
        return (self.due - self.today).days

    @property
    def progress(self) -> float:
        """孕期进度 0~1。"""
        return min(max(self.days / GESTATION_DAYS, 0.0), 1.0)

    # ---------- 展示 ----------
    @property
    def label(self) -> str:
        """临床写法：孕 8 周 + 6 天（满 8 周再加 6 天）。"""
        if self.days < 0:
            return "备孕期"
        done = self.days // 7
        rest = self.days % 7
        if rest == 0:
            return "孕%d周" % done
        return "孕%d周+%d天" % (done, rest)

    @property
    def short_label(self) -> str:
        return "%dW%dD" % (self.days // 7, self.days % 7) if self.days >= 0 else "备孕"

    @property
    def week_start(self) -> dt.date:
        """本周第一天（含）。"""
        return self.lmp + dt.timedelta(days=(self.week - 1) * 7)

    @property
    def week_end(self) -> dt.date:
        return self.week_start + dt.timedelta(days=6)

    def day_of(self, date: dt.date) -> "Gestation":
        """同一 LMP 下另一天的状态。"""
        return Gestation(self.lmp, date)

    def as_dict(self) -> dict:
        return {
            "lmp": self.lmp.isoformat(),
            "today": self.today.isoformat(),
            "due": self.due.isoformat(),
            "days": self.days,
            "week": self.week,
            "day": self.day,
            "label": self.label,
            "short_label": self.short_label,
            "trimester": self.trimester,
            "trimester_name": self.trimester_name,
            "remaining_days": self.remaining_days,
            "progress": round(self.progress, 4),
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
        }


def week_range(lmp: dt.date, week: int) -> Tuple[dt.date, dt.date]:
    """第 N 周对应的日历区间（周一起算的天数偏移）。"""
    start = lmp + dt.timedelta(days=(week - 1) * 7)
    return start, start + dt.timedelta(days=6)


def countdown_text(days: int) -> str:
    if days > 0:
        return "距离预产期还有 %d 天" % days
    if days == 0:
        return "今天是预产期"
    return "已超过预产期 %d 天" % (-days)


def cn_weekday(date: dt.date) -> str:
    return "一二三四五六日"[date.weekday()]


def friendly_date(date: dt.date) -> str:
    return "%d月%d日 周%s" % (date.month, date.day, cn_weekday(date))


def parse_lmp(value, fallback: Optional[dt.date] = None) -> dt.date:
    try:
        return parse_date(value)
    except (TypeError, ValueError):
        if fallback is not None:
            return fallback
        raise
