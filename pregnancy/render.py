"""移动端 H5 渲染：今日卡片 / 往期 / 周详情 / 40 周时间轴。"""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path
from typing import Dict, List, Optional

from .content import DailyCard
from .gestation import Gestation, friendly_date
from .visuals import MEAL_ICONS, emoji_for

APP_NAME = "孕期日历"
ASSET_DIR = Path(__file__).resolve().parent.parent / "web" / "assets"

CSS = """
:root{
  --bg:#fdf6f1; --card:#ffffff; --ink:#3b3230; --muted:#8d7f7a;
  --accent:#e8735a; --accent2:#f4a261; --line:#f0e4dd; --ok:#5f9e6e;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:16px; line-height:1.65; padding-bottom:78px;
}
.wrap{max-width:520px;margin:0 auto;padding:18px 16px 8px}
.banner{display:block;width:100%;height:auto;border-radius:20px;margin-bottom:14px;
  box-shadow:0 8px 22px rgba(180,120,100,.16);background:#fff5ef}
.hero{
  background:linear-gradient(135deg,#ffd8c2 0%,#ffc0b0 45%,#f9a88f 100%);
  border-radius:24px;padding:22px 20px 18px;color:#4a2b23;
  box-shadow:0 10px 24px rgba(232,115,90,.18);position:relative;overflow:hidden;
}
.hero:after{content:"";position:absolute;right:-40px;top:-50px;width:150px;height:150px;
  background:rgba(255,255,255,.28);border-radius:50%}
.hero .date{font-size:13px;opacity:.8;letter-spacing:.5px}
.hero h1{margin:6px 0 2px;font-size:30px;letter-spacing:1px;font-weight:700}
.hero .sub{font-size:14px;opacity:.85}
.progress{height:8px;background:rgba(255,255,255,.55);border-radius:99px;margin-top:14px;overflow:hidden}
.progress i{display:block;height:100%;background:#e8735a;border-radius:99px}
.hero .meta{display:flex;justify-content:space-between;font-size:12px;margin-top:6px;opacity:.85}
.card{background:var(--card);border-radius:18px;padding:16px 18px;margin-top:14px;
  box-shadow:0 4px 16px rgba(120,80,60,.06);border:1px solid var(--line)}
.card h2{margin:0 0 10px;font-size:15px;letter-spacing:.5px;display:flex;align-items:center;gap:8px;color:#4a3b36}
.card h2 .ico{font-size:18px}
.card p{margin:0 0 8px}
.muted{color:var(--muted);font-size:13px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;
  background:#fff1ea;color:#c9603f;margin:2px 6px 2px 0;border:1px solid #ffd9c9}
.pill.ok{background:#eef7ef;color:#3f7a52;border-color:#d6ead9}
.meals{list-style:none;padding:0;margin:0}
.meals li{display:flex;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line)}
.meals li:last-child{border:none;padding-bottom:0}
.meals b{flex:0 0 82px;color:#c9603f;font-weight:600;font-size:13.5px}
.meals span{flex:1;font-size:14.5px}
.checks{list-style:none;padding:0;margin:0}
.checks li{padding:10px 12px;border-radius:12px;background:#fff8f4;margin-bottom:8px;border-left:3px solid var(--accent2)}
.checks li.now{background:#fff1e9;border-left-color:var(--accent)}
.checks .t{font-weight:600;font-size:14.5px}
.checks .d{color:var(--muted);font-size:13px;margin-top:2px}
.babybox{display:flex;align-items:center;gap:14px}
.babyicon{font-size:34px;line-height:1;width:44px;text-align:center}
.babybox .num{font-size:19px;font-weight:700;letter-spacing:.3px}
.badge{display:inline-block;background:#3b3230;color:#fff;border-radius:8px;padding:1px 8px;font-size:12px;margin-left:6px;font-weight:400}
.note{background:#fffaf0;border:1px dashed #f0cfa8;border-radius:12px;padding:10px 12px;font-size:13.5px;color:#7a5a3a;margin-top:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.stat{background:#fff8f4;border-radius:12px;padding:10px 12px}
.stat.wide{grid-column:1 / -1}
.stat .k{font-size:12px;color:var(--muted)}
.stat .v{font-size:16px;font-weight:600;margin-top:2px}
.tip{display:flex;gap:8px;font-size:14px;margin-bottom:8px}
.tip:before{content:"•";color:var(--accent);flex:0 0 auto}
.dad{background:linear-gradient(135deg,#fff0e6,#ffe4d6);border:none}
.dad p{font-size:15px}
.quote{font-size:14px;color:#9a7b6c;font-style:italic;text-align:center;padding:4px 0}
.lesson .hook{color:var(--muted);font-size:14px;margin:0 0 10px}
.lesson .sec{font-size:14.5px;margin-bottom:10px;line-height:1.7}
.lesson .sec b{color:#c9603f}
.lesson .note{margin-top:12px}
.safety{background:#fff7f4;border-color:#f6d6c9}
.safety p{font-size:14.5px;margin:0}
.safety b{color:#c9603f}
footer{text-align:center;color:#b7a9a2;font-size:12px;padding:18px 10px 26px;line-height:1.7}
nav{position:fixed;left:0;right:0;bottom:0;background:rgba(255,255,255,.94);
  backdrop-filter:blur(10px);border-top:1px solid var(--line);display:flex;max-width:520px;margin:0 auto;z-index:9}
nav a{flex:1;text-align:center;padding:10px 0 12px;color:var(--muted);text-decoration:none;font-size:12px}
nav a .i{display:block;font-size:19px;margin-bottom:2px}
nav a.on{color:var(--accent);font-weight:600}
.pager{display:flex;align-items:center;justify-content:space-between;gap:8px;
  background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 14px;margin-top:14px;font-size:13.5px}
.pager a{color:var(--accent);text-decoration:none;white-space:nowrap}
.pager span{color:var(--muted);font-size:12.5px}
.timeline{list-style:none;padding:0;margin:0}
.timeline li{position:relative;padding:10px 0 10px 22px;border-left:2px solid var(--line);margin-left:6px}
.timeline li:before{content:"";position:absolute;left:-7px;top:20px;width:12px;height:12px;border-radius:50%;
  background:#fff;border:2px solid var(--line)}
.timeline li.now{border-left-color:var(--accent)}
.timeline li.now:before{background:var(--accent);border-color:var(--accent)}
.timeline li.past:before{background:#e8d5cc;border-color:#e8d5cc}
.timeline a{display:flex;gap:10px;align-items:center;color:inherit;text-decoration:none}
.timeline .thumb{width:58px;height:33px;border-radius:8px;object-fit:cover;flex:0 0 58px;background:#f6ece6}
.timeline .w{font-weight:600;font-size:15px}
.timeline .s{font-size:12.5px;color:var(--muted)}
.timeline li.now .w{color:var(--accent)}
a.plain{color:inherit;text-decoration:none}
.top{display:flex;align-items:center;gap:8px;padding:6px 0 10px}
.top a{color:var(--accent);text-decoration:none;font-size:14px}
h1.page{font-size:22px;margin:6px 0 4px}
.hist-week{font-size:13px;color:var(--muted);margin:18px 4px 6px;letter-spacing:.5px}
.hist{display:flex;gap:12px;align-items:center;background:#fff;border:1px solid var(--line);
  border-radius:14px;padding:10px 12px;margin-bottom:8px;text-decoration:none;color:inherit}
.hist .thumb{width:56px;height:32px;border-radius:8px;object-fit:cover;background:#f6ece6;flex:0 0 56px}
.hist .d{font-size:13px;color:var(--muted)}
.hist .t{font-size:14.5px;font-weight:600}
.hist.now{border-color:var(--accent);background:#fff8f4}
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _page(title: str, body: str, active: str = "today", nav: bool = True) -> str:
    tabs = [
        ("today", "/", "🐣", "今日"),
        ("history", "/history", "🗂️", "往期"),
        ("timeline", "/timeline", "📅", "时间轴"),
        ("about", "/about", "💡", "说明"),
    ]
    nav_html = ""
    if nav:
        items = "".join(
            '<a class="%s" href="%s"><span class="i">%s</span>%s</a>'
            % ("on" if key == active else "", href, icon, label)
            for key, href, icon, label in tabs
        )
        nav_html = "<nav>%s</nav>" % items
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#ffd8c2">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>%s</title>
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<style>%s</style>
</head>
<body>
<div class="wrap">%s</div>
%s
<script>if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(function(){})}</script>
</body>
</html>""" % (_esc(title), CSS, body, nav_html)


def _asset(week: int, ext: str) -> Optional[str]:
    name = "week-%02d.%s" % (week, ext)
    if (ASSET_DIR / name).exists():
        return "/assets/" + name
    return None


def _banner(week: int, alt: str) -> str:
    src = _asset(week, "webp")
    if not src:
        return ""
    return (
        '<img class="banner" src="%s" alt="%s" width="720" height="405" '
        'loading="eager" decoding="async">' % (_esc(src), _esc(alt))
    )


def _thumb(week: int, alt: str) -> str:
    src = _asset(week, "png")
    if not src:
        return ""
    return '<img class="thumb" src="%s" alt="%s" width="240" height="135" loading="lazy">' % (
        _esc(src), _esc(alt),
    )


def _hero(card: DailyCard) -> str:
    g = card.g
    pct = max(2.0, round(g.progress * 100, 1))
    return """
<div class="hero">
  <div class="date">%s</div>
  <h1>%s</h1>
  <div class="sub">%s · 预产期 %s</div>
  <div class="progress"><i style="width:%s%%"></i></div>
  <div class="meta"><span>%s</span><span>已走过 %s%%</span></div>
</div>""" % (
        _esc(friendly_date(g.today)),
        _esc(g.label),
        _esc(g.trimester_name),
        _esc(g.due.strftime("%Y年%m月%d日")),
        pct,
        _esc(_countdown(g)),
        pct,
    )


def _countdown(g: Gestation) -> str:
    if g.remaining_days > 0:
        return "距离预产期 %d 天" % g.remaining_days
    if g.remaining_days == 0:
        return "今天就是预产期"
    return "已超过预产期 %d 天" % (-g.remaining_days)


def _list(items: List[str]) -> str:
    return "".join('<div class="tip">%s</div>' % _esc(i) for i in items if i)


def _pager(g: Gestation, date, earliest, today) -> str:
    prev_date = date - dt.timedelta(days=1)
    next_date = date + dt.timedelta(days=1)
    left = (
        '<a href="/day/%s">‹ %s</a>' % (prev_date.isoformat(), _esc(prev_date.strftime("%m月%d日")))
        if prev_date >= earliest
        else "<span>已是最早一期</span>"
    )
    right = (
        '<a href="/day/%s">%s ›</a>' % (next_date.isoformat(), _esc(next_date.strftime("%m月%d日")))
        if next_date <= today
        else "<span>已是最新一期</span>"
    )
    return (
        '<div class="pager">%s<a href="/history">全部往期</a>%s</div>' % (left, right)
    )


def render_pager(g: Gestation, date) -> str:
    """上一条 / 全部往期 / 下一条。"""
    return _pager(g, date, g.lmp, g.today)


def render_day(card: DailyCard, config: dict, share_url: str = "", pager: str = "") -> str:
    g = card.g
    week = card.week
    size = card.size

    if card.checkup_now:
        rows = "".join(
            '<li class="now"><div class="t">%s · 第 %d~%d 周</div><div class="d">%s</div></li>'
            % (_esc(c.name), c.start_week, c.end_week, _esc(c.detail))
            for c in card.checkup_now
        )
        checkup_html = '<div class="card"><h2><span class="ico">🏥</span>本周要做的产检</h2><ul class="checks">%s</ul></div>' % rows
    elif card.checkup_next:
        c = card.checkup_next
        checkup_html = (
            '<div class="card"><h2><span class="ico">🏥</span>下一次产检</h2>'
            '<ul class="checks"><li><div class="t">%s</div>'
            '<div class="d">%d 周起（约 %s，还有 %d 天）· %s</div></li></ul></div>'
            % (_esc(c.name), c.start_week, _esc(c.date.strftime("%m月%d日")), c.days_left, _esc(c.detail))
        )
    else:
        checkup_html = ""

    meals = "".join(
        '<li><b>%s %s</b><span>%s</span></li>'
        % (_esc(MEAL_ICONS.get(label, "")), _esc(label), _esc(text))
        for label, text in card.diet.meals
    )
    highlights = "".join('<span class="pill">%s</span>' % _esc(h) for h in card.diet.highlights)
    avoid = "".join('<span class="pill">%s</span>' % _esc(a) for a in card.diet.avoid)
    supplements = "".join('<div class="tip">%s</div>' % _esc(s) for s in card.diet.supplements)
    trick_lines = ["%s：%s" % (h.get("title", ""), h.get("detail", "")) for h in card.hacks]
    tips = _list([week.get("tip", "")] + trick_lines + card.tips_extra)

    lesson_html = ""
    if card.lesson:
        sections = "".join(
            '<div class="sec"><b>%s</b>：%s</div>' % (_esc(sec.get("h", "")), _esc(sec.get("p", "")))
            for sec in card.lesson.get("sections", [])
        )
        tip_block = (
            '<div class="note">💡 %s</div>' % _esc(card.lesson["tip"])
            if card.lesson.get("tip")
            else ""
        )
        lesson_html = (
            '<div class="card lesson"><h2><span class="ico">📚</span>科普小课堂 · %s</h2>'
            '<p class="hook">%s</p>%s%s</div>'
            % (
                _esc(card.lesson.get("title", "")),
                _esc(card.lesson.get("hook", "")),
                sections,
                tip_block,
            )
        )

    safety_html = ""
    if card.safety:
        safety_html = (
            '<div class="card safety"><h2><span class="ico">🛡️</span>安全提醒</h2>'
            "<p><b>%s</b>：%s</p></div>"
            % (_esc(card.safety.get("title", "")), _esc(card.safety.get("detail", "")))
        )

    kick = (
        '<div class="card"><h2><span class="ico">👶</span>今日胎动</h2><p>%s</p></div>' % _esc(card.kick_text)
        if card.kick_text else ""
    )

    body = """
%s
%s
<div class="card">
  <h2><span class="ico">🍼</span>宝宝现在 <span class="badge">第 %d 周</span></h2>
  <div class="babybox">
    <div class="babyicon">%s</div>
    <div>
      <div class="num">约 %s cm · %s g</div>
      <div class="muted">大小像%s</div>
    </div>
  </div>
  <p style="margin-top:12px">%s</p>
</div>

<div class="card">
  <h2><span class="ico">🌱</span>本周主题 · %s</h2>
  <p><b>本周重点：</b>%s</p>
  <p><b>妈妈的变化：</b>%s</p>
  <p class="muted"><b>营养重点：</b>%s</p>
</div>

<!--LESSON-->

<div class="card">
  <h2><span class="ico">🍲</span>今日饮食 <span class="badge">%s</span></h2>
  <ul class="meals">%s</ul>
  <div style="margin-top:12px">%s</div>
  <div class="muted" style="margin-top:6px">饮水约 %sml · 盐 &lt;%sg · 蛋白质优先，少油少盐</div>
  %s
</div>

<div class="card">
  <h2><span class="ico">🥗</span>营养与忌口</h2>
  <p class="muted" style="margin:0 0 6px">今日尽量避开</p>
  <div>%s</div>
  <p class="muted" style="margin:12px 0 6px">补剂参考（遵医嘱）</p>
  %s
</div>

<div class="card">
  <h2><span class="ico">⚠️</span>今日注意</h2>
  %s
</div>

<!--SAFETY-->

<div class="card">
  <h2><span class="ico">💡</span>生活小贴士</h2>
  %s
</div>

%s
%s

<div class="card dad">
  <h2><span class="ico">💗</span>给爸爸的小任务</h2>
  <p>%s</p>
</div>

<div class="card">
  <h2><span class="ico">⚖️</span>体重与本周</h2>
  <div class="grid2">
    <div class="stat wide"><div class="k">体重建议</div><div class="v" style="font-size:13.5px;line-height:1.6;font-weight:500">%s</div></div>
    <div class="stat wide"><div class="k">本周日期</div><div class="v" style="font-size:13.5px;font-weight:500">%s 至 %s（%s）</div></div>
  </div>
  <p class="quote" style="margin-top:12px">“%s”</p>
</div>

%s

<footer>
  孕期日历 · 每天 %s 推送<br>
  内容仅供健康科普参考，不能替代医生诊断，具体请遵医嘱。
</footer>
""" % (
        _banner(g.week, "%s · 大小像%s" % (g.label, size.get("like", ""))),
        _hero(card),
        g.week,
        emoji_for(size.get("like", "")),
        _esc(size.get("len")),
        _esc(size.get("weight")),
        _esc(size.get("like", "")),
        _esc(week.get("baby", "")),
        _esc(week.get("title", "")),
        _esc(week.get("focus", "")),
        _esc(week.get("mom", "")),
        _esc(week.get("nutrition", "")),
        _esc(card.diet.tag),
        meals,
        highlights,
        card.diet.water_ml,
        card.diet.salt_g,
        '<div class="note">%s</div>' % _esc(card.week_note) if card.week_note else "",
        avoid,
        supplements,
        _list(week.get("precautions", [])),
        tips,
        kick,
        checkup_html,
        _esc(card.dad_task),
        _esc(card.weight_text),
        _esc(g.week_start.strftime("%m/%d")),
        _esc(g.week_end.strftime("%m/%d")),
        _esc(g.trimester_name),
        _esc(card.quote),
        pager,
        _esc(config.get("push_time", "07:30")),
    )
    body = body.replace("<!--LESSON-->", lesson_html).replace("<!--SAFETY-->", safety_html)
    return _page("%s · %s" % (g.label, APP_NAME), body, "today")


def render_timeline(g: Gestation, rows: List[dict]) -> str:
    items = []
    for row in rows:
        cls = row["state"]
        label = "第 %d 周" % row["week"]
        if row["state"] == "now":
            label += " · 现在"
        items.append(
            '<li class="%s"><a href="/week/%d">%s<div><div class="w">第 %d 周 · %s</div>'
            '<div class="s">%s 至 %s</div></div></a></li>'
            % (cls, row["week"], _thumb(row["week"], row["title"]), row["week"], _esc(row["title"]),
               _esc(row["start"]), _esc(row["end"]))
        )
    body = """
<div class="top"><a href="/">‹ 今日</a></div>
<h1 class="page">40 周时间轴</h1>
<p class="muted">%s · 预产期 %s</p>
<div class="card"><ul class="timeline">%s</ul></div>
<footer>点击任意周可查看当周知识。内容仅供健康科普参考。</footer>""" % (
        _esc(g.label),
        _esc(g.due.strftime("%Y-%m-%d")),
        "".join(items),
    )
    return _page("时间轴 · %s" % APP_NAME, body, "timeline")


def render_week(g: Gestation, week: int, entry: dict) -> str:
    size = entry.get("size") or {}
    body = """
<div class="top"><a href="/timeline">‹ 时间轴</a></div>
%s
<h1 class="page">第 %d 周 · %s</h1>
<p class="muted">%s</p>
<div class="card">
  <h2><span class="ico">🍼</span>宝宝的变化</h2>
  <p>%s</p>
  <div class="muted">约 %s cm · %s g · 大小像%s</div>
</div>
<div class="card">
  <h2><span class="ico">🌱</span>本周重点</h2>
  <p>%s</p>
  <p><b>妈妈的变化：</b>%s</p>
  <p class="muted"><b>营养：</b>%s</p>
</div>
<div class="card">
  <h2><span class="ico">⚠️</span>注意事项</h2>
  %s
</div>
<div class="card">
  <h2><span class="ico">💡</span>小贴士</h2>
  <p>%s</p>
  %s
</div>
<footer>内容仅供健康科普参考，具体请遵医嘱。</footer>""" % (
        _banner(week, "第 %d 周 · %s" % (week, entry.get("title", ""))),
        week,
        _esc(entry.get("title", "")),
        _esc(g.label),
        _esc(entry.get("baby", "")),
        _esc(size.get("len", "-")),
        _esc(size.get("weight", "-")),
        _esc(size.get("like", "-")),
        _esc(entry.get("focus", "")),
        _esc(entry.get("mom", "")),
        _esc(entry.get("nutrition", "")),
        _list(entry.get("precautions", [])),
        _esc(entry.get("tip", "")),
        '<div class="note">产检：%s</div>' % _esc(entry["checkup"]) if entry.get("checkup") else "",
    )
    return _page("第%d周 · %s" % (week, APP_NAME), body, "timeline")


def render_history(g: Gestation, days: List[dict]) -> str:
    blocks = []
    current_week = None
    for item in reversed(days):  # 新的在前
        if item["week"] != current_week:
            current_week = item["week"]
            blocks.append('<div class="hist-week">第 %d 周</div>' % current_week)
        blocks.append(
            '<a class="hist%s" href="/day/%s">%s<div><div class="d">%s · %s</div>'
            '<div class="t">%s</div></div></a>'
            % (
                " now" if item["is_today"] else "",
                item["date"],
                _thumb(item["week"], item["title"]),
                _esc(item["date_cn"]),
                _esc(item["label"]),
                _esc(item["title"]),
            )
        )
    body = """
<div class="top"><a href="/">‹ 今日</a></div>
<h1 class="page">往期回顾</h1>
<p class="muted">共 %d 期 · %s 至 %s</p>
%s
<footer>每一期都会保留，点开即可回看当天的知识与饮食。内容仅供健康科普参考。</footer>""" % (
        len(days),
        _esc(days[0]["date"]),
        _esc(days[-1]["date"]),
        "".join(blocks),
    )
    return _page("往期 · %s" % APP_NAME, body, "history")


def render_about(g: Gestation, config: dict) -> str:
    body = """
<div class="top"><a href="/">‹ 今日</a></div>
<h1 class="page">关于这个小应用</h1>
<div class="card">
  <h2><span class="ico">📆</span>你的孕期档案</h2>
  <div class="grid2">
    <div class="stat"><div class="k">末次月经</div><div class="v">%s</div></div>
    <div class="stat"><div class="k">预产期</div><div class="v">%s</div></div>
    <div class="stat"><div class="k">当前孕周</div><div class="v">%s</div></div>
    <div class="stat"><div class="k">剩余天数</div><div class="v">%d 天</div></div>
  </div>
</div>
<div class="card">
  <h2><span class="ico">⏰</span>推送时间</h2>
  <p>每天 <b>%s</b> 推送到「%s」。</p>
  <p class="muted">推送内容 = 今日孕周 + 胎儿发育 + 本周重点 + 一日六餐 + 注意事项 + 产检提醒 + 给爸爸的任务 + 往期入口。</p>
</div>
<div class="card">
  <h2><span class="ico">🛡️</span>说明</h2>
  <p>孕周按末次月经第一天推算，预产期 = 末次月经 + 280 天，与医院算法一致。</p>
  <p class="muted">全部内容为健康科普，不构成医疗建议；出现出血、腹痛、破水、胎动异常请立即就医。</p>
</div>
<footer>孕期日历 · 本地运行，数据不外传。</footer>""" % (
        _esc(g.lmp.isoformat()),
        _esc(g.due.isoformat()),
        _esc(g.label),
        max(g.remaining_days, 0),
        _esc(config.get("push_time", "07:30")),
        _esc(config.get("channel_label", "微信")),
    )
    return _page("说明 · %s" % APP_NAME, body, "about")


def render_error(message: str, status: int = 404) -> str:
    body = """
<div class="card" style="margin-top:40px;text-align:center">
  <h1 class="page">%d</h1>
  <p>%s</p>
  <p><a class="plain" href="/" style="color:#e8735a">回到今日</a></p>
</div>""" % (status, _esc(message))
    return _page("出错了 · %s" % APP_NAME, body, "today")
