"""把整站导出为静态文件，方便部署到 GitHub Pages / 任意静态托管。

导出的站点不含后端：所有页面在构建时按「当天」生成，含往期全部页面与素材。
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .content import build_card, history_days, load_checkups, load_meals, load_weeks, timeline, week_entry
from .gestation import Gestation, parse_date
from .render import render_about, render_day, render_history, render_timeline, render_week, render_pager

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

LINK_RE_WEEK = re.compile(r'href="/(week)/(\d+)"')
LINK_RE_DAY = re.compile(r'href="/(day)/([0-9-]+)"')
LINK_RE_PAGE = re.compile(r'href="/(timeline|history|about)"')


def rebase(html: str, depth: int) -> str:
    """把以 / 开头的链接改成相对路径，并补上 .html，适配子路径部署。"""
    prefix = "../" * depth
    out = LINK_RE_WEEK.sub(lambda m: 'href="%sweek/%02d.html"' % (prefix, int(m.group(2))), html)
    out = LINK_RE_DAY.sub(lambda m: 'href="%sday/%s.html"' % (prefix, m.group(2)), out)
    out = LINK_RE_PAGE.sub(lambda m: 'href="%s%s.html"' % (prefix, m.group(1)), out)
    out = out.replace('href="/"', 'href="%sindex.html"' % prefix)
    out = out.replace('href="/', 'href="%s' % prefix)
    out = out.replace('src="/', 'src="%s' % prefix)
    out = out.replace("register('/sw.js')", "register('%ssw.js')" % prefix)
    out = out.replace('href="/manifest.json"', 'href="%smanifest.json"' % prefix)
    return out


def _write(path: Path, html: str, depth: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rebase(html, depth), encoding="utf-8")


def export_site(config: dict, out_dir: Path, today: Optional[dt.date] = None) -> Dict[str, int]:
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    weeks = load_weeks()
    meals = load_meals()
    checkups = load_checkups()
    g = Gestation(parse_date(config["lmp"]), today or dt.date.today())

    def card_for(date: dt.date):
        return build_card(Gestation(g.lmp, date), config, weeks=weeks, checkups=checkups, meals=meals)

    stats = {"pages": 0}
    _write(out_dir / "index.html", render_day(card_for(g.today), config, pager=render_pager(g, g.today)), 0)
    stats["pages"] += 1

    for item in history_days(g, weeks):
        date = dt.date.fromisoformat(item["date"])
        day_card = card_for(date)
        day_html = render_day(day_card, config, pager=render_pager(g, date))
        _write(out_dir / "day" / ("%s.html" % item["date"]), day_html, 1)
        # 同时提供 /day/2026-11-03 这样的干净链接（推送里使用）
        _write(out_dir / "day" / item["date"] / "index.html", day_html, 2)
        stats["pages"] += 2

    for week in range(1, 41):
        _write(out_dir / "week" / ("%02d.html" % week), render_week(g, week, week_entry(weeks, week)), 1)
        stats["pages"] += 1

    history_html = render_history(g, history_days(g, weeks))
    _write(out_dir / "history.html", history_html, 0)
    _write(out_dir / "history" / "index.html", history_html, 1)
    _write(out_dir / "timeline.html", render_timeline(g, timeline(g, weeks)), 0)
    _write(out_dir / "about.html", render_about(g, config), 0)
    stats["pages"] += 4

    # 素材与 PWA 文件
    shutil.copytree(WEB_DIR / "assets", out_dir / "assets", dirs_exist_ok=True)
    for name in ("manifest.json", "sw.js", "icon.svg"):
        shutil.copyfile(WEB_DIR / name, out_dir / name)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    stats["assets"] = len(list((out_dir / "assets").glob("*")))
    return stats
