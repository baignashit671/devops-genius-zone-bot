#!/usr/bin/env python3
"""
DevOps Genius Zone — YouTube Shorts bot (v1.0)
==============================================
Makes N vertical Shorts per day (default 2) in the formats that actually
go viral for DevOps channels (the @bashopsOfficial analysis: "DevOps
Roadmap" 990K views, "5 DevOps Projects for a strong resume" 281K, while
promo/testimonial Shorts stayed under 1.5K) - every Short teaches ONE
concrete, useful thing:

  ROADMAP   - step-by-step path to a skill            (their #1 format)
  TOP_N     - "5 projects / 3 tools / 4 commands ..."  (their #2 format)
  COMMAND   - one command/flag that saves hours, shown in a terminal
  INTERVIEW - a real DevOps interview question + the senior-level answer
  MISTAKE   - "stop doing X in production" -> the fix
  VERSUS    - X vs Y: when to use which
  CAREER    - a career/skill insight (salary only from verified BLS data)

Same AI presenter as the long videos (assets/host.png, lip-synced on the
free Kaggle GPU via host_lipsync.py). If Kaggle fails, the Short is still
published - faceless, with big visuals - so a day is never missed.

Reuses the long-video bot's tested building blocks (Kokoro voice, Kaggle
host job, overlay compositor, caption timing, YouTube auth/upload helpers).

Usage:
    python shorts_bot.py               # make + upload today's Shorts
    python shorts_bot.py --test        # build only, no upload
    python shorts_bot.py --count 1
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Separate Kaggle dataset/kernel from the long-video job so the two
# workflows can never overwrite each other's inputs.
os.environ.setdefault("HOST_KAGGLE_DATASET", "devops-shorts-host-inputs")
os.environ.setdefault("HOST_KAGGLE_KERNEL", "devops-shorts-host-lipsync")

import devops_365_bot as core  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

W, H = 1080, 1920
core.TERM_FONT_SIZE = 34   # bigger terminal text for phone screens (long-video default is 30)
# No Ken Burns zoom in Shorts: the presenter/terminal overlays are fixed, and a
# zooming background made their card borders look doubled. Motion comes from
# the presenter, typing terminal, word-by-word captions and crossfades.
core.KEN_BURNS_MAX_ZOOM = 1.0
OUT_DIR = Path("shorts_output")
SHORTS_LOG = Path("shorts_log.json")
SHORTS_PER_DAY = int(os.environ.get("SHORTS_PER_DAY", "2"))
# IST hours each slot goes public (US-friendly: 18:00 IST = 7:30 AM ET,
# 23:00 IST = 12:30 PM ET). Long video stays at 21:00 IST.
SHORTS_PUBLISH_IST_HOURS = [int(x) for x in os.environ.get("SHORTS_PUBLISH_IST_HOURS", "18,23").split(",") if x.strip()]
SHORTS_MAX_SECONDS = float(os.environ.get("SHORTS_MAX_SECONDS", "58"))
SHORTS_PLAYLIST_ID = os.environ.get("SHORTS_PLAYLIST_ID", "").strip()
HOST_ENABLED = core.HOST_ENABLED
HOST_IMAGE = core.HOST_IMAGE
IST = core.IST_TIMEZONE

# Layout (1080x1920). YouTube's Shorts UI covers the bottom ~380 px (title,
# channel, music) and a right column of buttons (x > ~940, y 900-1700), so
# everything important stays inside x 60..940, y 120..1600.
HOST_PANEL = (260, 270, 560, 720)            # x, y, w, h  (native SadTalker 560x720, no upscaling blur)
CARD_WITH_HOST = (60, 1030, 940, 1450)       # content card under the presenter
CARD_FACELESS = (60, 270, 940, 1450)         # big visual when there is no presenter
CAPTION_MARGIN_V = 330                        # captions sit in y ~1500-1590, between the card and YouTube's UI

BG_TOP, BG_BOTTOM = (8, 14, 32), (3, 5, 12)
ACCENT, YELLOW, GREEN, RED, SOFT = (0, 190, 255), (255, 214, 0), (80, 240, 140), (255, 95, 95), (205, 216, 238)

FORMATS = ["ROADMAP", "TOP_N", "COMMAND", "INTERVIEW", "MISTAKE", "VERSUS", "CAREER"]
AREAS = [
    "Kubernetes", "Docker", "Terraform", "AWS", "CI/CD with GitHub Actions", "Linux for DevOps",
    "Git", "Monitoring with Prometheus and Grafana", "DevSecOps", "AI tools for DevOps engineers",
    "Ansible", "Helm and GitOps (Argo CD)",
]
FORMAT_BRIEFS = {
    "ROADMAP": "A step-by-step learning roadmap (4-6 steps) for {area}, in the order a hiring manager in the US would expect. Each step = what to learn + a 1-line proof-of-skill project.",
    "TOP_N": "A numbered list (3-5 items) for {area}: e.g. projects that make a resume stand out, tools worth learning, or commands every engineer should know. Each item must be specific and immediately useful.",
    "COMMAND": "ONE real command or flag for {area} that saves time or prevents an outage. Show it in the terminal, explain what it does, when to use it, and one gotcha.",
    "INTERVIEW": "One real interview question about {area} that US DevOps/SRE interviewers ask, the junior answer that fails, and the senior answer that gets the offer.",
    "MISTAKE": "One common production mistake with {area}, what it breaks, and the exact fix plus how to prevent it.",
    "VERSUS": "A clear X vs Y comparison inside {area} (pick the pair people actually confuse), with 2-3 concrete differences and when to choose each.",
    "CAREER": "A career insight for engineers moving into {area}: which skill to learn next and why it pays off. Only use this verified number if you mention pay: {stat}.",
}


def log(m):
    print(f"[SHORTS] {m}", flush=True)


# ---------------------------------------------------------------- log
def load_shorts_log() -> list:
    if SHORTS_LOG.exists():
        try:
            data = json.loads(SHORTS_LOG.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def save_shorts_log(entries: list):
    SHORTS_LOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_format_and_area(index: int) -> tuple:
    """Deterministic rotation: formats cycle every 7 Shorts, areas every 12,
    so the same format+area pair only repeats after 84 Shorts."""
    return FORMATS[index % len(FORMATS)], AREAS[(index * 5) % len(AREAS)]


# ---------------------------------------------------------------- script
def gemini_short_script(fmt: str, area: str, recent_titles: list, long_video: dict) -> dict:
    if not core.HAS_GEMINI or not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options={"timeout": core.GEMINI_TIMEOUT_SEC * 1000})
    st = core.BLS_STATS["sec"] if "Sec" in area else core.BLS_STATS["dev"]
    stat = f"U.S. Bureau of Labor Statistics, May 2025 median pay for {st['role']}: ${st['pay']:,}"
    brief = FORMAT_BRIEFS[fmt].format(area=area, stat=stat)
    avoid = "\n".join(f"- {t}" for t in recent_titles[-40:]) or "- (none yet)"
    prompt = f"""
You write viral, genuinely useful YouTube Shorts for DevOps Genius Zone, a channel for
working DevOps engineers and people breaking into DevOps in the US. One presenter talks
straight to camera. Every Short must teach ONE concrete thing the viewer can use today.

FORMAT: {fmt}
BRIEF: {brief}

Rules:
- 40-55 seconds spoken: 105-135 words TOTAL across all beats. Never more than 140.
- Beat 1 is the hook, max 14 words, said in the first 2 seconds. It states the payoff or
  the pain ("Five projects that get DevOps resumes past the US recruiter screen.").
  No greeting, no "in this video", no channel name.
- 4-7 beats. Each beat is 1-2 short spoken sentences and has ONE on-screen visual.
- The last beat = the single takeaway + "Follow for a DevOps tip every day."
- Technically correct for current tool versions. Commands must be real (no invented flags).
- Never invent statistics, salaries or quotes. No emojis inside "say".
- Do not repeat these recent titles/topics:
{avoid}

On-screen visual types (field "screen"):
  {{"type":"title","heading":"2-5 WORD HOOK"}}
  {{"type":"list","heading":"short heading","items":["item 1","item 2",...],"highlight":0}}   (max 5 items, each <= 34 chars; highlight = index being explained)
  {{"type":"roadmap","heading":"short heading","items":["step 1","step 2",...],"highlight":0}} (max 6 steps, <= 30 chars each)
  {{"type":"terminal","heading":"short heading","lines":[["cmd","kubectl get pods -A"],["out","..."]]}} (2-6 lines, <= 36 chars per line)
  {{"type":"versus","heading":"X vs Y","left":"X","right":"Y","rows":[["left point","right point"],...]}} (max 3 rows, <= 22 chars per cell)
  {{"type":"tip","heading":"short heading","text":"one key sentence, <= 90 chars"}}

Return ONLY this JSON:
{{
  "title": "under 55 characters, curiosity + payoff, names the tool, no hashtags",
  "hook_text": "2-5 WORDS IN CAPS for the top of the first frame",
  "beats": [{{"say": "...", "screen": {{...}}}}],
  "description": "2-3 sentences: what the viewer learns + why it matters",
  "tags": ["8-12 specific search tags"],
  "hashtags": ["#devops", "#shorts", "2-3 more specific ones"]
}}
"""
    last_exc = None
    for model in core.GEMINI_MODELS:
        for attempt in range(1, 3):
            try:
                log(f"Gemini {model} ({fmt} / {area}) attempt {attempt}")
                resp = client.models.generate_content(model=model, contents=prompt)
                raw = (resp.text or "").strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
                raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                beats = [b for b in data.get("beats", []) if isinstance(b, dict) and str(b.get("say", "")).strip()]
                words = sum(len(str(b["say"]).split()) for b in beats)
                if not (3 <= len(beats) <= 8) or not (70 <= words <= 170) or not str(data.get("title", "")).strip():
                    raise ValueError(f"bad shape: {len(beats)} beats, {words} words")
                data["beats"] = beats
                data["_source"] = f"gemini:{model}"
                return data
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                log(f"{model} failed: {msg[:200]}")
                if re.search(r"\b404\b|NOT_FOUND|not found", msg):
                    break
                time.sleep(10 * attempt)
    raise RuntimeError(f"all Gemini models failed: {last_exc}")


# ---------------------------------------------------------------- audio
def synth_beats(beats: list, workdir: Path, speed: float) -> tuple:
    """One Kokoro clip per beat -> (durations, audio_path)."""
    engine = core._kokoro_engine()
    workdir.mkdir(parents=True, exist_ok=True)
    clips, durs = [], []
    import numpy as np
    for i, b in enumerate(beats):
        samples, sr = engine.create(core._tts_normalize(b["say"]), voice=core.KOKORO_VOICE, speed=speed, lang="en-us")
        samples = np.concatenate([samples, np.zeros(int(sr * 0.12), dtype="float32")])
        p = workdir / f"beat_{i:02d}.wav"
        core._write_wav_pcm16(p, samples, sr)
        clips.append(p)
        durs.append(core._ffprobe_duration(p))
    audio = workdir / "audio.mp3"
    core._concat_clips(clips, audio)
    return durs, audio


# ---------------------------------------------------------------- visuals
def _font(size, bold=True, mono=False):
    if mono:
        name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    else:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except Exception:
        return core._get_font(size, bold)


def _fit(draw, text, max_w, start, minimum, bold=True, mono=False):
    for s in range(start, minimum - 1, -2):
        f = _font(s, bold, mono)
        if draw.textlength(text, font=f) <= max_w:
            return f
    return _font(minimum, bold, mono)


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _background(seed: int) -> Image.Image:
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), BG_BOTTOM), Image.new("RGB", (W, H), BG_TOP), grad)
    glow = Image.new("RGB", (W // 4, H // 4), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    rnd = random.Random(seed)
    for col in (ACCENT, (150, 90, 255)):
        x, y, r = rnd.randint(0, W // 4), rnd.randint(0, H // 4), rnd.randint(90, 160)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(c * 0.35) for c in col))
    glow = glow.filter(ImageFilter.GaussianBlur(40)).resize((W, H))
    from PIL import ImageChops
    return ImageChops.add(img, glow).convert("RGBA")


def _card(img, box, outline=ACCENT, fill=(8, 13, 30, 235), r=34):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, r, fill=fill, outline=(*outline, 170), width=3)
    img.alpha_composite(layer)


def _header(img, d, fmt_label, title_text, step_label=""):
    d.rounded_rectangle([60, 70, 60 + 24 + d.textlength(fmt_label, font=_font(30)) + 24, 124], 26, fill=(*ACCENT, 255))
    d.text((84, 78), fmt_label, font=_font(30), fill=(4, 10, 24))
    if step_label:
        f = _font(30)
        d.text((940 - d.textlength(step_label, font=f), 80), step_label, font=f, fill=SOFT)
    f = _fit(d, title_text, 880, 60, 34)
    d.text((60, 160), title_text, font=f, fill=(255, 255, 255))


def render_beat_frame(beat: dict, fmt: str, hook_text: str, idx: int, total: int, with_host: bool, terminal_reg: dict) -> Image.Image:
    sc = beat.get("screen") or {}
    typ = str(sc.get("type", "tip")).lower()
    img = _background(seed=idx * 7 + len(fmt))
    d = ImageDraw.Draw(img)
    labels = {"ROADMAP": "ROADMAP", "TOP_N": "TOP PICKS", "COMMAND": "COMMAND", "INTERVIEW": "INTERVIEW Q",
              "MISTAKE": "PROD MISTAKE", "VERSUS": "X vs Y", "CAREER": "CAREER"}
    heading = str(sc.get("heading") or hook_text or "")[:60]
    _header(img, d, labels.get(fmt, "DEVOPS"), heading if idx else hook_text.upper(), f"{idx + 1}/{total}")
    if with_host:
        _card(img, (HOST_PANEL[0] - 14, HOST_PANEL[1] - 14, HOST_PANEL[0] + HOST_PANEL[2] + 14, HOST_PANEL[1] + HOST_PANEL[3] + 14),
              outline=ACCENT, fill=(6, 10, 24, 255), r=40)
        box = CARD_WITH_HOST
    else:
        box = CARD_FACELESS
    x0, y0, x1, y1 = box
    big = not with_host

    if typ == "title" or idx == 0:
        _card(img, box, outline=YELLOW)
        text = (sc.get("heading") or hook_text or "").upper()
        f = _font(96 if big else 64)
        lines = _wrap(d, text, f, x1 - x0 - 80)
        lh = int(f.size * 1.15)
        ty = (y0 + y1) // 2 - lh * len(lines) // 2
        for ln in lines:
            d.text(((x0 + x1 - d.textlength(ln, font=f)) / 2, ty), ln, font=f, fill=YELLOW)
            ty += lh
        return img

    if typ in ("list", "roadmap"):
        items = [str(i)[:40] for i in (sc.get("items") or [])][:6] or [beat["say"][:40]]
        hi = int(sc.get("highlight", 0) or 0)
        _card(img, box)
        n = len(items)
        row_h = min(150 if big else 62, (y1 - y0 - 50) // max(n, 1))
        fs = 46 if big else 34
        ty = y0 + (y1 - y0 - row_h * n) // 2
        for k, it in enumerate(items):
            active = k == hi
            col = YELLOW if active else SOFT
            if active:
                d.rounded_rectangle([x0 + 24, ty + 4, x1 - 24, ty + row_h - 6], 20, fill=(40, 34, 0, 255))
            num = f"{k + 1}" if typ == "list" else f"{k + 1}"
            nf = _font(fs)
            cx = x0 + 70
            d.ellipse([cx - fs * 0.7, ty + row_h / 2 - fs * 0.7, cx + fs * 0.7, ty + row_h / 2 + fs * 0.7],
                      fill=(*(YELLOW if active else ACCENT), 255))
            d.text((cx - d.textlength(num, font=nf) / 2, ty + row_h / 2 - fs * 0.62), num, font=nf, fill=(5, 8, 20))
            f = _fit(d, it, x1 - x0 - 190, fs, 24, bold=active)
            d.text((x0 + 130, ty + row_h / 2 - f.size * 0.62), it, font=f, fill=col)
            if typ == "roadmap" and k < n - 1:
                d.line([(cx, ty + row_h / 2 + fs * 0.7), (cx, ty + row_h * 1.5 - fs * 0.7)], fill=(*ACCENT, 255), width=4)
            ty += row_h
        return img

    if typ == "terminal":
        lines = []
        for ln in (sc.get("lines") or [])[:8]:
            if isinstance(ln, (list, tuple)) and len(ln) == 2:
                lines.append(("cmd" if str(ln[0]).lower() == "cmd" else "out", str(ln[1])[:60]))
            elif isinstance(ln, str):
                lines.append(("cmd", ln[2:]) if ln.startswith("$ ") else ("out", ln))
        lines = lines or [("cmd", "echo 'DevOps Genius Zone'")]
        tbox = (x0, y0, x1, y1)
        core._terminal_window(img, tbox, title="bash")
        terminal_reg["base"] = img.convert("RGB").copy()
        terminal_reg["box"] = tbox
        terminal_reg["lines"] = lines
        core._draw_terminal_lines(img, tbox, lines, reveal=None)
        return img

    if typ == "versus":
        _card(img, box)
        left, right = str(sc.get("left", "A"))[:16], str(sc.get("right", "B"))[:16]
        rows = [r for r in (sc.get("rows") or []) if isinstance(r, (list, tuple)) and len(r) == 2][:3]
        mid = (x0 + x1) // 2
        hf = _font(52 if big else 38)
        d.text((x0 + (mid - x0 - d.textlength(left, font=hf)) / 2, y0 + 30), left, font=hf, fill=RED)
        d.text((mid + (x1 - mid - d.textlength(right, font=hf)) / 2, y0 + 30), right, font=hf, fill=GREEN)
        d.line([(mid, y0 + 30), (mid, y1 - 30)], fill=(*ACCENT, 160), width=3)
        rf = _font(36 if big else 26, bold=False)
        ty = y0 + (130 if big else 90)
        step = (y1 - ty - 30) // max(len(rows), 1)
        for a, b in rows:
            for txt, cx0, cx1 in ((str(a), x0 + 30, mid - 20), (str(b), mid + 20, x1 - 30)):
                wl = _wrap(d, txt, rf, cx1 - cx0)[:3]
                yy = ty
                for ln in wl:
                    d.text((cx0, yy), ln, font=rf, fill=SOFT)
                    yy += int(rf.size * 1.25)
            ty += step
        return img

    # tip (default)
    _card(img, box, outline=GREEN)
    text = str(sc.get("text") or beat["say"])[:120]
    f = _font(58 if big else 40)
    lines = _wrap(d, text, f, x1 - x0 - 100)[:6]
    lh = int(f.size * 1.25)
    ty = (y0 + y1) // 2 - lh * len(lines) // 2
    for ln in lines:
        d.text((x0 + 50, ty), ln, font=f, fill=(255, 255, 255))
        ty += lh
    return img


# ---------------------------------------------------------------- captions
def build_vertical_ass(beats: list, durs: list, path: Path) -> Path:
    slides = [("body", b["say"], dur, "ACT 1") for b, dur in zip(beats, durs)]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,7,3,2,80,150,{CAPTION_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for start, end, grp in core._timed_caption_groups(slides, max_chars=20, max_words=4):
        for k, (w_, ws, we) in enumerate(grp):
            parts = []
            for j, (w2, _, _) in enumerate(grp):
                t = core._ass_escape(w2.upper())
                parts.append("{\\c&H00D6FF&\\fscx110\\fscy110}" + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}" if j == k else t)
            events.append(f"Dialogue: 0,{core._ass_time(ws)},{core._ass_time(we)},Cap,,0,0,0,,{' '.join(parts)}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


def build_srt(beats: list, durs: list, path: Path) -> Path:
    slides = [("body", b["say"], dur, "ACT 1") for b, dur in zip(beats, durs)]
    cues, prev = [], 0.0
    for i, (s, e, grp) in enumerate(core._timed_caption_groups(slides, max_chars=72, max_words=14), 1):
        s, e = max(s, prev), max(e, max(s, prev) + 0.6)
        cues.append(f"{i}\n{core._srt_timestamp(s)} --> {core._srt_timestamp(e)}\n{core._two_lines(' '.join(w for w, _, _ in grp), 34)}\n")
        prev = e
    path.write_text("\n".join(cues), encoding="utf-8")
    return path


# ---------------------------------------------------------------- video
def build_short_video(short: dict, durs: list, audio: Path, out: Path, host_clip) -> dict:
    work = out.parent / (out.stem + "_frames")
    work.mkdir(parents=True, exist_ok=True)
    beats, fmt = short["beats"], short["_format"]
    with_host = host_clip is not None
    frames, terminals = [], []
    for i, b in enumerate(beats):
        reg = {}
        img = render_beat_frame(b, fmt, short.get("hook_text", ""), i, len(beats), with_host, reg)
        p = work / f"beat_{i:02d}.png"
        img.convert("RGB").save(p)
        frames.append((p, durs[i]))
        if reg:
            terminals.append((i, reg))
    temp = out.parent / (out.stem + "_temp.mp4")
    core._render_with_motion(frames, temp, W, H)

    starts, t = [], 0.0
    for dd in durs:
        starts.append(t)
        t += dd
    overlays = []
    for i, reg in terminals:
        clip = work / f"term_{i:02d}.mp4"
        try:
            x, y, w, h = core._render_terminal_typing_clip(reg, durs[i], clip)
            overlays.append({"path": clip, "start": starts[i], "dur": durs[i], "x": x, "y": y, "w": w, "h": h, "fade_in": False})
        except Exception as exc:
            log(f"terminal typing skipped: {exc}")
    if with_host:
        px, py, pw, ph = HOST_PANEL
        mask_p, frame_p, pad = core._host_assets(pw, ph)
        overlays.append({"path": host_clip, "start": 0.0, "dur": sum(durs), "x": px, "y": py, "w": pw, "h": ph,
                         "mask": mask_p, "frame": frame_p, "pad": pad, "fade_in": False})
    ass = build_vertical_ass(beats, durs, out.parent / (out.stem + ".ass"))
    try:
        core._compose_final(temp, audio, out, overlays, ass)
    except Exception as exc:
        log(f"compose with overlays failed ({str(exc)[-300:]}) - retrying captions only")
        core._compose_final(temp, audio, out, [], ass)
        with_host = False
    temp.unlink(missing_ok=True)
    return {"host": with_host, "terminal_scenes": len(terminals)}


# ---------------------------------------------------------------- upload
def publish_at_for(slot: int):
    if not SHORTS_PUBLISH_IST_HOURS:
        return None
    hour = SHORTS_PUBLISH_IST_HOURS[slot % len(SHORTS_PUBLISH_IST_HOURS)]
    now = datetime.now(IST)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now + timedelta(minutes=20):
        return None  # slot already passed -> publish right away
    return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_short(service, video: Path, short: dict, synthetic: bool, slot: int) -> str:
    from googleapiclient.http import MediaFileUpload
    title = re.sub(r"\s+", " ", short["title"]).strip()[:95]
    hashtags = [h if h.startswith("#") else f"#{h}" for h in short.get("hashtags", [])][:5]
    if "#shorts" not in [h.lower() for h in hashtags]:
        hashtags.append("#shorts")
    desc = short.get("description", "").strip()
    lv = short.get("_long_video")
    if lv and lv.get("url"):
        desc += f"\n\nFull breakdown (long video): {lv['title']}\n{lv['url']}"
    desc += f"\n\nNew DevOps tip every day - subscribe: {core.CHANNEL_URL}\n\n" + " ".join(hashtags)
    if synthetic:
        desc += "\n\nTransparency: the presenter is an AI-generated avatar and the voice is AI text-to-speech."
    tags = core.sanitize_youtube_tags(list(short.get("tags", [])) + ["devops", "devops shorts", "devops tips"])
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "27",
                    "defaultLanguage": "en-US", "defaultAudioLanguage": "en-US"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(synthetic)},
    }
    pa = publish_at_for(slot)
    if pa:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = pa
        log(f"scheduled: public at {pa}")
    req = service.videos().insert(part="snippet,status", body=body,
                                  media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--count", type=int, default=SHORTS_PER_DAY)
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    core.OUTPUT_DIR.mkdir(exist_ok=True)   # shared helpers write temp files there
    entries = load_shorts_log()
    today = datetime.now(IST).date().isoformat()
    done_today = [e for e in entries if e.get("date") == today and not e.get("test_mode")]
    todo = max(0, args.count - (0 if args.test else len(done_today)))
    if todo == 0:
        log(f"{len(done_today)} real Short(s) already published for {today} - nothing to do.")
        return
    real_count = len([e for e in entries if not e.get("test_mode")])
    recent_titles = [e.get("title", "") for e in entries[-60:]]
    long_log = core.load_log()
    long_video = next((e for e in reversed(long_log) if e.get("url")), None)

    shorts = []
    for k in range(todo):
        idx = real_count + k
        fmt, area = pick_format_and_area(idx)
        try:
            s = gemini_short_script(fmt, area, recent_titles, long_video or {})
        except Exception as exc:
            log(f"slot {k + 1}: script failed ({exc}) - skipped (no generic template Shorts).")
            continue
        s.update({"_format": fmt, "_area": area, "_index": idx, "_slot": len(done_today) + k, "_long_video": long_video})
        recent_titles.append(s["title"])
        speed = core.KOKORO_SPEED
        for _ in range(3):
            durs, audio = synth_beats(s["beats"], OUT_DIR / f"short_{idx}", speed)
            total = sum(durs)
            if total <= SHORTS_MAX_SECONDS:
                break
            speed = round(min(1.3, speed + 0.08), 2)
            log(f"{s['title']}: {total:.1f}s > {SHORTS_MAX_SECONDS}s - re-voicing at speed {speed}")
        if sum(durs) > SHORTS_MAX_SECONDS and len(s["beats"]) > 3:
            s["beats"] = s["beats"][:-2] + s["beats"][-1:]
            durs, audio = synth_beats(s["beats"], OUT_DIR / f"short_{idx}", speed)
        s["_durs"], s["_audio"] = durs, audio
        log(f"slot {k + 1}: [{fmt} / {area}] {s['title']} - {sum(durs):.1f}s")
        shorts.append(s)
    if not shorts:
        log("No Shorts could be written today.")
        return

    # One Kaggle job for all of today's Shorts: concatenate their audio and
    # ask for one presenter segment per Short.
    host_clips = {}
    import host_lipsync
    ok, why = host_lipsync.kaggle_ready()
    if HOST_ENABLED and HOST_IMAGE.exists() and ok:
        combined = OUT_DIR / "all_shorts_audio.mp3"
        core._concat_clips([s["_audio"] for s in shorts], combined)
        segs, t = [], 0.0
        for n, s in enumerate(shorts):
            d = core._ffprobe_duration(s["_audio"])
            segs.append({"id": f"short_{n:02d}", "start": t, "end": t + d})
            t += d
        try:
            clips = host_lipsync.render_host_clips(combined, segs, HOST_IMAGE, OUT_DIR / "host_job", core.HOST_TIMEOUT_MIN)
            for c in clips:
                n = next(i for i, sg in enumerate(segs) if abs(sg["start"] - c["start"]) < 0.01)
                host_clips[n] = c["path"]
        except Exception as exc:
            log(f"AI presenter unavailable today - faceless Shorts instead: {str(exc)[:400]}")
    else:
        log(f"AI presenter off (enabled={HOST_ENABLED}, image={HOST_IMAGE.exists()}, kaggle={ok or why}) - faceless Shorts.")

    service = None if args.test else core.get_authenticated_service()
    for n, s in enumerate(shorts):
        out = OUT_DIR / f"short_{today}_{n + 1}.mp4"
        info = build_short_video(s, s["_durs"], s["_audio"], out, host_clips.get(n))
        srt = build_srt(s["beats"], s["_durs"], OUT_DIR / f"short_{today}_{n + 1}.srt")
        vid = "TEST_MODE_NO_UPLOAD"
        if not args.test:
            vid = upload_short(service, out, s, info["host"], s["_slot"])
            core.upload_captions(service, vid, srt)
            if SHORTS_PLAYLIST_ID:
                core.add_video_to_playlist(service, vid, SHORTS_PLAYLIST_ID)
            log(f"uploaded https://youtube.com/shorts/{vid}")
        entries.append({
            "date": today, "slot": s["_slot"], "index": s["_index"], "format": s["_format"], "area": s["_area"],
            "title": s["title"], "video_id": vid,
            "url": None if args.test else f"https://youtube.com/shorts/{vid}",
            "duration_sec": round(sum(s["_durs"]), 1), "host": info["host"],
            "terminal_scenes": info["terminal_scenes"], "content_source": s.get("_source"),
            "contains_synthetic_media": info["host"], "test_mode": args.test,
        })
        save_shorts_log(entries)
        log(f"Short {n + 1}: {out} ({sum(s['_durs']):.1f}s, presenter={info['host']})")


if __name__ == "__main__":
    main()
