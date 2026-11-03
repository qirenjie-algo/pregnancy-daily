"""检查导出的静态站点里是否有断链（href/src 指向不存在的文件）。"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')


def main(site_dir: str) -> int:
    site = Path(site_dir).resolve()
    pages = sorted(site.rglob("*.html"))
    missing = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for link in LINK_RE.findall(text):
            if link.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            target = (page.parent / unquote(link.split("#", 1)[0])).resolve()
            try:
                exists = target.exists()
            except OSError:
                exists = False
            if not exists:
                missing.append((str(page.relative_to(site)), link))
    print("页面数：%d，素材数：%d" % (len(pages), len(list(site.rglob('*.*')))))
    if missing:
        print("断链：%d" % len(missing))
        for page, link in missing[:20]:
            print("  %s -> %s" % (page, link))
        return 1
    print("没有断链 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
