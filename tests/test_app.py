"""基础测试：孕周算法、内容完整性、渲染与 HTTP 接口。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pregnancy.content import (  # noqa: E402
    build_card,
    load_checkups,
    load_meals,
    load_weeks,
    markdown,
    plain_text,
    timeline,
    week_entry,
)
from pregnancy.gestation import Gestation, due_date, parse_date, week_of  # noqa: E402
from pregnancy.push import build_message, dispatch, preview_payload  # noqa: E402

LMP = dt.date(2026, 9, 2)
TODAY = dt.date(2026, 11, 3)  # 孕 62 天 = 8 周 6 天 = 第 9 周


class TestGestation(unittest.TestCase):
    def test_due_date(self):
        self.assertEqual(due_date(LMP), dt.date(2027, 6, 9))

    def test_basic_numbers(self):
        g = Gestation(LMP, TODAY)
        self.assertEqual(g.days, 62)
        self.assertEqual(g.label, "孕8周+6天")
        self.assertEqual(g.week, 9)          # 第 9 周（内容按周序号）
        self.assertEqual(g.day, 6)
        self.assertEqual(g.trimester, 1)
        self.assertEqual(g.remaining_days, 218)
        self.assertAlmostEqual(g.progress, 62 / 280, places=4)

    def test_trimester_boundaries(self):
        self.assertEqual(Gestation(LMP, LMP + dt.timedelta(days=97)).trimester, 1)
        self.assertEqual(Gestation(LMP, LMP + dt.timedelta(days=98)).trimester, 2)
        self.assertEqual(Gestation(LMP, LMP + dt.timedelta(days=195)).trimester, 2)
        self.assertEqual(Gestation(LMP, LMP + dt.timedelta(days=196)).trimester, 3)

    def test_week_start_end(self):
        g = Gestation(LMP, TODAY)
        # 第 9 周 = 末次月经后 56~62 天 = 10-28 ~ 11-03
        self.assertEqual(g.week_start, dt.date(2026, 10, 28))
        self.assertEqual(g.week_end, dt.date(2026, 11, 3))

    def test_before_lmp(self):
        g = Gestation(LMP, LMP - dt.timedelta(days=5))
        self.assertEqual(g.label, "备孕期")
        self.assertEqual(g.progress, 0.0)
        self.assertEqual(g.week, 1)

    def test_parse_variants(self):
        self.assertEqual(parse_date("2026-09-02"), LMP)
        self.assertEqual(parse_date("2026/09/02"), LMP)
        self.assertEqual(parse_date(dt.datetime(2026, 9, 2, 8, 0)), LMP)

    def test_week_of(self):
        self.assertEqual(week_of(0), 1)
        self.assertEqual(week_of(6), 1)
        self.assertEqual(week_of(7), 2)
        self.assertEqual(week_of(62), 9)


class TestContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weeks = load_weeks()
        cls.config = {"lmp": LMP.isoformat(), "height_cm": 165, "pre_weight_kg": 55}

    def test_all_weeks_present(self):
        self.assertEqual(sorted(self.weeks), list(range(1, 43)))

    def test_week_fields(self):
        required = ["title", "baby", "mom", "focus", "nutrition", "precautions", "tip", "size"]
        for week, entry in self.weeks.items():
            for key in required:
                self.assertIn(key, entry, "第 %d 周缺少 %s" % (week, key))
            self.assertTrue(entry["precautions"], "第 %d 周注意事项为空" % week)
            self.assertIn("like", entry["size"])

    def test_card_shape(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        self.assertEqual(card.subject, "孕8周+6天｜开始会动了")
        self.assertEqual(len(card.diet.meals), 6)
        self.assertEqual(card.diet.meals[0][0], "早餐")
        self.assertTrue(card.diet.highlights)
        self.assertTrue(card.dad_task)
        self.assertTrue(card.weight_text)
        self.assertEqual(card.kick_text, "")  # 28 周前不提示数胎动

    def test_kick_count_late(self):
        card = build_card(Gestation(LMP, LMP + dt.timedelta(days=200)), self.config)
        self.assertIn("数胎动", card.kick_text)

    def test_diet_rotation_is_deterministic(self):
        g = Gestation(LMP, TODAY)
        a = build_card(g, self.config).diet.meals
        b = build_card(g, self.config).diet.meals
        self.assertEqual(a, b)
        next_day = build_card(Gestation(LMP, TODAY + dt.timedelta(days=1)), self.config).diet.meals
        self.assertNotEqual(a, next_day)

    def test_checkups(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        # 9 周时首次 B 超窗口已过，建档/NT 还未到
        self.assertEqual(card.checkup_now, [])
        self.assertIsNotNone(card.checkup_next)
        self.assertEqual(card.checkup_next.name, "建档 + 早期系统检查")
        self.assertEqual(card.checkup_next.days_left, 8)  # 11 周起 = 11-11

    def test_checkup_in_window(self):
        card = build_card(Gestation(LMP, LMP + dt.timedelta(days=11 * 7)), self.config)
        names = [c.name for c in card.checkup_now]
        self.assertIn("NT 检查", names)
        self.assertIn("建档 + 早期系统检查", names)

    def test_markdown(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        text = markdown(card, "http://127.0.0.1:8787/")
        self.assertIn("孕8周+6天", text)
        self.assertIn("今日饮食", text)
        self.assertIn("http://127.0.0.1:8787/", text)
        self.assertNotIn("%s", text)
        self.assertGreater(len(text), 300)

    def test_plain_text(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        text = plain_text(card)
        self.assertIn("【孕8周+6天", text)
        self.assertIn("早餐", text)

    def test_timeline(self):
        rows = timeline(Gestation(LMP, TODAY), self.weeks)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0]["state"], "past")
        self.assertEqual(rows[8]["state"], "now")
        self.assertEqual(rows[9]["state"], "future")

    def test_fallback_week(self):
        self.assertTrue(week_entry(self.weeks, 99))
        self.assertEqual(week_entry({}, 9), {})

    def test_message(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        msg = build_message(card, self.config, "http://x/")
        self.assertEqual(msg.title, card.subject)
        self.assertIn("孕8周+6天", msg.markdown)
        self.assertLessEqual(len(msg.clipped_markdown(200).encode("utf-8")), 200)

    def test_dry_run_dispatch(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        msg = build_message(card, self.config, "")
        cfg = {"channels": [{"name": "测试", "type": "bark", "key": "k"}]}
        results = dispatch(cfg, msg, dry_run=True)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertIn("dry-run", results[0]["detail"])

    def test_unknown_channel(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        msg = build_message(card, self.config, "")
        results = dispatch({"channels": [{"name": "x", "type": "nope"}]}, msg, dry_run=False)
        self.assertFalse(results[0]["ok"])

    def test_preview_payload(self):
        card = build_card(Gestation(LMP, TODAY), self.config)
        msg = build_message(card, self.config, "http://x/")
        payload = preview_payload(self.config, msg)
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["title"], card.subject)


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app = app_module
        app_module.Handler.config = {
            "lmp": LMP.isoformat(),
            "push_time": "07:30",
            "port": 8787,
            "base_url": "",
            "channels": [],
            "_today": TODAY.isoformat(),  # 冻结「今天」，避免跨零点导致测试漂移
        }
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_home(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("孕8周+6天", body)
        self.assertIn("今日饮食", body)
        self.assertIn("今日注意", body)
        self.assertIn("给爸爸的小任务", body)

    def test_api_today(self):
        status, body = self.get("/api/today")
        data = json.loads(body)
        self.assertEqual(data["gestation"]["week"], 9)
        self.assertEqual(len(data["diet"]["meals"]), 6)
        json.dumps(data, ensure_ascii=False)

    def test_timeline(self):
        status, body = self.get("/timeline")
        self.assertEqual(status, 200)
        self.assertIn("第 9 周", body)

    def test_week_page(self):
        status, body = self.get("/week/9")
        self.assertEqual(status, 200)
        self.assertIn("开始会动了", body)

    def test_week_out_of_range(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/week/99")
        self.assertEqual(ctx.exception.code, 404)

    def test_health(self):
        status, body = self.get("/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_manifest_and_sw(self):
        for path, needle in (("/manifest.json", "孕期日历"), ("/sw.js", "addEventListener"), ("/icon.svg", "<svg")):
            status, body = self.get(path)
            self.assertEqual(status, 200)
            self.assertIn(needle, body)

    def test_home_has_banner(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('src="/assets/week-09.webp"', body)
        self.assertIn("全部往期", body)

    def test_history_page(self):
        status, body = self.get("/history")
        self.assertEqual(status, 200)
        self.assertIn("往期回顾", body)
        self.assertIn("第 9 周", body)
        self.assertIn('href="/day/2026-11-03"', body)

    def test_day_page(self):
        status, body = self.get("/day/2026-10-28")
        self.assertEqual(status, 200)
        self.assertIn("孕8周", body)
        status, body = self.get("/day/2026-11-03")
        self.assertIn("孕8周+6天", body)

    def test_day_out_of_range(self):
        for bad in ("/day/2026-12-01", "/day/2026-08-01", "/day/not-a-date"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(bad)
            self.assertEqual(ctx.exception.code, 404)

    def test_assets(self):
        with urllib.request.urlopen("http://127.0.0.1:%d/assets/week-09.webp" % self.port, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/webp")
            data = resp.read()
        self.assertEqual(data[:4], b"RIFF")
        self.assertGreater(len(data), 1000)
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/assets/..%2fapp.py")


class TestPushTransport(unittest.TestCase):
    """用本地回显服务验证真实 HTTP 投递与当日去重。"""

    received = []

    @classmethod
    def setUpClass(cls):
        outer = cls

        class Echo(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                outer.received.append(json.loads(body))
                payload = b'{"code":0,"msg":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

        import pregnancy.store as store

        cls._orig_log = store.LOG_PATH
        store.LOG_PATH = Path(tempfile.mkdtemp()) / "push_log.jsonl"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        import pregnancy.store as store

        store.LOG_PATH = cls._orig_log

    def test_webhook_delivery_and_dedupe(self):
        config = {"lmp": LMP.isoformat()}
        card = build_card(Gestation(LMP, TODAY), config)
        msg = build_message(card, config, "http://127.0.0.1:8787/")
        cfg = {
            "channels": [
                {"name": "本地回显", "type": "webhook", "url": "http://127.0.0.1:%d/hook" % self.port}
            ]
        }
        results = dispatch(cfg, msg, date=TODAY)
        self.assertTrue(results[0]["ok"], results[0]["detail"])
        self.assertEqual(self.received[-1]["title"], card.subject)
        self.assertIn("孕8周+6天", self.received[-1]["markdown"])
        self.assertIn("http://127.0.0.1:8787/", self.received[-1]["url"])

        before = len(self.received)
        again = dispatch(cfg, msg, date=TODAY)
        self.assertTrue(again[0]["ok"])
        self.assertIn("跳过", again[0]["detail"])
        self.assertEqual(len(self.received), before)

        forced = dispatch(cfg, msg, date=TODAY, force=True)
        self.assertTrue(forced[0]["ok"])
        self.assertEqual(len(self.received), before + 1)


class TestHistory(unittest.TestCase):
    def test_history_days(self):
        from pregnancy.content import history_days

        g = Gestation(LMP, TODAY)
        rows = history_days(g, load_weeks())
        self.assertEqual(len(rows), 63)  # 9/2 到 11/3 共 63 期
        self.assertEqual(rows[0]["date"], "2026-09-02")
        self.assertEqual(rows[-1]["date"], "2026-11-03")
        self.assertTrue(rows[-1]["is_today"])
        self.assertEqual(rows[-1]["week"], 9)
        self.assertIn("title", rows[-1])

    def test_public_url(self):
        from pregnancy.content import is_public_url

        self.assertTrue(is_public_url("https://user.github.io/pregnancy/"))
        self.assertFalse(is_public_url("http://127.0.0.1:8787/"))
        self.assertFalse(is_public_url("http://192.168.1.20:8787/"))
        self.assertFalse(is_public_url(""))

    def test_markdown_links(self):
        card = build_card(Gestation(LMP, TODAY), {"lmp": LMP.isoformat()})
        text = markdown(card, "https://example.com/preg/", {"push_image": True})
        self.assertIn("![今日配图](https://example.com/preg/assets/week-09.webp)", text)
        self.assertIn("[昨天的卡片](https://example.com/preg/day/2026-11-02)", text)
        self.assertIn("[全部往期](https://example.com/preg/history)", text)

        local = markdown(card, "http://127.0.0.1:8787/", {"push_image": True})
        self.assertNotIn("![今日配图]", local)


class TestExport(unittest.TestCase):
    def test_export_site(self):
        import tempfile
        from pathlib import Path as P

        from pregnancy.site import export_site

        with tempfile.TemporaryDirectory() as tmp:
            out = P(tmp) / "site"
            stats = export_site({"lmp": LMP.isoformat(), "push_time": "07:30"}, out, today=TODAY)
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "day" / "2026-11-03.html").exists())
            self.assertTrue((out / "day" / "2026-11-03" / "index.html").exists())
            self.assertTrue((out / "week" / "09.html").exists())
            self.assertTrue((out / "history.html").exists())
            self.assertTrue((out / "history" / "index.html").exists())
            self.assertTrue((out / "assets" / "week-09.webp").exists())
            self.assertGreaterEqual(stats["pages"], 63 + 40 + 3)

            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('href="/', index)
            self.assertNotIn('src="/', index)
            self.assertIn('src="assets/week-09.webp"', index)
            self.assertIn('href="day/2026-11-02.html"', index)

            day_page = (out / "day" / "2026-10-28.html").read_text(encoding="utf-8")
            self.assertIn('src="../assets/week-', day_page)
            self.assertIn('href="../history.html"', day_page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
