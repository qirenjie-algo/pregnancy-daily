"""生成孕期动态高清图（动画 WebP）与缩略图。

设计：按孕期配色做柔和渐变 + 光斑，中央是「宝宝大小」的水果隐喻，
叠加呼吸式光晕、缓慢浮动与粒子，循环播放，无文字（文字由页面渲染，保持清晰与可翻译）。

用法：
    python -m pregnancy.assets --out web/assets          # 补齐缺失的素材
    python -m pregnancy.assets --out web/assets --force  # 全部重新生成
"""

from __future__ import annotations

import argparse
import math
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .content import load_weeks
from .visuals import PALETTES, emoji_for

CANVAS = (720, 405)
THUMB = (240, 135)
FRAMES = 14
DURATION = 80  # ms/帧，约 1.1 秒一个循环

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
]


def _emoji_font(size: int) -> Optional[ImageFont.FreeTypeFont]:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def _gradient(size: Tuple[int, int], top, bottom) -> Image.Image:
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        pixels[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize(size, Image.BILINEAR)


def _bokeh(size: Tuple[int, int], color, seed: int) -> Image.Image:
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(5):
        radius = rng.randint(90, 190)
        x = rng.randint(-40, width + 40)
        y = rng.randint(-60, height + 60)
        alpha = rng.randint(28, 70)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(48))


def _emoji_layer(char: str, size: int) -> Image.Image:
    """把彩色 emoji 渲染成透明背景的 RGBA 图。"""
    font = _emoji_font(size)
    if font is None:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((size // 2, size // 2), char, font=font, embedded_color=True)
    bbox = canvas.getbbox()
    if not bbox:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glyph = canvas.crop(bbox)
    scale = size / max(glyph.width, glyph.height)
    return glyph.resize((max(1, int(glyph.width * scale)), max(1, int(glyph.height * scale))), Image.LANCZOS)


def _particles(layer: Image.Image, width: int, height: int, t: float, seed: int, color):
    draw = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(18):
        base_x = rng.uniform(0, width)
        base_y = rng.uniform(0, height)
        radius = rng.uniform(1.6, 4.6)
        speed = rng.uniform(20, 55)
        phase = rng.uniform(0, math.tau)
        y = (base_y - speed * t) % (height + 40) - 20
        alpha = int(35 + 55 * abs(math.sin(math.tau * (t * 0.8) + phase)))
        draw.ellipse(
            (base_x - radius, y - radius, base_x + radius, y + radius),
            fill=color + (alpha,),
        )


def _heart(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, color, alpha: int = 90, steps: int = 28):
    points = []
    for i in range(steps):
        t = math.tau * i / steps
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((cx + x * size / 16, cy + y * size / 16))
    draw.polygon(points, fill=color + (alpha,))


def render_frames(like: str, trimester: int, seed: int = 0, frames: int = FRAMES) -> List[Image.Image]:
    palette = PALETTES.get(trimester, PALETTES[1])
    width, height = CANVAS
    base = _gradient((width, height), palette["top"], palette["bottom"]).convert("RGBA")
    base = Image.alpha_composite(base, _bokeh((width, height), palette["bokeh"], seed))

    char = emoji_for(like)
    glyph = _emoji_layer(char, 240)
    glow_color = palette["glow"]
    accent = palette["accent"]
    rng = random.Random(seed + 3)
    hearts = []
    for _ in range(4):
        side = rng.choice((0, 1))
        hx = rng.uniform(40, width * 0.26) if side == 0 else rng.uniform(width * 0.74, width - 40)
        hearts.append((hx, rng.uniform(70, height - 60), rng.uniform(13, 20), rng.uniform(0, math.tau)))

    result = []
    for index in range(frames):
        t = index / frames
        frame = base.copy()

        # 中央聚光 + 暖色光晕
        spot = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(spot)
        pulse = 0.5 + 0.5 * math.sin(math.tau * t)
        sdraw.ellipse(
            (width // 2 - 210, height // 2 - 190, width // 2 + 210, height // 2 + 170),
            fill=(255, 255, 255, 70),
        )
        sdraw.ellipse(
            (width // 2 - 160 - 14 * pulse, height // 2 - 140 - 14 * pulse,
             width // 2 + 160 + 14 * pulse, height // 2 + 140 + 14 * pulse),
            fill=glow_color + (int(95 + 40 * pulse),),
        )
        frame = Image.alpha_composite(frame, spot.filter(ImageFilter.GaussianBlur(46)))

        # 浮动的水果 + 投影
        bob = math.sin(math.tau * t) * 9
        scale = 1 + 0.025 * math.sin(math.tau * t + 0.6)
        size = (max(1, int(glyph.width * scale)), max(1, int(glyph.height * scale)))
        item = glyph.resize(size, Image.LANCZOS)

        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shdraw = ImageDraw.Draw(shadow)
        sy = height // 2 + size[1] // 2 - 16
        shdraw.ellipse(
            (width // 2 - size[0] // 3, sy - 10, width // 2 + size[0] // 3, sy + 10),
            fill=(110, 70, 55, 52),
        )
        frame = Image.alpha_composite(frame, shadow.filter(ImageFilter.GaussianBlur(13)))

        frame.alpha_composite(item, (width // 2 - size[0] // 2, int(height // 2 - size[1] // 2 - 10 + bob)))

        # 粒子与漂浮的心
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        _particles(layer, width, height, t, seed + 7, (255, 255, 255))
        ldraw = ImageDraw.Draw(layer)
        for hx, hy, hsize, phase in hearts:
            y = hy - 26 * ((t + phase) % 1.0)
            alpha = int(60 + 70 * abs(math.sin(math.tau * ((t + phase) % 1.0))))
            _heart(ldraw, hx, y, hsize, accent, alpha)
        frame = Image.alpha_composite(frame, layer)

        result.append(ImageEnhance.Color(frame.convert("RGB")).enhance(1.12))
    return result


# ---------------------------------------------------------------------------
# 风格二：动物城（原创动物角色 + 城市天际线 + 霓虹窗景）
# ---------------------------------------------------------------------------
MASCOTS = ["🐰", "🦊", "🐨", "🐼", "🐯", "🐻"]

CITY_PALETTES: Dict[int, Dict] = {
    1: {
        "sky_top": (255, 226, 202),
        "sky_bottom": (255, 168, 140),
        "building": (124, 84, 94),
        "window": (255, 226, 162),
        "ground": (156, 101, 99),
        "sun": (255, 244, 210),
        "accent": (232, 115, 90),
        "cloud": (255, 248, 240),
    },
    2: {
        "sky_top": (210, 242, 232),
        "sky_bottom": (132, 198, 178),
        "building": (72, 102, 108),
        "window": (255, 248, 212),
        "ground": (88, 122, 112),
        "sun": (255, 252, 228),
        "accent": (86, 152, 112),
        "cloud": (255, 255, 255),
    },
    3: {
        "sky_top": (252, 228, 246),
        "sky_bottom": (172, 146, 220),
        "building": (88, 66, 122),
        "window": (255, 226, 152),
        "ground": (112, 84, 142),
        "sun": (255, 242, 216),
        "accent": (150, 120, 190),
        "cloud": (255, 250, 255),
    },
}


def _city_layout(width: int, seed: int) -> List[List[float]]:
    """生成一次楼群布局，所有帧复用，保证建筑不跳动。"""
    rng = random.Random(seed)
    buildings: List[List[float]] = []
    x = -30.0
    while x < width + 30:
        w = rng.randint(46, 92)
        h = rng.randint(96, 232)
        buildings.append([x, w, h, rng.random()])
        x += w + rng.randint(8, 20)
    return buildings


def _mix(c1, c2, k: float):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


def _draw_city(frame: Image.Image, buildings: List[List[float]], palette: Dict, t: float, far: bool = False) -> None:
    width, height = frame.size
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    base_y = height - (8 if far else 0)
    color = _mix(palette["building"], palette["sky_bottom"], 0.45) if far else palette["building"]
    scale = 0.72 if far else 1.0
    for i, (bx, bw, bh, _seed) in enumerate(buildings):
        h = bh * scale
        top = base_y - h
        draw.rectangle((bx, top, bx + bw, base_y), fill=color + (255 if not far else 175,))
        draw.rectangle((bx, top, bx + bw, top + 3), fill=palette["accent"] + (70 if far else 110,))
        cols = max(2, int(bw // 20))
        rows = max(2, int(h // 24))
        for r in range(rows):
            for c in range(cols):
                if (r * 7 + c * 3 + i) % 4 == 0:
                    continue
                wx = bx + 10 + c * 18
                wy = top + 14 + r * 22
                if wx + 7 > bx + bw - 6:
                    continue
                flicker = 0.55 + 0.45 * math.sin(math.tau * t * 2 + i * 1.7 + r * 0.9 + c * 0.6)
                alpha = int((150 if far else 220) * flicker)
                draw.rectangle((wx, wy, wx + 7, wy + 9), fill=palette["window"] + (alpha,))
    frame.alpha_composite(layer)


def _draw_sky(frame: Image.Image, palette: Dict, t: float, seed: int, hour: int) -> None:
    width, height = frame.size
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    # 日月（放在左侧，右侧留给徽章）
    cx, cy, r = int(width * 0.16), 82, 38
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((cx - r - 30, cy - r - 30, cx + r + 30, cy + r + 30), fill=palette["sun"] + (85,))
    frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(26)))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=palette["sun"] + (240,))

    if hour < 3:  # 白天：云
        rng = random.Random(seed + 11)
        for _ in range(3):
            bx = rng.randint(120, width - 120)
            by = rng.randint(40, 120)
            drift = 8 * math.sin(math.tau * t + bx * 0.01)
            draw.ellipse((bx + drift, by, bx + 110 + drift, by + 32), fill=palette["cloud"] + (95,))
            draw.ellipse((bx + 26 + drift, by - 14, bx + 86 + drift, by + 22), fill=palette["cloud"] + (95,))
    else:  # 夜晚：星星
        rng = random.Random(seed + 13)
        for _ in range(36):
            sx = rng.randint(0, width)
            sy = rng.randint(8, 180)
            radius = rng.uniform(1.0, 2.4)
            alpha = int(90 + 120 * abs(math.sin(math.tau * t + sx * 0.05)))
            draw.ellipse((sx - radius, sy - radius, sx + radius, sy + radius), fill=(255, 255, 255, alpha))
    frame.alpha_composite(layer)


def render_city_frames(
    week: int,
    like: str,
    trimester: int,
    seed: int = 0,
    frames: int = FRAMES,
    hour: Optional[int] = None,
) -> List[Image.Image]:
    """动物城风格：双层城市天际线，动物居民站在屋顶，右侧是「宝宝大小」徽章。"""
    palette = CITY_PALETTES.get(trimester, CITY_PALETTES[1])
    width, height = CANVAS
    if hour is None:
        hour = 3 if trimester == 3 else 1  # 孕晚期用夜景

    base = _gradient((width, height), palette["sky_top"], palette["sky_bottom"]).convert("RGBA")
    far_buildings = _city_layout(width, seed)
    near_buildings = _city_layout(width, seed + 1)

    mascot = MASCOTS[(week - 1) % len(MASCOTS)]
    fruit = emoji_for(like)
    fruit_glyph = _emoji_layer(fruit, 52) if fruit else None

    # 窗边与屋顶的动物居民
    small_glyphs = [_emoji_layer(MASCOTS[(week + i) % len(MASCOTS)], 54) for i in range(3)]
    roof_glyph = _emoji_layer(mascot, 78)

    resident_spots = []
    picks = [b for i, b in enumerate(near_buildings) if i % 3 == 1][:3]
    for i, (bx, bw, bh, _s) in enumerate(picks):
        top = height - bh
        sy = top + 24 + (i % 2) * 22
        sy = min(max(sy, 56), height - 96)
        sx = min(max(bx + bw / 2, 52), width - 52)
        resident_spots.append((sx, sy))
    if len(near_buildings) > 4:
        rb = near_buildings[len(near_buildings) // 2]
        roof_spot = (rb[0] + rb[1] / 2, height - rb[2])
    else:
        roof_spot = (width / 2, height - 90)

    rng = random.Random(seed + 5)
    hearts = [
        (rng.uniform(60, width * 0.28) if i % 2 == 0 else rng.uniform(width * 0.72, width - 60),
         rng.uniform(110, height - 130), rng.uniform(10, 15), rng.uniform(0, math.tau))
        for i in range(4)
    ]

    result = []
    for index in range(frames):
        t = index / frames
        frame = base.copy()

        _draw_sky(frame, palette, t, seed, hour)
        # 地平线暖光
        haze = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        hz = ImageDraw.Draw(haze)
        hz.ellipse((-120, height - 190, width + 120, height + 60), fill=palette["sun"] + (55,))
        frame = Image.alpha_composite(frame, haze.filter(ImageFilter.GaussianBlur(40)))
        _draw_city(frame, far_buildings, palette, t, far=True)
        _draw_city(frame, near_buildings, palette, t, far=False)

        # 窗边的居民：轻轻探头
        for i, ((sx, sy), glyph) in enumerate(zip(resident_spots, small_glyphs)):
            bob = math.sin(math.tau * t + i * 1.3) * 2.5
            frame.alpha_composite(glyph, (int(sx - glyph.width / 2), int(sy - glyph.height / 2 + bob)))

        # 屋顶上的居民
        rx, ry = roof_spot
        bob = math.sin(math.tau * t + 0.6) * 3.5
        frame.alpha_composite(
            roof_glyph,
            (int(rx - roof_glyph.width / 2), int(ry - roof_glyph.height + 4 + bob)),
        )

        # 「宝宝大小」徽章
        if fruit_glyph is not None:
            bx, by, br = width - 70, 72, 40
            pulse = 1 + 0.02 * math.sin(math.tau * t + 1.2)
            br = int(br * pulse)
            badge = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            bdraw = ImageDraw.Draw(badge)
            bdraw.ellipse((bx - br - 8, by - br - 8, bx + br + 8, by + br + 8), fill=(255, 255, 255, 70))
            bdraw.ellipse((bx - br, by - br, bx + br, by + br), fill=(255, 255, 255, 235))
            bdraw.ellipse((bx - br, by - br, bx + br, by + br), outline=palette["accent"] + (190,), width=3)
            frame = Image.alpha_composite(frame, badge)
            frame.alpha_composite(fruit_glyph, (bx - fruit_glyph.width // 2, by - fruit_glyph.height // 2))

        # 漂浮的心
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer)
        for hx, hy, hsize, phase in hearts:
            y = hy - 24 * ((t + phase) % 1.0)
            alpha = int(50 + 70 * abs(math.sin(math.tau * ((t + phase) % 1.0))))
            _heart(ldraw, hx, y, hsize, (255, 255, 255), alpha)
        frame = Image.alpha_composite(frame, layer)

        result.append(ImageEnhance.Color(frame.convert("RGB")).enhance(1.08))
    return result


def save_webp(frames: Sequence[Image.Image], path: Path, quality: int = 82) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        path,
        "WEBP",
        save_all=True,
        append_images=list(frames[1:]),
        duration=DURATION,
        loop=0,
        quality=quality,
        method=4,
    )


def save_thumb(frame: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.resize(THUMB, Image.LANCZOS).save(path, "PNG", optimize=True)


def generate_all(
    out_dir: Path,
    force: bool = False,
    weeks: Optional[Dict[int, dict]] = None,
    style: str = "city",
) -> Dict[str, int]:
    weeks = weeks or load_weeks()
    out_dir = Path(out_dir)
    stats = {"made": 0, "skipped": 0}
    for week in range(1, 43):
        entry = weeks.get(week) or {}
        like = (entry.get("size") or {}).get("like", "")
        trimester = 1 if week <= 13 else (2 if week <= 27 else 3)
        webp_path = out_dir / ("week-%02d.webp" % week)
        thumb_path = out_dir / ("week-%02d.png" % week)
        if not force and webp_path.exists() and thumb_path.exists():
            stats["skipped"] += 1
            continue
        if style == "fruit":
            frames = render_frames(like, trimester, seed=week * 31)
        else:
            frames = render_city_frames(week, like, trimester, seed=week * 31)
        save_webp(frames, webp_path)
        save_thumb(frames[0], thumb_path)
        stats["made"] += 1
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成孕期动态图素材")
    parser.add_argument("--out", default="web/assets")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--style", choices=("city", "fruit"), default="city", help="city=动物城风格，fruit=水果隐喻")
    args = parser.parse_args(argv)
    stats = generate_all(Path(args.out), force=args.force, style=args.style)
    print("生成完成（%s）：新增 %d 周，跳过 %d 周 -> %s" % (args.style, stats["made"], stats["skipped"], args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
