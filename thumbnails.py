#!/usr/bin/env python3
"""
thumbnails.py - high-CTR thumbnails for DevOps Genius Zone (v3.4.0).

Used by devops_365_bot.py (1280x720, long videos) and shorts_bot.py
(1080x1920, Shorts). Pure Pillow, runs on the GitHub runner.

What makes a tech thumbnail get clicked (and what this draws):
  * 2-4 huge words, readable at phone size (~160 px wide in the feed):
    Anton display font, white with a thick black outline, ONE word in
    yellow so the eye has a single entry point.
  * A big, consistent face (the same AI presenter on every video builds
    recognition - viewers learn "that guy explains DevOps well").
  * One concrete visual object that creates curiosity: a terminal "status
    badge" with the real error/result (CrashLoopBackOff, 0 DOWNTIME...).
    Red = pain, green = fix.
  * High contrast: near-black background, coloured glow behind the face.
  * No clutter: no day counter, no channel name, no full title (YouTube
    already prints the title right under the thumbnail).

Honesty: the headline/badge come from the video's own script (see the
prompts) - the thumbnail must promise what the video actually delivers.
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "assets" / "fonts"

YELLOW = (255, 214, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
CYAN = (0, 190, 255)
RED = (255, 64, 64)
GREEN = (60, 230, 120)
BG_TOP = (8, 12, 26)
BG_BOTTOM = (2, 3, 8)

_DISPLAY = [FONT_DIR / "Anton-Regular.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/impact.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")]
_UI_BOLD = [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf")]
_MONO_BOLD = [Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
              Path("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
              Path("C:/Windows/Fonts/consolab.ttf")]
_font_cache: dict = {}

# Person cut-out (face pops off the background with an outline + glow - the
# standard high-CTR look). u2net_human_seg (Apache-2.0, via the rembg project)
# runs on onnxruntime, which Kokoro already installs. Optional: without it the
# portrait is blended in with a soft fade instead.
U2NET_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
U2NET_PATH = Path(os.environ.get("U2NET_MODEL", str(HERE / "models" / "u2net" / "u2net_human_seg.onnx")))
THUMB_CUTOUT = os.environ.get("THUMB_CUTOUT", "true").strip().lower() not in ("0", "false", "no", "off")
_cutout_cache: dict = {}


def _font(kind: str, size: int):
    key = (kind, size)
    if key not in _font_cache:
        paths = {"display": _DISPLAY, "ui": _UI_BOLD, "mono": _MONO_BOLD}[kind]
        font = None
        for p in paths:
            if p.exists():
                try:
                    font = ImageFont.truetype(str(p), size)
                    break
                except Exception:
                    continue
        _font_cache[key] = font or ImageFont.load_default()
    return _font_cache[key]


def display_font_available() -> bool:
    return (FONT_DIR / "Anton-Regular.ttf").exists()


# ---------------------------------------------------------------- helpers
def _clean_words(text: str, max_words: int) -> list[str]:
    text = re.sub(r"[#*_`\"“”]", "", str(text or "")).strip()
    return text.upper().split()[:max_words]


def pick_highlight(words: list[str], highlight: str | None) -> int:
    """Index of the word to colour yellow: the one Gemini chose, else the
    first number / strong word, else the last word."""
    if highlight:
        h = re.sub(r"\W", "", highlight.upper())
        for i, w in enumerate(words):
            if re.sub(r"\W", "", w) == h:
                return i
    strong = {"STOP", "NEVER", "FIX", "FIXED", "FAST", "ZERO", "DOWN", "BROKE", "BROKEN", "WRONG",
              "FAIL", "FAILS", "FAILED", "KILLED", "LEAK", "DELETE", "DELETED", "SECRET", "HIRED", "FREE"}
    for i, w in enumerate(words):
        core = re.sub(r"\W", "", w)
        if core.isdigit() or core in strong:
            return i
    return len(words) - 1 if words else -1


def _layout_headline(draw, words, max_w, max_lines, start_px, min_px, max_h=10**6):
    """Largest size at which the words fit in max_lines lines of max_w."""
    for px in range(start_px, min_px - 1, -4):
        font = _font("display", px)
        lines, cur = [], []
        for w in words:
            trial = cur + [w]
            if draw.textlength(" ".join(trial), font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = [w]
        if cur:
            lines.append(cur)
        if (len(lines) <= max_lines and len(lines) * int(px * 0.98) <= max_h
                and all(draw.textlength(" ".join(l), font=font) <= max_w for l in lines)):
            return lines, font, px
    return lines[:max_lines], font, px


def _draw_headline(img, lines, font, px, x, y, hi_index, align="left", box_w=None, line_gap=0.98):
    """White words with a thick black outline + soft shadow; one yellow word."""
    stroke = max(4, px // 14)
    line_h = int(px * line_gap)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=font)
    positions = []
    idx = 0
    cy = y
    for line in lines:
        widths = [d.textlength(w, font=font) for w in line]
        total = sum(widths) + space * (len(line) - 1)
        cx = x + ((box_w - total) / 2 if align == "center" and box_w else 0)
        for w, ww in zip(line, widths):
            positions.append((cx, cy, w, idx))
            cx += ww + space
            idx += 1
        cy += line_h
    for cx, cy2, w, _ in positions:
        sd.text((cx + px * 0.05, cy2 + px * 0.06), w, font=font, fill=(0, 0, 0, 200),
                stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(px * 0.06)))
    d = ImageDraw.Draw(img)
    for cx, cy2, w, i in positions:
        d.text((cx, cy2), w, font=font, fill=YELLOW if i == hi_index else WHITE,
               stroke_width=stroke, stroke_fill=BLACK)
    return cy


def _rounded(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)


def _badge_image(text: str, kind: str, px: int) -> Image.Image:
    """Terminal-style status pill: '✗ CrashLoopBackOff' / '✓ 0 DOWNTIME'."""
    good = str(kind).lower() in ("success", "fix", "fixed", "good", "ok")
    color = GREEN if good else RED
    mark = "✓" if good else "✗"
    text = re.sub(r"\s+", " ", str(text)).strip()[:26]
    font = _font("mono", px)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    label = f"{mark} {text}"
    tw = int(tmp.textlength(label, font=font))
    pad_x, pad_y = int(px * 0.6), int(px * 0.42)
    w, h = tw + pad_x * 2, int(px * 1.25) + pad_y * 2
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([24, 26, 24 + w, 26 + h], radius=int(px * 0.45), fill=(0, 0, 0, 170))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([18, 18, 18 + w, 18 + h], radius=int(px * 0.45), fill=(14, 16, 20, 255),
                        outline=color + (255,), width=max(3, px // 9))
    d.text((18 + pad_x, 18 + pad_y + int(px * 0.08)), label, font=font, fill=color + (255,))
    return im.rotate(-4 if not good else 3, resample=Image.BICUBIC, expand=True)


def _chip(draw, x, y, text, px, fill=CYAN, fg=(6, 10, 20)):
    font = _font("ui", px)
    text = str(text).upper()[:22]
    tw = draw.textlength(text, font=font)
    _rounded(draw, [x, y, x + tw + px * 1.1, y + px * 1.55], int(px * 0.35), fill=fill)
    draw.text((x + px * 0.55, y + px * 0.22), text, font=font, fill=fg)
    return x + tw + px * 1.1


def _background(w, h, glow_xy, glow_color, glow_r):
    bg = Image.new("RGB", (w, h))
    top, bot = BG_TOP, BG_BOTTOM
    grad = Image.linear_gradient("L").resize((w, h))
    bg = Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), grad)
    d = ImageDraw.Draw(bg)
    step = max(40, w // 22)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(18, 26, 46), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(18, 26, 46), width=1)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gx, gy = glow_xy
    ImageDraw.Draw(glow).ellipse([gx - glow_r, gy - glow_r, gx + glow_r, gy + glow_r], fill=glow_color + (150,))
    glow = glow.filter(ImageFilter.GaussianBlur(glow_r * 0.45))
    bg = bg.convert("RGBA")
    bg.alpha_composite(glow)
    return bg


def _cutout(host_image, host: Image.Image):
    """RGBA portrait with the background removed, or None."""
    if not THUMB_CUTOUT:
        return None
    key = (str(host_image), host.size)
    if key in _cutout_cache:
        return _cutout_cache[key]
    result = None
    try:
        import numpy as np
        import onnxruntime as ort
        if not U2NET_PATH.exists() or U2NET_PATH.stat().st_size < 1_000_000:
            U2NET_PATH.parent.mkdir(parents=True, exist_ok=True)
            print("[THUMB] Downloading the person-cutout model (176 MB, cached afterwards)...")
            tmp = U2NET_PATH.with_suffix(".part")
            with urllib.request.urlopen(U2NET_URL, timeout=180) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.replace(U2NET_PATH)
        sess = ort.InferenceSession(str(U2NET_PATH), providers=["CPUExecutionProvider"])
        x = np.asarray(host.convert("RGB").resize((320, 320), Image.LANCZOS), dtype=np.float32)
        x = x / max(float(x.max()), 1e-6)
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        pred = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
        pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
        mask = Image.fromarray((pred * 255).astype("uint8")).resize(host.size, Image.LANCZOS)
        if np.asarray(mask).mean() < 8:  # nothing found - not a person photo
            raise RuntimeError("no person detected")
        result = host.convert("RGBA")
        result.putalpha(mask)
        print("[THUMB] Presenter cut out from the background.")
    except Exception as exc:
        print(f"[THUMB] Cut-out unavailable ({exc}) - using the soft-fade portrait.")
    _cutout_cache[key] = result
    return result


def _place_cutout(canvas, person, box, glow_col, head_frac=0.80, outline=10):
    """Fit the top head_frac of the cut-out into box (bottom-anchored, may
    bleed off the canvas) with a coloured glow + white outline behind it."""
    x0, y0, bw, bh = box
    pw, ph = person.size
    src = person.crop((0, 0, pw, int(ph * head_frac)))
    scale = bh / src.height
    src = src.resize((max(1, int(src.width * scale)), bh), Image.LANCZOS)
    px = x0 + (bw - src.width) // 2
    alpha = src.getchannel("A")
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow = Image.new("L", canvas.size, 0)
    glow.paste(alpha, (px, y0))
    big = glow.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.GaussianBlur(40))
    layer.paste(Image.new("RGBA", canvas.size, glow_col + (255,)), (0, 0), big)
    canvas.alpha_composite(layer)
    ring = glow.filter(ImageFilter.MaxFilter(outline * 2 + 1)).filter(ImageFilter.GaussianBlur(1.2))
    canvas.paste(Image.new("RGBA", canvas.size, WHITE + (255,)), (0, 0), ring)
    canvas.alpha_composite(src, (px, y0))


def _load_host(host_image):
    if not host_image:
        return None
    try:
        return Image.open(host_image).convert("RGB")
    except Exception as exc:
        print(f"[THUMB] Presenter image not used: {exc}")
        return None


def _smooth(ramp):
    return ramp.point(lambda v: int(255 * ((v / 255) ** 2) * (3 - 2 * v / 255)))


def _place_host(canvas, host, box, fade_left=0, fade_bottom=0, head_frac=0.72, vignette=False):
    """Cover-fit the top `head_frac` of the portrait (head + shoulders, so
    the face is BIG) into box, with soft fades into the background."""
    x0, y0, bw, bh = box
    hw, hh = host.size
    src = host.crop((0, 0, hw, int(hh * head_frac)))
    sw, sh_ = src.size
    scale = max(bw / sw, bh / sh_)
    src = src.resize((int(sw * scale) + 1, int(sh_ * scale) + 1), Image.LANCZOS)
    left = (src.width - bw) // 2
    src = src.crop((left, 0, left + bw, bh))
    mask = Image.new("L", (bw, bh), 255)
    if fade_left:
        ramp = _smooth(Image.linear_gradient("L").rotate(90, expand=True).resize((fade_left, bh)).transpose(Image.FLIP_LEFT_RIGHT))
        mask.paste(ramp, (0, 0))
    if fade_bottom:
        ramp = _smooth(Image.linear_gradient("L").resize((bw, fade_bottom)).transpose(Image.FLIP_TOP_BOTTOM))
        m2 = Image.new("L", (bw, bh), 255)
        m2.paste(ramp, (0, bh - fade_bottom))
        from PIL import ImageChops
        mask = ImageChops.multiply(mask, m2)
    if vignette:
        from PIL import ImageChops
        v = Image.new("L", (bw, bh), 0)
        r = int(min(bw, bh) * 0.12)
        ImageDraw.Draw(v).ellipse([r, r // 2, bw - r, bh + bh // 3], fill=255)
        mask = ImageChops.multiply(mask, v.filter(ImageFilter.GaussianBlur(r)))
    canvas.paste(src, (x0, y0), mask)


def _save(img, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = img.convert("RGB")
    for q in (92, 85, 78):
        rgb.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if path.stat().st_size < 1_900_000:  # YouTube limit is 2 MB
            break
    return path


# ---------------------------------------------------------------- long video 1280x720
def long_thumbnail(out_path, headline: str, highlight: str = "", tool: str = "",
                   badge: str = "", badge_kind: str = "error", host_image=None) -> Path:
    W, H = 1280, 720
    good = str(badge_kind).lower() in ("success", "fix", "fixed", "good", "ok")
    glow_col = (0, 150, 90) if good else (200, 30, 40)
    host = _load_host(host_image)
    img = _background(W, H, (1000, 330) if host else (980, 360), glow_col, 380)

    text_w = 700 if host else 1180
    person = _cutout(host_image, host) if host else None
    if person is not None:
        _place_cutout(img, person, (720, 40, 560, H - 40), glow_col)
    elif host:
        _place_host(img, host, (640, 0, 640, H), fade_left=260, fade_bottom=0)
        # coloured light over the portrait's own backdrop so it melts into ours
        tint = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(tint).ellipse([700, -200, 1500, 900], fill=glow_col + (55,))
        img.alpha_composite(tint.filter(ImageFilter.GaussianBlur(120)))

    d = ImageDraw.Draw(img)
    y = 46
    if tool:
        _chip(d, 48, y, tool, 30)
        y += 68
    words = _clean_words(headline, 5) or ["DEVOPS"]
    hi = pick_highlight(words, highlight)
    max_lines = 3
    b = _badge_image(badge, badge_kind, 40) if badge else None
    avail_top, avail_bot = y, H - (b.height + 10 if b else 40)
    lines, font, px = _layout_headline(d, words, text_w - 70, max_lines, 190, 64, max_h=avail_bot - avail_top)
    block_h = int(px * 0.98) * len(lines)
    hy = avail_top + max(0, (avail_bot - avail_top - block_h) // 2)
    end_y = _draw_headline(img, lines, font, px, 48, hy, hi)
    if b:
        img.alpha_composite(b, (30, min(H - b.height, end_y + int(px * 0.12))))
    return _save(img, out_path)


# ---------------------------------------------------------------- Shorts 1080x1920
def short_thumbnail(out_path, headline: str, highlight: str = "", tool: str = "",
                    badge: str = "", badge_kind: str = "error", host_image=None) -> Path:
    """Vertical cover. YouTube shows Shorts in the feed cropped to roughly
    the centre 3:2-ish band, so face + headline live in y 520..1400."""
    W, H = 1080, 1920
    good = str(badge_kind).lower() in ("success", "fix", "fixed", "good", "ok")
    glow_col = (0, 150, 90) if good else (200, 30, 40)
    host = _load_host(host_image)
    img = _background(W, H, (540, 760), glow_col, 520)
    person = _cutout(host_image, host) if host else None
    if person is not None:
        _place_cutout(img, person, (90, 400, 900, 760), glow_col, head_frac=0.62)
    elif host:
        _place_host(img, host, (40, 380, 1000, 840), fade_bottom=300, vignette=True)
    d = ImageDraw.Draw(img)
    if tool:
        tf = _font("ui", 40)
        tw = d.textlength(str(tool).upper()[:22], font=tf) + 44
        _chip(d, int((W - tw) / 2), 300, tool, 40)
    words = _clean_words(headline, 5) or ["DEVOPS"]
    hi = pick_highlight(words, highlight)
    b = _badge_image(badge, badge_kind, 52) if badge else None
    top = 1010 if host else 620
    bottom = 1640 - (b.height if b else 0)
    lines, font, px = _layout_headline(d, words, W - 120, 3, 230, 90, max_h=bottom - top)
    end_y = _draw_headline(img, lines, font, px, 60, top, hi, align="center", box_w=W - 120)
    if b:
        img.alpha_composite(b, (int((W - b.width) / 2), end_y + int(px * 0.1)))
    return _save(img, out_path)


if __name__ == "__main__":  # quick local preview
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else None
    out = Path("thumb_preview")
    long_thumbnail(out / "long_error.jpg", "Pods Keep Crashing", "CRASHING", "Kubernetes",
                   "CrashLoopBackOff", "error", host)
    long_thumbnail(out / "long_fix.jpg", "Deploy With Zero Downtime", "ZERO", "GitHub Actions",
                   "0 DOWNTIME", "success", host)
    long_thumbnail(out / "long_nohost.jpg", "Stop Terraform State Locks", "STOP", "Terraform",
                   "Error acquiring state lock", "error", None)
    short_thumbnail(out / "short.jpg", "Ansible Flag That Saves Prod", "SAVES", "Ansible",
                    "--check --diff", "success", host)
    print("written to", out.resolve())
