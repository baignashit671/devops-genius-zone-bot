#!/usr/bin/env python3
"""
DevOps Genius Zone — YouTube Automation Bot v3.3.0
==================================================
Changed in v3.3.0 — "Production Incident File" format + AI presenter (all free):
- Script: every episode is one realistic production incident (cold open ->
  symptoms + wrong first move -> debug/root cause/fix -> prevention best
  practices + interview angle). Gemini embeds [[TERMINAL]] blocks with real
  commands/output; a second Gemini pass reviews technical accuracy. Real
  experiences from stories.yaml are the ONLY first-person stories allowed.
- Voice: Kokoro-82M via kokoro-onnx (offline, same male voice "am_michael"
  every video), edge_tts fallback. DevOps jargon pronunciation fixes.
- Visuals: animated terminal typing scenes; word-by-word highlighted
  captions burned into the video (the .srt upload stays).
- AI presenter: the same fictional face (assets/host.png) lip-synced with
  SadTalker on a free Kaggle GPU (host_lipsync.py), composited on the right
  side of the hook, chapter openers and outro. Rendered in parallel with
  the slides; any failure ships the video without it. When the presenter
  is used, the upload sets status.containsSyntheticMedia=true and the
  description says so (YouTube's altered/synthetic content disclosure).
- Thumbnail shows the presenter's face when the presenter is in the video.

Changed in v3.2.0 — retention + reliability (based on the channel's own
YouTube Analytics: average view duration is flat at ~1:40 no matter the
video length or voice, and ElevenLabs videos did NOT retain better than
edge_tts ones):
- TTS: edge_tts is now the DEFAULT voice (TTS_PROVIDER=edge_tts) and is
  generated PER SLIDE with retries, so one dropped Microsoft stream
  (NoAudioReceived, run #250) no longer kills the whole day's video, and
  edge_tts videos now get the same exact audio/slide sync ElevenLabs had.
  ElevenLabs is opt-in only (TTS_PROVIDER=elevenlabs).
- Length: script target cut from ~4,500 to ~2,000 words (~10-12 min),
  with a hard cap (SCRIPT_MAX_WORDS) that trims middle paragraphs if the
  model overshoots.
- First 30 seconds: no silent title card, no HOOK chapter card, no INTRO
  chapter, no "what you'll learn" agenda slide and no salary stat up
  front - narration starts on frame one over the title visual.
- Titles: no more generic template suffixes ("— A Step-by-Step
  Walkthrough for 2026" etc.); offline titles come from the topic itself.
- Gemini: tries a list of models (GEMINI_MODELS) before falling back to
  the offline script, so one overloaded model no longer means a generic
  video. upload_log now records which source actually wrote the script.

Added in v3.1.0 — frame-accurate audio/slide sync (ElevenLabs path):
- Previously (and still, on the edge_tts fallback path), slide timing
  was an approximation: a handful of structural slides (title, chapter
  dividers, CTA overlays, outro) got fixed screen time, and the
  remaining audio duration was split EVENLY across every other slide -
  a slide whose narration took 8 seconds to say and a slide whose
  narration took 20 seconds got roughly the same time on screen. Worse,
  because the single continuous audio track never paused for the fixed
  structural slides, the video could visibly drift out of sync with
  what was actually being said the further into the video you got.
- generate_synced_narration() replaces that with frame-accurate sync
  end to end. The script is parsed into an ordered list of slide
  segments FIRST (parse_script_to_segments() - the parsing logic that
  used to live inside build_video(), now the single shared source of
  truth for both TTS paths). On the ElevenLabs path
  (_generate_synced_narration_elevenlabs()), every spoken (hook/tip/
  body) slide is sent through ElevenLabs' character-timestamp API
  (convert_with_timestamps) so its on-screen duration is the EXACT time
  ElevenLabs took to say that exact slide's text - not an average.
  Structural slides (title/chapter/cta/outro) get real, generated
  SILENCE inserted into the audio track for their fixed duration, so
  the video never runs ahead of or behind the narration - the final
  audio.mp3 is literally built by concatenating one clip per slide, in
  slide order, so video and audio share the exact same timeline by
  construction. Segments are still batched into ElevenLabs API calls
  respecting ELEVENLABS_MAX_CHUNK_CHARS (with previous_text/next_text
  context across batches for natural pacing), but a batch is never
  split mid-slide, which is what makes mapping each slide back to its
  exact timestamp range possible.
- This is deliberately all-or-nothing: if anything in the exact-sync
  attempt fails (a chunk's timestamps come back malformed, a network
  error survives all retries, etc.), the whole attempt is abandoned and
  generate_synced_narration() falls back to the previous approximate
  method with a normal continuous edge_tts track - never a video that's
  exactly synced for part of its runtime and drifting for the rest.
- build_video() no longer parses the script or computes slide durations
  itself - it now takes the already-timed `slides` list straight from
  generate_synced_narration() and only handles rendering (pptx/PIL) +
  Ken Burns/crossfade + audio muxing, unchanged from v3.0.0.

Added in v3.0.0 — real PPTX slide deck + ElevenLabs "Adam" voiceover:
- Slides are no longer PNG frames rendered directly by Pillow. Every
  video's slide deck is now built as a real, human-editable .pptx file
  (build_slide_deck(), python-pptx) using the same (kind, text,
  duration, act_name) slide list that already drove timing, saved
  under devops_output/slides/day_NNN_<topic>.pptx and kept (not a temp
  file) so it can be opened and hand-tweaked in PowerPoint/Google
  Slides/LibreOffice Impress. That .pptx is then rasterized to PNG
  frames (render_pptx_to_frames()) via a LibreOffice headless
  pptx->pdf conversion followed by poppler's pdftoppm for pdf->PNG per
  page - the standard reliable headless pipeline, since LibreOffice's
  own --convert-to png only exports a single slide. Those frames feed
  the existing Ken Burns + crossfade motion pipeline completely
  unchanged. If python-pptx isn't installed, or the LibreOffice/poppler
  conversion fails for any reason, build_video() automatically falls
  back to the original Pillow-rendered PNG frames (_render_slide() and
  friends, kept intact) so a slide-pipeline problem never blocks a
  whole day's video - same fallback philosophy as Gemini -> offline
  script generation.
- Narration voiceover now uses the ElevenLabs API instead of edge_tts
  by default, targeting the male, US-accented "Adam" preset voice for
  this channel's USA audience (generate_audio(), which now returns
  (duration, engine_used) since it can fall back mid-run). The voice
  is resolved BY NAME against the account's live voice library at
  request time (_resolve_elevenlabs_voice_id()) rather than a
  hardcoded voice_id, since ElevenLabs has reshuffled its default
  voice library before; a hardcoded historical Adam id is only used as
  a last-resort fallback if the name lookup comes back empty, and
  ELEVENLABS_VOICE_ID can pin an exact voice_id (e.g. a custom clone)
  if you'd rather skip the lookup entirely. Long scripts are chunked
  by sentence (_chunk_text_for_tts()) well under every current model's
  per-request character cap, and each chunk is sent with the
  previous/next chunk's tail/head as ElevenLabs' previous_text /
  next_text context parameters so pacing and intonation stay
  consistent across chunk boundaries instead of each chunk sounding
  like a fresh cold start. Chunks are retried with backoff
  (ELEVENLABS_MAX_RETRIES) and stitched back into one audio.mp3 via an
  ffmpeg concat. If ELEVENLABS_API_KEY isn't set, the elevenlabs
  package isn't installed, or the ElevenLabs call fails after retries,
  generate_audio() automatically falls back to the original edge_tts
  voice so a missing/expired key never blocks a day's video either -
  it just quietly reverts to the old voice and logs why.
- upload_log.json now records which TTS engine and which slides engine
  actually rendered each day's video (tts_engine / slides_engine),
  since either can silently fall back - this makes that visible after
  the fact instead of only in the run's console log.
- New required env var for the primary voice path: ELEVENLABS_API_KEY
  (add as a GitHub Actions secret, same pattern as GEMINI_API_KEY).
  Optional overrides: ELEVENLABS_VOICE_NAME (default "Adam"),
  ELEVENLABS_VOICE_ID (skip name lookup entirely), ELEVENLABS_MODEL_ID
  (default "eleven_turbo_v2_5"), ELEVENLABS_OUTPUT_FORMAT, and
  ELEVENLABS_MAX_CHUNK_CHARS. New system deps for the primary slides
  path: LibreOffice (`soffice`) and poppler-utils (`pdftoppm`) must be
  installed on the runner - see the companion requirements.txt/workflow
  notes shipped alongside this file.

Added in v2.9.3:
- New `MANUAL_SEO_OVERRIDES` dict, keyed by day number. When the day
  being generated has an entry, `main()` swaps in that entry's exact
  title/description/tags after the normal script/content generation
  step (Gemini or offline fallback) runs — so the narration script is
  still generated normally for the day's topic, but the SEO metadata
  that actually reaches YouTube is the hand-tuned version instead of
  the auto-generated one. Overridden tags still flow through
  `sanitize_youtube_tags()` like any other tag list, so the 500-char
  real-cost budget from v2.9.2 is still enforced. Currently has one
  entry: Day 2 (the AI-replacing-junior-DevOps-engineers video),
  hand-optimized for a USA audience.
Fixed in v2.9.2 — the ACTUAL root cause of the recurring invalidTags
upload rejections (v2.9.1's fix was real but was not the cause of this):
- YouTube's tags property has a documented 500-character hard limit,
  but the character count is NOT simply the sum of each tag's string
  length. Per Google's own docs
  (https://developers.google.com/youtube/v3/docs/videos#snippet.tags):
  "If a tag contains a space, the API server handles the tag value as
  though it were wrapped in quotation marks, and the quotation marks
  count toward the character limit." So a tag with a space costs
  len(tag) + 2, not len(tag) — and almost every tag this bot generates
  is a multi-word phrase.
- Both `sanitize_youtube_tags()` and `upload_video()`'s pre-flight
  length check were summing plain `len(tag)`, silently undercounting
  the real YouTube-side total by ~2 characters per multi-word tag. A
  tag list that looked like "20 tags, 479 characters" (safely under our
  480 budget) was actually 511 real characters once YouTube's implicit
  quote-wrapping was counted — over the real 500-char limit, which is
  exactly why the upload kept failing with the same invalidTags error
  even after v2.9.1's duplicate-word fix was correctly deployed.
- New `_youtube_tag_char_cost()` implements YouTube's real formula and
  is now used everywhere a tag budget is calculated. Verified: worst
  case across 30 random tag orderings and a full 365-day sweep of every
  topic in TOPICS_365 tops out at exactly 480 real characters — never
  over the documented 500-char limit.
- Also added "<" and ">" to the stripped-punctuation set in
  sanitize_youtube_tags(), since YouTube's docs separately call out
  angle brackets as disallowed in individual tags.
Fixed in v2.9.1:
- YouTube upload was rejected with HttpError 400 reason: 'invalidTags'
  ("The request metadata specifies invalid video keywords."). Root
  cause: the offline fallback tag builder blindly appended suffix
  words ("explained", "2026", "mistakes", ...) onto `core` even when
  `core` already ended with that exact word, producing nonsensical
  duplicated-word tags — e.g. topic "Docker Networking Explained —
  ..." produced the tag "docker networking explained explained", and
  topic "How AI is Replacing Junior DevOps Engineers in 2026 — ..."
  produced "...engineers in 2026 2026". Both are real titles in the
  365-topic list, so this was going to recur on many future days.
  Fixed two ways:
    1. Root cause: new `_build_core_tag_variants()` skips a suffix
       variant whenever `core` already ends with that suffix's words
       (checked word-by-word, case-insensitively).
    2. Defensive net in `sanitize_youtube_tags()`: strips risky
       punctuation (`?!():;"`) from every tag (many topic titles carry
       it, and titles without an em-dash become `core` in full), and
       collapses any immediately-repeated word in a tag via regex —
       so even a future bug of this same shape can't reach the
       YouTube API.
  Verified with a full 365-day sweep of every topic in TOPICS_365:
  zero duplicate-word tags, zero risky-punctuation tags.
Expanded in v2.9.0:
- TOPICS_365 grew from 115 unique titles (cycled ~3x to fill the year,
  meaning every subscriber saw the exact same video again by day 116)
  to 365 fully unique titles — a real, non-repeating calendar year.
  New coverage: Azure, GCP, Ansible, the HashiCorp stack, service mesh
  and advanced networking, API gateways/load balancers/CDN, advanced
  Kubernetes (autoscaling, operators, multi-tenancy), FinOps/cost
  optimization, incident management, databases, message queues,
  serverless, supply chain security, Windows/PowerShell, multi-cloud,
  AI/MLOps infrastructure, load testing, progressive delivery,
  certifications, real-world postmortem case studies, head-to-head
  tool comparisons, disaster recovery, edge computing, and career/
  leadership skills.
- The 365-topic list is validated for uniqueness at load time; the old
  silent cycling logic is now a safety net that only activates (and
  warns loudly) if the list is ever trimmed below 365 entries.
Fixed in v2.7.3:
- Actually fixed the offline fallback `.strip()` list bug in both
  generator functions (`_generate_long_fallback` and
  `generate_fallback_content`) — v2.7.2 claimed this was resolved
  but the `[0]` index accessor after `topic.split("—")` was never
  added, so `.strip()` was still being called on a list and raising
  AttributeError.
- Actually added the missing `[2]` accessors on Pillow's
  `textbbox()` calls (six call sites: two in
  `_draw_act_structure_diagram`, three in `_render_slide` for the
  title/chapter/outro slide kinds, and one in `generate_thumbnail`).
  `textbbox()` returns a 4-tuple `(x0, y0, x1, y1)`, not a width, so
  arithmetic like `lw // 2` on the raw return value raised
  `TypeError: unsupported operand type(s) for //: 'tuple' and 'int'`.
  v2.7.2 also claimed this was fixed but it wasn't.

Upgraded in v2.8.0 — retention & growth pass:
- Both the Gemini prompt and the offline fallback generator now
  write to a hook → problem → solution → proof → payoff structure
  instead of a generic explainer: a cold-open pattern-interrupt
  hook, a clearly named problem the viewer actually has, a concrete
  step-by-step fix, real-world proof it works, and a single
  actionable takeaway — in a natural, spoken, first-person tone.
- Engagement asks (like / comment / subscribe) are now woven in at
  the moment value has just been delivered instead of dumped only
  at the end, and every video now teases tomorrow's specific topic
  by name to build a reason to come back and subscribe.
- Fallback titles now rotate through several proven high-CTR
  suffixes instead of one fixed template, so 365 days of videos
  don't all read identically in search and suggested feed.
- Video descriptions lead with the problem being solved (for
  search snippets and the suggested-feed preview) and spell out
  concrete "you'll walk away knowing how to..." outcomes.
- Slide detection keywords were broadened so problem/mistake
  paragraphs and solution/best-practice paragraphs reliably land on
  the right colored slide (red "problem" callouts, green "solution"
  callouts) instead of defaulting to plain body slides.
"""

import argparse
import asyncio
import base64
import json
import os
import platform
import re
import subprocess
import sys
import textwrap
import time

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Force stdout to flush immediately so GitHub Actions doesn't buffer logs
sys.stdout.reconfigure(line_buffering=True)

# ---------- Google / YouTube ----------
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import ResumableUploadError
from googleapiclient.http import MediaFileUpload

# ---------- TTS ----------
# edge_tts stays installed as the automatic offline-voice fallback if
# ElevenLabs is unreachable/misconfigured on a given day (see
# generate_synced_narration()) - the same "never let one day's video
# fail to render" philosophy already used for Gemini -> offline script
# generation.
import edge_tts

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs.core.api_error import ApiError as ElevenLabsApiError

    HAS_ELEVENLABS = True
except ImportError:
    HAS_ELEVENLABS = False
    ElevenLabsApiError = Exception
    print("[WARN] elevenlabs is not installed. Falling back to edge_tts.")
    print("       Fix: add 'elevenlabs' to requirements.txt and install it.")

# ---------- Image / Video ----------
from PIL import Image, ImageDraw, ImageFont

# ---------- Slides (PPTX) ----------
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn

    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False
    print("[WARN] python-pptx is not installed. Falling back to the static PIL slide renderer.")
    print("       Fix: add 'python-pptx' to requirements.txt and install it.")

# ---------- AI ----------
try:
    from google import genai

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("[WARN] google-genai is not installed. Using offline generator.")
    print("       Fix: add 'google-genai' to requirements.txt and install it.")


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
OUTPUT_DIR = Path("devops_output")
OUTPUT_DIR.mkdir(exist_ok=True)

UPLOAD_LOG = Path("upload_log.json")
TOKEN_FILE = Path("token.json")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    # NEW in v3.1.0, required for captions().insert() (auto-uploaded
    # English captions). IMPORTANT: this scope is only requested on a
    # FRESH OAuth consent - an existing GOOGLE_CREDENTIALS refresh token
    # minted before this line was added does NOT have it, and YouTube
    # will reject the captions upload with a 403 until you re-authorize
    # (regenerate token.json/GOOGLE_CREDENTIALS through the consent
    # screen again so the new scope is included). This does not block
    # the video upload itself - upload_captions() fails soft and just
    # logs a warning if the scope is missing.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

IST_TIMEZONE = ZoneInfo("Asia/Kolkata")

CHANNEL_NAME = "DevOps Genius Zone"
CHANNEL_BRAND = "@devopsgeniuszone"
CHANNEL_URL = "https://youtube.com/@devopsgeniuszone"

# Series/curriculum identity — bumped whenever TOPICS_365 is swapped out for
# a new content series. day_num (and the "Day X of 365" thumbnail/title
# badge) is computed only from upload_log.json entries tagged with the
# CURRENT series, so switching series always restarts cleanly at Day 1
# without touching or renumbering old log entries from a previous series.
SERIES_NAME = os.environ.get("SERIES_NAME", "ai-in-devops-2026").strip()

# Optional: every real (non-test) upload is auto-added to this playlist
# ID if set, in addition to whatever --playlist is passed manually. Set
# it to the current series' playlist so every video in the series lands
# in one binge-watchable playlist (helps session watch time). Create the
# playlist once in YouTube Studio and paste its ID (from the playlist's
# URL) here via the env var - there's no API for creating playlists tied
# to "the current series" automatically, only for adding videos to one
# that already exists.
SERIES_PLAYLIST_ID = os.environ.get("SERIES_PLAYLIST_ID", "").strip()

# Scheduled publish: the video is uploaded as PRIVATE and YouTube itself flips
# it to PUBLIC at this hour (IST, 0-23) - so the public go-live time no longer
# depends on when GitHub's scheduler happens to start the job (GitHub cron
# runs are routinely hours late). Set to "off" (or empty) to publish
# immediately on upload instead.
PUBLISH_AT_IST_HOUR_RAW = os.environ.get("PUBLISH_AT_IST_HOUR", "21").strip().lower()

# Gemini model
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
# Tried in order. A 503 "high demand" on one model is usually not a 503 on
# the next, so we move on quickly instead of hammering the same one.
GEMINI_MODELS = [
    m.strip() for m in os.environ.get(
        "GEMINI_MODELS",
        f"{GEMINI_MODEL},gemini-flash-lite-latest,gemini-3.8-flash,gemini-3.5-flash-lite,gemini-pro-latest",
    ).split(",") if m.strip()
]
GEMINI_MODELS = list(dict.fromkeys(GEMINI_MODELS))  # de-dupe, keep order
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "2"))  # per model
GEMINI_TIMEOUT_SEC = int(os.environ.get("GEMINI_TIMEOUT_SEC", "120"))

# YouTube upload limits (leave a safety margin for commas)
MAX_YOUTUBE_TAGS = 25
MAX_YOUTUBE_TAG_CHARS = 480

# ─────────────────────────────────────────
# ELEVENLABS TTS CONFIG
# ─────────────────────────────────────────
# We target the male, US-accented "Adam" preset voice for every video, to
# match the USA audience this channel is written for. ElevenLabs has
# reshuffled its default voice library before, so instead of hardcoding
# Adam's voice_id we resolve it by name against the account's voice
# library at runtime (see _resolve_elevenlabs_voice_id()) and only fall
# back to this historical ID if that lookup can't find a name match.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
# Optional SECOND (free-plan) account. Keys are tried in this order:
#   1) ELEVENLABS_API_KEY_FREE  (free credits first)
#   2) ELEVENLABS_API_KEY       (paid plan, only once the free one is empty/blocked)
# then edge_tts (free voice) if every key is out. Leave the FREE one unset to
# keep the old paid-only behaviour.
ELEVENLABS_API_KEY_FREE = os.environ.get("ELEVENLABS_API_KEY_FREE", "").strip()
ELEVENLABS_KEYS = []
for _label, _key in (("free", ELEVENLABS_API_KEY_FREE), ("paid", ELEVENLABS_API_KEY)):
    if _key and _key not in [k for _, k in ELEVENLABS_KEYS]:
        ELEVENLABS_KEYS.append((_label, _key))
ELEVENLABS_VOICE_NAME = os.environ.get("ELEVENLABS_VOICE_NAME", "Adam").strip()
# Optional hard override - set this secret if you'd rather pin an exact
# voice_id (e.g. a cloned/custom voice) instead of a name lookup.
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_FALLBACK_ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # historical premade "Adam" id
# eleven_flash_v2_5 is the actively-supported successor to eleven_turbo_v2_5
# (now deprecated by ElevenLabs) and shares the same discounted Flash/Turbo
# API credit tier - real usage data from this project's ElevenLabs account
# showed ~0.25 credits consumed per character on that tier (see
# SETUP_NOTES.md), a meaningfully better rate than 1:1. Override via env
# if you want eleven_multilingual_v2 (ElevenLabs docs call it more
# expressive for long-form, but it is NOT confirmed to share this same
# credit discount for API/subscription usage - verify against your own
# ElevenLabs usage dashboard before relying on it for budget math).
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5").strip()
ELEVENLABS_OUTPUT_FORMAT = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128").strip()
# Conservative per-request character chunk size - well under every
# current model's per-request cap (10k-40k depending on model), chosen
# so chunk boundaries land on natural act/paragraph breaks rather than
# raw character-count cuts, and so a single retried chunk is cheap.
ELEVENLABS_MAX_CHUNK_CHARS = int(os.environ.get("ELEVENLABS_MAX_CHUNK_CHARS", "2500"))
ELEVENLABS_MAX_RETRIES = 3

# Which voice engine to use. "edge_tts" (default, free) or "elevenlabs".
# ElevenLabs is only ever attempted when this is "elevenlabs" AND a key is
# set - having the secret configured is no longer enough on its own, so an
# empty/cancelled ElevenLabs plan can't silently waste a run's time.
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "kokoro").strip().lower() or "kokoro"
# v3.3.0: Kokoro-82M (Apache-2.0 weights) via kokoro-onnx (MIT) is the
# DEFAULT voice - fully offline on the runner's CPU, no endpoint to drop,
# and the same male voice every single video. Model files are fetched once
# from the kokoro-onnx GitHub release and cached by the workflow.
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_michael").strip() or "am_michael"
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0") or 1.0)
KOKORO_MODEL_DIR = Path(os.environ.get("KOKORO_MODEL_DIR", "models/kokoro"))
KOKORO_MODEL_URLS = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
KOKORO_SAMPLE_RATE = 24000
EDGE_TTS_VOICE = os.environ.get("EDGE_TTS_VOICE", "en-US-GuyNeural").strip()
EDGE_TTS_RATE = os.environ.get("EDGE_TTS_RATE", "+5%").strip()
# Run #253: one slide needed 6 tries on the GitHub runner, so give more
# headroom and fewer parallel requests (fewer simultaneous streams from
# one Azure IP = fewer NoAudioReceived drops).
EDGE_TTS_MAX_RETRIES = int(os.environ.get("EDGE_TTS_MAX_RETRIES", "8"))
EDGE_TTS_WORKERS = int(os.environ.get("EDGE_TTS_WORKERS", "2"))
EDGE_TTS_SAMPLE_RATE = 24000  # edge_tts default output: 24 kHz mono mp3

# Script length. Analytics showed viewers leave at ~100s regardless of
# length, so shorter videos keep a much higher % viewed.
SCRIPT_TARGET_WORDS = (1800, 2200)
SCRIPT_MAX_WORDS = int(os.environ.get("SCRIPT_MAX_WORDS", "2500"))
# Below this a Gemini script counts as "too short" (run #253: the lite
# model returned 1,252 words = 8 min) and the next model is tried; the
# longest short script is still preferred over the generic offline one.
SCRIPT_MIN_WORDS = int(os.environ.get("SCRIPT_MIN_WORDS", "1500"))

# ─────────────────────────────────────────
# PPTX SLIDE DECK CONFIG
# ─────────────────────────────────────────
# The real slide deck for each video is authored as an actual .pptx file
# (see build_slide_deck()) and then rasterized to PNG frames for the
# video pipeline (see render_pptx_to_frames()) - the .pptx is the source
# of truth, not a byproduct. Slide size matches the video's 1920x1080
# 16:9 canvas at PPTX_RENDER_DPI (13.333in x 7.5in @ 144 DPI = 1920x1080).
PPTX_SLIDE_WIDTH_IN = 13.333
PPTX_SLIDE_HEIGHT_IN = 7.5
PPTX_RENDER_DPI = 144
SLIDES_DIR = OUTPUT_DIR / "slides"

# ─────────────────────────────────────────
# MANUAL SEO OVERRIDES
# ─────────────────────────────────────────
# Keyed by day number (1-365). When the day being generated has an entry
# here, main() uses this exact title/description/tags instead of the
# auto-generated (Gemini or offline fallback) ones. The narration script
# itself is unaffected - it's still generated normally from TOPICS_365 for
# that day. Overridden tags still pass through sanitize_youtube_tags(), so
# the real (quote-wrapping-aware) 500-char budget is still enforced even
# if an entry below is edited carelessly.
MANUAL_SEO_OVERRIDES = {
    2: {
        "title": "How AI is Replacing Junior DevOps Engineers in 2026 (What Senior Engineers Know)",
        "description": (
            "AI tools are writing Terraform, debugging Kubernetes, and automating CI/CD "
            "pipelines - so what actually happens to junior DevOps engineers in 2026? In "
            "this video we break down exactly what AI is automating away, what senior "
            "DevOps engineers still do that AI can't touch yet, and how to future-proof "
            "your DevOps career.\n\n"
            "You'll learn:\n"
            "- Which junior DevOps tasks AI copilots already handle end-to-end\n"
            "- The skills senior engineers rely on that AI still can't replace (systems "
            "thinking, incident response, architecture tradeoffs)\n"
            "- A practical roadmap to move from junior to senior-level DevOps skills "
            "before the gap closes\n"
            "- Real examples from AWS, Kubernetes, Docker, Terraform, and CI/CD pipelines\n\n"
            "Whether you're a junior DevOps engineer worried about job security or a "
            "senior engineer scaling a team, this is a clear, no-hype look at where "
            "DevOps careers are headed.\n\n"
            "Subscribe for daily DevOps tutorials, career breakdowns, and hands-on "
            "AWS/Kubernetes/Terraform content.\n\n"
            f"Day 2 of 365 | {CHANNEL_NAME}\n{CHANNEL_URL}\n\n"
            "#DevOps #AIinDevOps #DevOpsCareer #CloudComputing #Kubernetes #AWS "
            "#Terraform #CICD #TechCareerUSA #DevOps2026"
        ),
        "tags": [
            "devops", "devops engineer", "cloud computing", "aws", "kubernetes",
            "docker", "cicd", "terraform", "github actions", "learn devops",
            "devops tutorial", "devops career", "tech career usa", "devops 2026",
            "ai in devops", "ai replacing developers", "junior devops engineer",
            "senior devops engineer", "devops jobs 2026", "future of devops",
            "ai automation devops", "devops interview questions",
            "cloud engineer career", "sre career", "platform engineering",
        ],
    },
}

# Brand palette
BRAND = {
    "bg":       (10, 14, 26),
    "surface":  (18, 24, 42),
    "accent":   (0,  190, 255),
    "accent2":  (255, 80,  80),
    "accent3":  (80, 255, 140),
    "text":     (235, 240, 255),
    "muted":    (130, 145, 180),
    "grid":     (22, 30, 52),
}

ACT_COLORS = {
    "HOOK":  (20, 110, 110),
    "INTRO": (52, 168, 92),
    "ACT 1": (222, 168, 24),
    "ACT 2": (222, 108, 24),
    "ACT 3": (204, 58, 58),
}
# v3.2.0: INTRO removed - the script goes HOOK -> ACT 1 directly.
ACT_ORDER = ["HOOK", "ACT 1", "ACT 2", "ACT 3"]
ACT_SUBLABELS = {
    "HOOK":  "Grab / Intrigue / Capture",
    "INTRO": "World / Hero / Context",
    "ACT 1": "Introduce / Establish / Disrupt",
    "ACT 2": "Challenge / Break / Transform",
    "ACT 3": "Climax / Closure / Change",
}

# Motion settings
ENABLE_MOTION      = True
CROSSFADE_SEC      = 0.4
KEN_BURNS_MAX_ZOOM = 1.08
RENDER_FPS         = 24

COMPANY_EXAMPLES = [
    "a major streaming service",
    "a large e-commerce company",
    "a fintech startup",
    "a healthcare SaaS platform",
    "a logistics company",
    "a social media company",
    "an enterprise software vendor",
    "a gaming company",
    "a travel booking platform",
    "a cybersecurity firm",
]

# ─────────────────────────────────────────
#  365 VIRAL SEO TOPICS (2026 US MARKET)
# ─────────────────────────────────────────
TOPICS_365 = [
    # AI in DevOps (Viral / High Growth)
    "How AI is Replacing Junior DevOps Engineers in 2026 — What to Do",
    "GitHub Copilot for DevOps — 10 Prompts to Automate Your Job",
    "Claude Code vs GitHub Copilot — Which is Better for Infrastructure?",
    "AIOps Explained — How to Let AI Auto-Resolve Production Incidents",
    "Writing Terraform with AI — Stop Doing It Manually in 2026",
    "How I Use ChatGPT to Debug Kubernetes Errors in Seconds",
    "The Future of DevOps in 2026 — Platform Engineering & AI",
    "AI Code Review in CI/CD — Catching Security Flaws Automatically",
    "Using AI to Write Perfect Kubernetes YAML Files",
    "Is DevOps Dead in 2026? The Rise of AI Platform Engineers",

    # Kubernetes (Core & Advanced)
    "Kubernetes Explained in 10 Minutes — From Zero to Confident",
    "Stop Using kubectl manually — The GitOps Way to Manage K8s",
    "Kubernetes Architecture Explained Simply — Nodes, Pods & Control Plane",
    "Kubernetes Ingress vs Gateway API — Stop Using Ingress in 2026",
    "Kubernetes Cost Optimization — Cut Your Cloud Bill by 60 Percent",
    "K3s vs K8s — Why Everyone is Moving to Lightweight Kubernetes",
    "Kubernetes StatefulSets — Why Databases in K8s are Finally Safe",
    "How to Upgrade a Production Kubernetes Cluster with Zero Downtime",
    "Kubernetes RBAC Explained — Security Without Breaking Things",
    "Kubernetes Resource Limits — Stop OOMKilled Pods Forever",
    "Top 15 kubectl Commands Every Senior Engineer Uses",
    "Kubernetes Multi-Cluster Strategy — How Enterprise Teams Scale",
    "Helm vs Kustomize — Which K8s Package Manager Wins in 2026?",
    "Crossplane Explained — Why Kubernetes is Replacing Terraform",
    "Kubernetes Pod Disruption Budgets — Stop Breaking Production",

    # CI/CD & GitOps
    "GitHub Actions vs Jenkins — Why Jenkins is Finally Dying in 2026",
    "ArgoCD Tutorial — The Ultimate GitOps Kubernetes Pipeline",
    "Flux vs ArgoCD — Which GitOps Tool Should You Choose?",
    "How to Build a Zero-Downtime CI/CD Pipeline from Scratch",
    "GitHub Actions Matrix Builds — Test 10x Faster",
    "Blue-Green vs Canary Deployments — Which is Safer?",
    "Stop Storing Secrets in GitHub — Do This Instead",
    "How to Deploy to AWS EKS using GitHub Actions & ArgoCD",
    "Progressive Delivery with Argo Rollouts — Safe Production Releases",
    "GitLab CI/CD Masterclass — Complete Pipeline Tutorial",

    # Terraform & IaC
    "Terraform Tutorial 2026 — Infrastructure as Code in 30 Minutes",
    "Terraform vs OpenTofu — Which Should You Learn?",
    "Terraform State Management — Remote Backends & Locking Explained",
    "How to Write Reusable Terraform Modules like a Senior Engineer",
    "Terraform import — How to Take Control of Manually Created AWS Resources",
    "Pulumi vs Terraform — Is Python better than HCL?",
    "CDK for Terraform — Write AWS Infrastructure in TypeScript",
    "Terratest Explained — Stop Guessing and Test Your IaC",
    "Terraform Drift Detection — Catch Manual AWS Changes Instantly",
    "How to Structure a Terraform Repository for a 50-Person Team",

    # AWS & Cloud
    "AWS Explained for DevOps — The Only 7 Services You Need",
    "How to Setup a Secure AWS VPC from Scratch",
    "AWS IAM Best Practices — Stop Giving AdministratorAccess",
    "AWS Fargate vs EC2 — Which is Actually Cheaper?",
    "AWS S3 Lifecycle Policies — Stop Wasting Money on Storage",
    "How to Deploy Docker Containers to AWS ECS Step by Step",
    "AWS Lambda Serverless Tutorial — Build an API in 10 Minutes",
    "AWS RDS vs DynamoDB — Choose the Right Database",
    "AWS CodePipeline — CI/CD using 100% Native AWS Tools",
    "How to Pass the AWS DevOps Professional Exam in 2026",

    # Docker & Containers
    "Docker Explained in 10 Minutes — The Ultimate Beginner Guide",
    "How to Write a Perfect Dockerfile in 2026",
    "Docker Multi-Stage Builds — Reduce Image Size by 90 Percent",
    "Docker Compose Tutorial — Local Development Made Easy",
    "Docker Volumes vs Bind Mounts — Stop Losing Your Data",
    "Docker Networking Explained — Bridge, Host, and Overlay",
    "How to Run Docker Containers as Non-Root — Security 101",
    "Stop Using Docker Desktop — The Best Free Alternatives in 2026",
    "Docker Layer Caching — Make Your CI/CD Pipelines 10x Faster",
    "How to Scan Docker Images for Security Vulnerabilities (Trivy)",

    # DevSecOps & Security
    "DevSecOps Explained — How to Shift Left in 2026",
    "HashiCorp Vault Tutorial — Secrets Management for DevOps",
    "Kubernetes Secrets are NOT Secret — How to Fix It",
    "SBOMs Explained — Why Software Supply Chain Security is Mandatory",
    "Sigstore & Cosign — How to Sign Your Docker Images",
    "Zero Trust Security for DevOps — How to Implement It",
    "OPA (Open Policy Agent) — Policy as Code for Kubernetes",
    "Kyverno vs OPA Gatekeeper — Enforcing K8s Security Policies",
    "How to Rotate Database Credentials Automatically with Vault",
    "Container Escape Attacks — How Hackers Break Out of Docker",

    # Platform Engineering & SRE
    "Platform Engineering Explained — Why DevOps is Evolving",
    "How to Build an Internal Developer Platform (IDP)",
    "Backstage by Spotify — Create Your Own Developer Portal",
    "SRE vs DevOps — What is the Actual Difference?",
    "SLIs, SLAs, and SLOs Explained for DevOps Engineers",
    "How to Build a DevOps On-Call Rotation That Doesn’t Suck",
    "Chaos Engineering — Breaking Production on Purpose",
    "Incident Management — How to Handle a Sev1 Outage Calmly",
    "DORA Metrics Explained — Measure Your DevOps Success",
    "Team Topologies — How to Structure Engineering Teams",

    # Observability & Monitoring
    "Prometheus & Grafana Tutorial — Monitor Everything in 15 Mins",
    "OpenTelemetry Explained — The Future of Observability in 2026",
    "The 4 Golden Signals of Monitoring Every Engineer Must Know",
    "Prometheus Alertmanager — Stop Alert Fatigue Instantly",
    "Loki vs ELK Stack — Which Log Aggregator is Better?",
    "Jaeger & Distributed Tracing — Find the Slow Microservice",
    "eBPF Explained — Why It's Changing Cloud Native Observability",
    "Cilium vs Calico — eBPF Networking for Kubernetes",
    "Datadog vs New Relic — Which Monitoring Tool Wins?",
    "How to Monitor AWS Lambda Serverless Functions Effectively",

    # Linux & Networking
    "Top 20 Linux Commands Every DevOps Engineer Must Memorize",
    "Bash Scripting Tutorial — Automate Your Job in 20 Minutes",
    "Linux File Permissions Explained — Stop Using chmod 777",
    "How DNS Actually Works — A Deep Dive for DevOps",
    "Systemd Explained — How to Manage Linux Services",
    "SSH Best Practices — Lock Down Your Linux Servers",
    "Nginx vs HAProxy vs Traefik — Which Load Balancer is Best?",
    "awk and sed Tutorial — Parsing Logs Like a Pro",
    "Linux Troubleshooting — htop, strace, and tcpdump",
    "Shell Scripting Mistakes That Break Production",

    # Career, Salary & Interviews (High CTR)
    "Top 50 DevOps Interview Questions & Answers for 2026",
    "DevOps Engineer Salary 2026 — USA vs UK vs India",
    "How to Become a DevOps Engineer in 6 Months (Zero Experience)",
    "The Ultimate DevOps Resume That Gets FAANG Interviews",
    "Top 5 DevOps Projects for Your Portfolio in 2026",
    "How to Answer System Design Questions in DevOps Interviews",
    "Is DevOps Saturated? The Honest Truth for 2026",
    "Freelance DevOps — How to Make $150/hr Remotely",
    "Staff DevOps Engineer — How to Get Promoted Faster",
    "The Worst DevOps Mistakes I Made in My First Year",

    # Azure DevOps & Cloud
    "Azure DevOps Explained — The Complete Beginner's Guide for 2026",
    "Azure vs AWS — Which Cloud Should You Actually Learn in 2026?",
    "Azure Kubernetes Service (AKS) — Full Setup and Best Practices",
    "Azure Pipelines vs GitHub Actions — Which CI/CD Tool Wins?",
    "Azure DevOps Boards — Agile Project Management for Engineering Teams",
    "Azure Resource Manager (ARM) Templates vs Bicep — Which Should You Use?",
    "Azure Active Directory (Entra ID) — Identity and Access for DevOps Engineers",
    "Azure Functions — Serverless DevOps for the Microsoft Cloud",
    "Azure Monitor & Application Insights — Full Observability Setup",
    "Azure Policy — Governance and Compliance as Code",
    "How to Migrate a Legacy App to Azure — A Real Migration Walkthrough",
    "Azure Cost Management — Cut Your Azure Bill Without Cutting Performance",

    # GCP & Google Cloud
    "Google Cloud for DevOps Engineers — The Only Services You Actually Need",
    "GKE Autopilot vs Standard — Which Kubernetes Mode Should You Pick?",
    "Google Cloud Build — CI/CD Pipelines the GCP Way",
    "Cloud Run Explained — Serverless Containers Without the Kubernetes Overhead",
    "Google Cloud IAM — Least Privilege Done Right",
    "Terraform on GCP — Provisioning Infrastructure the Right Way",
    "GCP vs AWS vs Azure — An Honest 2026 Comparison for Job Seekers",
    "Google Cloud Load Balancing — Global Traffic Management Explained",
    "BigQuery for DevOps Engineers — Log Analytics at Scale",
    "Google Cloud Armor — DDoS and WAF Protection Explained",
    "Anthos & Multi-Cloud Kubernetes — Is It Worth Learning in 2026?",
    "GCP Cost Optimization — Committed Use Discounts and Rightsizing",

    # Ansible & Configuration Management
    "Ansible Explained — Configuration Management for Absolute Beginners",
    "Ansible vs Terraform — When to Use Which Tool (And Why Not Both)",
    "Ansible Playbooks — Write Your First Automation in 15 Minutes",
    "Ansible Vault — Securing Secrets in Your Automation",
    "Ansible Roles — Structuring Automation for Large Teams",
    "Ansible AWX / Tower — Running Ansible at Enterprise Scale",
    "Ansible Idempotency Explained — Why Your Playbooks Keep Breaking",
    "Chef vs Puppet vs Ansible — Which Config Management Tool Survives 2026?",
    "Ansible for Network Automation — Beyond Servers",
    "Common Ansible Mistakes That Break Production Deployments",

    # HashiCorp Stack
    "HashiCorp Consul — Service Discovery Explained Simply",
    "HashiCorp Nomad — The Kubernetes Alternative Nobody Talks About",
    "Packer Explained — Build Golden Images Like a Senior Engineer",
    "Vault Dynamic Secrets — Stop Using Static Credentials Forever",
    "Vault vs AWS Secrets Manager — Which Secrets Tool Should You Learn?",
    "Terraform Cloud vs Terraform Enterprise — What Actually Changes",
    "HashiCorp Boundary — Zero Trust Remote Access Explained",
    "Consul Service Mesh — Connecting Microservices Securely",
    "Vault Auto-Unseal — Stop Manually Unsealing Vault After Every Restart",
    "Why HashiCorp's License Change Still Matters for Your Toolchain in 2026",

    # Service Mesh & Advanced Networking
    "Istio Explained — Service Mesh for Real Production Systems",
    "Istio vs Linkerd vs Cilium — Which Service Mesh Should You Learn?",
    "Envoy Proxy Explained — The Engine Behind Every Modern Service Mesh",
    "mTLS Explained — Encrypting Service-to-Service Traffic Automatically",
    "Sidecar Pattern Explained — Why Every Pod Has Two Containers Now",
    "Kubernetes Network Policies — Locking Down Pod-to-Pod Traffic",
    "DNS for DevOps Engineers — What Actually Happens When a Pod Resolves a Name",
    "Service Mesh Observability — Tracing Requests Across 50 Microservices",
    "Zero Trust Networking — What It Actually Means for Your Infrastructure",
    "eBPF Networking Deep Dive — How Cilium Replaced iptables",

    # API Gateways, Load Balancers & CDN
    "Kong API Gateway Explained — Rate Limiting, Auth, and Routing",
    "NGINX Explained — From Reverse Proxy to Load Balancer to Ingress",
    "AWS Application Load Balancer vs Network Load Balancer — Which One?",
    "API Rate Limiting Explained — Protecting Your Backend from Abuse",
    "Cloudflare for DevOps Engineers — CDN, WAF, and DNS in One Place",
    "API Gateway vs Service Mesh — Do You Need Both?",
    "Building a Zero-Downtime API Gateway Migration",
    "GraphQL vs REST for DevOps — Deployment and Monitoring Differences",
    "Web Application Firewalls Explained — Stopping Attacks Before They Hit Your App",
    "CDN Caching Strategies That Actually Cut Your Origin Load",

    # Kubernetes Advanced
    "Kubernetes Horizontal Pod Autoscaler — Full Setup and Tuning Guide",
    "Kubernetes Vertical Pod Autoscaler — When HPA Isn't Enough",
    "Karpenter Explained — Smarter Node Autoscaling Than Cluster Autoscaler",
    "Kubernetes Operators Explained — Automating Day-2 Operations",
    "Kubernetes Custom Resource Definitions (CRDs) — Build Your Own API",
    "Kubernetes Admission Controllers — Enforcing Policy at the API Server",
    "Multi-Tenant Kubernetes — Isolating Teams on One Cluster",
    "Kubernetes Node Pools & Taints — Controlling Where Your Pods Actually Run",
    "Kubernetes GPU Scheduling — Running AI Workloads on K8s",
    "Kubernetes Backup & Disaster Recovery with Velero",
    "Kubernetes Namespace Design — How Enterprise Teams Structure Clusters",
    "Kubernetes Service Accounts — The Identity Layer Nobody Configures Correctly",
    "Kubernetes Liveness vs Readiness vs Startup Probes — Get This Wrong and Pods Die",
    "Kubernetes etcd Explained — The Database Your Whole Cluster Depends On",

    # Cost Optimization & FinOps
    "FinOps Explained — The Discipline Every DevOps Team Needs in 2026",
    "AWS Spot Instances — Cut Compute Costs by 70 Percent Without the Risk",
    "Reserved Instances vs Savings Plans — Which Saves You More",
    "Kubernetes Cost Allocation — Know Exactly What Each Team Is Spending",
    "Rightsizing Cloud Resources — Stop Paying for Servers You Don't Need",
    "Cloud Cost Anomaly Detection — Catch a Billing Spike Before Finance Does",
    "How to Read an AWS Bill Without Losing Your Mind",
    "Autoscaling to Zero — The Cost Optimization Most Teams Skip",
    "Multi-Cloud Cost Comparison — AWS vs Azure vs GCP Pricing for 2026",
    "Storage Cost Optimization — S3 Lifecycle Rules That Actually Save Money",
    "The Real Cost of Over-Provisioning Kubernetes Requests and Limits",
    "Building a Cloud Cost Dashboard Your Whole Team Will Actually Use",
    "Data Transfer Costs Explained — The Hidden Cloud Bill Nobody Warns You About",
    "Showback vs Chargeback — How Enterprise Teams Make Engineers Cost-Aware",

    # Incident Management & On-Call
    "How to Write a Blameless Postmortem That Actually Prevents Repeat Incidents",
    "Building an On-Call Rotation That Doesn't Burn Out Your Team",
    "PagerDuty vs Opsgenie — Which Incident Tool Should You Choose?",
    "Incident Severity Levels Explained — Sev1 vs Sev2 vs Sev3",
    "How to Run an Incident Commander Role During a Live Outage",
    "Runbooks That Actually Work — Writing Docs Engineers Will Follow at 3 AM",
    "Alert Fatigue Explained — Why Your Team Ignores Half Your Alerts",
    "Building a Status Page That Builds Customer Trust During Outages",
    "War Room vs Async Incident Response — Which Works Better Remote?",
    "The First 5 Minutes of a Production Outage — What to Actually Do",

    # Databases & Data Ops for DevOps Engineers
    "Database Migrations in CI/CD — How to Ship Schema Changes Safely",
    "PostgreSQL for DevOps Engineers — What You Actually Need to Know",
    "Database Backup Strategies — RPO, RTO, and What They Really Mean",
    "Zero-Downtime Database Migrations — A Real Walkthrough",
    "Read Replicas Explained — Scaling Reads Without Scaling Pain",
    "Database Connection Pooling — Why Your App Keeps Running Out of Connections",
    "Redis Explained — Caching, Queues, and Sessions in One Tool",
    "Managing Kubernetes StatefulSets for Databases in Production",
    "Database Sharding Explained — When and How to Split Your Data",
    "Blue-Green Database Deployments — Is It Even Possible?",
    "Automating Database Backups to S3 — A Step-by-Step Setup",
    "Database Monitoring — The Metrics That Actually Predict an Outage",
    "Managed Databases vs Self-Hosted — What Actually Changes for DevOps",
    "Data Retention Policies — Deleting Data Without Breaking Compliance",

    # Message Queues & Event-Driven Systems
    "Apache Kafka Explained — Event Streaming for DevOps Engineers",
    "Kafka vs RabbitMQ vs SQS — Which Message Queue Should You Use?",
    "Event-Driven Architecture Explained — Decoupling Services That Actually Scale",
    "Dead Letter Queues Explained — Where Your Failed Messages Actually Go",
    "Kafka Consumer Lag — The Metric That Predicts Outages Before They Happen",
    "Building a Resilient Message Queue Pipeline in Production",
    "Idempotent Consumers Explained — Stop Processing the Same Event Twice",
    "Monitoring Kafka in Production — What Actually Matters",

    # Serverless & Event-Driven Compute
    "Serverless Explained — When It Saves Money and When It Doesn't",
    "AWS Lambda Cold Starts — Why They Happen and How to Fix Them",
    "Serverless vs Containers — Choosing the Right Compute Model in 2026",
    "Building a Serverless CI/CD Pipeline from Scratch",
    "AWS Step Functions — Orchestrating Serverless Workflows Visually",
    "Serverless Observability — Debugging Functions You Can't SSH Into",
    "Event-Driven Serverless Architecture on AWS — A Real-World Pattern",
    "Serverless Security — The Mistakes That Leave Functions Exposed",
    "When Serverless Becomes More Expensive Than Containers",
    "Building a Serverless API Backend in Under an Hour",

    # Supply Chain Security & Compliance
    "Software Supply Chain Attacks — How They Actually Happen",
    "SLSA Framework Explained — Securing Your Build Pipeline",
    "Signing and Verifying Container Images — A Practical Walkthrough",
    "CIS Benchmarks Explained — Hardening Your Infrastructure the Right Way",
    "Distroless Container Images — Cutting Your Attack Surface in Half",
    "Dependency Scanning in CI/CD — Catching Vulnerable Packages Before Production",
    "SOC 2 Compliance for DevOps Teams — What You'll Actually Be Audited On",
    "Secrets Scanning — Stopping Credentials from Ever Reaching GitHub",
    "Private Package Registries — Why Public npm and PyPI Aren't Enough",
    "Building a Compliant CI/CD Pipeline Without Slowing Your Team Down",

    # Windows & PowerShell DevOps
    "PowerShell for DevOps Engineers — What Linux Users Are Missing",
    "Windows Containers Explained — Are They Worth Using in 2026?",
    "Automating Windows Server with DSC (Desired State Configuration)",
    "PowerShell vs Bash — Which Should You Actually Learn First?",
    "Managing Active Directory with PowerShell Automation",
    "Running .NET Applications in Docker — A Practical Guide",
    "Windows Server Patch Management Automation",
    "Hybrid Windows and Linux Infrastructure — Managing Both Without Losing Your Mind",

    # Multi-Cloud & Hybrid Cloud
    "Multi-Cloud Explained — Is It Actually Worth the Complexity?",
    "Hybrid Cloud Architecture — Connecting On-Prem to the Cloud Securely",
    "Multi-Cloud Kubernetes — Running the Same Cluster Config Everywhere",
    "Cloud Repatriation — Why Some Companies Are Leaving the Cloud in 2026",
    "Building a Disaster Recovery Site Across Two Cloud Providers",
    "Multi-Cloud Networking — VPNs, Peering, and Transit Gateways Explained",
    "Vendor Lock-In Explained — How to Architect Around It From Day One",
    "On-Prem to Cloud Migration — A Real 90-Day Migration Plan",

    # AI/ML Infra & MLOps for DevOps Engineers
    "MLOps Explained — DevOps Principles Applied to Machine Learning",
    "Deploying LLMs in Production — Infrastructure DevOps Engineers Need to Know",
    "GPU Infrastructure for AI Workloads — What Changes From Regular Compute",
    "Kubeflow Explained — Running ML Pipelines on Kubernetes",
    "Vector Databases Explained — Infrastructure for the AI Era",
    "Building a CI/CD Pipeline for Machine Learning Models",
    "Model Serving at Scale — Infrastructure Patterns for Real-Time Inference",
    "LLMOps Explained — The New Job Title DevOps Engineers Should Watch",
    "Feature Stores Explained — The Missing Piece in ML Infrastructure",
    "Monitoring AI Models in Production — Drift Detection for DevOps Engineers",
    "RAG Pipelines Explained — Infrastructure Behind AI Chatbots",
    "Autoscaling GPU Workloads in Kubernetes",
    "Cost Optimization for AI Infrastructure — GPUs Are Expensive, Here's How to Save",
    "Why Every DevOps Engineer Needs to Understand AI Infrastructure in 2026",

    # Load & Performance Testing
    "Load Testing Explained — Finding Your Breaking Point Before Customers Do",
    "K6 vs JMeter vs Locust — Which Load Testing Tool Should You Use?",
    "Building a Performance Testing Pipeline in CI/CD",
    "Chaos Engineering vs Load Testing — What's the Actual Difference?",
    "How to Read a Load Test Report Like a Senior Engineer",
    "Simulating Real Production Traffic in a Staging Environment",
    "Performance Budgets Explained — Setting Limits Before Things Get Slow",
    "Capacity Planning — Predicting When You'll Need to Scale",

    # Feature Flags, Canary & Progressive Delivery
    "Feature Flags Explained — Ship Code Without Shipping Risk",
    "LaunchDarkly vs Open Source Feature Flags — Which Should You Use?",
    "Canary Deployments Explained — Rolling Out to 5 Percent of Traffic First",
    "Progressive Delivery Explained — The Evolution Beyond CI/CD",
    "A/B Testing Infrastructure — What DevOps Engineers Actually Build",
    "Dark Launches Explained — Testing in Production Safely",
    "Automated Rollback Triggers — Letting Metrics Decide When to Roll Back",
    "Feature Flag Debt — The Hidden Cost Nobody Talks About",

    # Certifications & Learning Paths
    "The Only DevOps Certifications Worth Getting in 2026",
    "CKA vs CKAD — Which Kubernetes Certification Should You Get First?",
    "AWS Certified DevOps Engineer — Is It Actually Worth It in 2026?",
    "HashiCorp Terraform Associate — Full Study Guide and Exam Tips",
    "How I'd Learn DevOps From Scratch in 2026 (If I Started Today)",
    "Self-Taught vs Bootcamp vs Degree — What Actually Gets You Hired",
    "The DevOps Learning Roadmap Nobody Gives You for Free",
    "Building a Home Lab for DevOps Practice — What You Actually Need",
    "Free Resources to Learn DevOps in 2026 — No Paid Course Required",
    "How Long It Actually Takes to Become Job-Ready in DevOps",

    # Real-World Case Studies & Postmortems
    "Breaking Down a Real Production Outage — Lessons From a Postmortem",
    "How a Single Config Change Took Down Production for 4 Hours",
    "The Kubernetes Misconfiguration That Cost a Company $100K in a Weekend",
    "Anatomy of a Database Migration Gone Wrong — And How It Was Fixed",
    "How a Secrets Leak on GitHub Led to a Full Security Incident",
    "The Autoscaling Bug That Caused a Cascading Failure",
    "A Real Disaster Recovery Test — What Actually Broke",
    "How One Team Cut Deployment Time From 2 Hours to 8 Minutes",
    "The Monitoring Gap That Let an Outage Run for 6 Hours Undetected",
    "Lessons From Migrating a Legacy Monolith to Microservices",

    # Tool Comparisons ("X vs Y")
    "Jenkins vs GitHub Actions vs GitLab CI — The 2026 Verdict",
    "Terraform vs Ansible vs Pulumi — Picking the Right Tool for the Job",
    "Prometheus vs Datadog — Open Source vs Paid Monitoring",
    "Docker vs Podman — Is Docker Still the Default in 2026?",
    "Grafana vs Kibana — Which Dashboard Tool Should You Learn?",
    "ArgoCD vs Jenkins X — GitOps Tools Compared",
    "AWS ECS vs EKS — Which Container Platform Should You Choose?",
    "New Relic vs Datadog vs Grafana Cloud — Observability Platforms Compared",
    "Terraform vs CloudFormation vs CDK — Native vs Third-Party IaC",
    "Nginx vs Apache — Which Web Server Should You Actually Use in 2026?",
    "GitHub vs GitLab vs Bitbucket — Which Platform for Your Team?",
    "Docker Compose vs Kubernetes — When You Don't Need K8s Yet",
    "Vim vs VS Code for DevOps — Which Editor Actually Makes You Faster?",
    "Linux vs macOS for DevOps Engineers — Does It Actually Matter?",

    # Disaster Recovery & Backup
    "Disaster Recovery Explained — RPO, RTO, and Building a Real DR Plan",
    "Backup Strategies Every DevOps Engineer Should Have in Place",
    "Testing Your Disaster Recovery Plan — Why Most Companies Never Do It",
    "Multi-Region Failover — Architecture Patterns That Actually Work",
    "Ransomware Recovery — What DevOps Teams Need to Prepare For",
    "Immutable Backups Explained — Protecting Data From Deletion and Attack",
    "Building a Runbook for a Full Region Outage",
    "Point-in-Time Recovery Explained — Restoring to the Exact Right Second",

    # Edge Computing & CDN
    "Edge Computing Explained — Why Compute Is Moving Closer to Users",
    "Cloudflare Workers vs AWS Lambda@Edge — Edge Functions Compared",
    "Building a Global Low-Latency Application with Edge Infrastructure",
    "CDN Explained From First Principles — What Actually Happens on a Cache Hit",
    "Edge Security — Protecting Applications at the Network Edge",
    "When Edge Computing Actually Makes Sense (And When It's Overkill)",

    # Career, Soft Skills & Leadership Part 2
    "How to Write a Postmortem That Makes You Look Like a Senior Engineer",
    "Technical Writing for DevOps — Docs That People Actually Read",
    "How to Give a Technical Presentation Without Losing the Room",
    "Negotiating a DevOps Job Offer — What You Can Actually Ask For",
    "Remote DevOps Jobs in 2026 — What Companies Are Actually Hiring For",
    "How to Mentor a Junior DevOps Engineer the Right Way",
    "Imposter Syndrome in DevOps — Why Even Senior Engineers Feel It",
    "How to Push Back on an Unrealistic Deadline as an Engineer",
    "Building Influence as an Engineer Without Becoming a Manager",
    "How to Explain a Technical Outage to Non-Technical Executives",
    "Switching From Sysadmin to DevOps — A Realistic Career Path",
    "Switching From Developer to DevOps Engineer — What Actually Changes",
]

# TOPICS_365 above is 365 unique, hand-picked titles — one full calendar
# year with no repeats, spanning core DevOps tooling, cloud platforms
# (AWS/Azure/GCP), Kubernetes depth, security/compliance, cost/FinOps,
# databases, AI/MLOps infra, incident response, and career growth. A
# subscriber who watches every day for a year never sees the same title
# twice, which is the whole point of a 365-day series.
#
# This safety net only activates if the curated list above is ever
# trimmed below 365 entries (e.g. during editing) — it cycles the
# existing topics to keep the bot from crashing on a short list, rather
# than silently running past the end of TOPICS_365. It is a no-op today.
if len(TOPICS_365) < 365:
    print(
        f"[WARN] TOPICS_365 has only {len(TOPICS_365)} unique entries; "
        f"padding to 365 by repeating topics. Add more unique topics to "
        f"avoid duplicate videos within a single year."
    )
    _temp_list = TOPICS_365.copy()
    while len(_temp_list) < 365:
        _temp_list.extend(TOPICS_365)
    TOPICS_365 = _temp_list[:365]
elif len(TOPICS_365) > 365:
    TOPICS_365 = TOPICS_365[:365]


# ─────────────────────────────────────────
# SEO CONSTANTS
# ─────────────────────────────────────────
FALLBACK_TAGS = [
    "devops",
    "devops engineer",
    "cloud computing",
    "aws",
    "kubernetes",
    "docker",
    "cicd",
    "terraform",
    "github actions",
    "learn devops",
    "devops tutorial",
    "devops career",
    "tech career usa",
    "devops 2026"
]

HASHTAGS = (
    "#DevOps #Kubernetes #Docker #AWS #Terraform #CICD #GitHubActions "
    "#CloudNative #DevOpsEngineer #LearnDevOps #PlatformEngineering "
    "#TechCareers #DevOps2026"
)


# ─────────────────────────────────────────
# FONT HELPER
# ─────────────────────────────────────────
def _get_font(size=36, bold=False):
    paths = []
    if platform.system() == "Windows":
        paths = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]
    elif platform.system() == "Darwin":
        paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    else:
        bold_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        ]
        reg_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        paths = (bold_paths + reg_paths) if bold else (reg_paths + bold_paths)

    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ─────────────────────────────────────────
# LOG HELPERS
# ─────────────────────────────────────────
def load_log():
    if UPLOAD_LOG.exists():
        try:
            return json.loads(UPLOAD_LOG.read_text())
        except Exception:
            return []
    return []


def save_log_entry(entry):
    logs = load_log()
    logs.append(entry)
    UPLOAD_LOG.write_text(json.dumps(logs, indent=2))


# Approximate spoken words-per-minute for the narration voice this bot
# uses, purely to turn a chapter's position in the script into a
# description timestamp *before* the real audio exists. This is a
# best-effort estimate, not the source of the video's actual pacing -
# on the ElevenLabs path, every spoken slide's REAL duration comes from
# ElevenLabs' own character timestamps (see generate_synced_narration()),
# not this estimate. ElevenLabs' "Adam" preset at default settings paces
# close to a natural conversational rate, similar to the edge_tts voice
# this replaced.
SPOKEN_WPM = 150.0

CHAPTER_DESCRIPTION_LABELS = {
    "HOOK": "The Problem (Hook)",
    "INTRO": "Why This Costs You (Intro)",
    "ACT 1": "Why It Breaks + Mistakes to Avoid",
    "ACT 2": "The Step-by-Step Fix + Real Results",
    "ACT 3": "Recap + Your Action Item",
}


def compute_chapter_timestamps(script: str, wpm: float = SPOKEN_WPM) -> str:
    """Build a YouTube-description chapter list with real timestamps,
    derived from how many spoken words precede each chapter marker —
    instead of a fixed guess that drifts out of sync whenever the script
    length changes (as happened when the fallback generator's word count
    didn't match its hardcoded "22:30" final chapter)."""
    parts = re.split(r"===\s*CHAPTER:\s*(.*?)\s*===", script)
    lines = []
    cumulative_words = 0
    i = 1
    while i < len(parts) - 1:
        name = parts[i].strip().upper()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        seconds = int((cumulative_words / wpm) * 60) if wpm > 0 else 0
        mm, ss = divmod(max(0, seconds), 60)
        label = CHAPTER_DESCRIPTION_LABELS.get(name, name.title())
        lines.append(f"{mm}:{ss:02d} {label}")
        cumulative_words += len(body.split())
        i += 2

    if not lines:
        lines = ["0:00 Start"]
    return "\n".join(lines)


def compute_chapter_timestamps_from_slides(slides: list) -> str:
    """Real, ground-truth YouTube chapter markers built from the ACTUAL
    slide/audio timeline (slides = [(kind, text, duration, act_name), ...]
    as returned by generate_synced_narration(), after narration has been
    generated) - not a words-per-minute guess. Every timestamp here
    matches the real video exactly, including the real silence inserted
    for the title card and each chapter-divider slide, so it can never
    drift out of sync the way compute_chapter_timestamps() (the older,
    pre-audio WPM estimate, kept below as a last-resort fallback) could.

    One marker is emitted the first time each distinct act_name/chapter
    label is seen (so the title card and its immediately-following
    chapter-divider slide - both act_name "HOOK" by construction - collapse
    into a single 0:00 entry, and a mid-act CTA slide doesn't start a new
    chapter). YouTube requires the first chapter at exactly 0:00 and at
    least 3 chapters >=10s each; a real 5-act script comfortably clears
    both.
    """
    if not slides:
        return "0:00 Start"

    lines = []
    seen_acts = set()
    t = 0.0
    for kind, text, duration, act_name in slides:
        label_key = text.strip().upper() if kind == "chapter" else act_name
        if kind in ("title", "titlehook", "chapter") and label_key not in seen_acts:
            seen_acts.add(label_key)
            mark_seconds = 0.0 if not lines else t
            mm, ss = divmod(int(max(0, mark_seconds)), 60)
            label = CHAPTER_DESCRIPTION_LABELS.get(label_key, label_key.title())
            lines.append(f"{mm}:{ss:02d} {label}")
        t += duration

    if not lines:
        lines = ["0:00 Start"]
    return "\n".join(lines)


# ─────────────────────────────────────────
# YOUTUBE TAG SANITIZER
# ─────────────────────────────────────────
def _youtube_tag_char_cost(tag: str) -> int:
    """The tags property's 500-character limit is NOT simply the sum of
    each tag's string length. Per YouTube's own docs
    (https://developers.google.com/youtube/v3/docs/videos#snippet.tags):
    "If a tag contains a space, the API server handles the tag value as
    though it were wrapped in quotation marks, and the quotation marks
    count toward the character limit." So a tag with a space costs
    len(tag) + 2, not len(tag). Almost every tag this bot generates is a
    multi-word phrase, so ignoring this made every previous character
    budget calculation quietly wrong by ~2 chars per tag — a 20-tag list
    that looked like 479/480 chars was actually ~511 real characters,
    over YouTube's hard limit, which is what produced the invalidTags
    upload rejection even after the duplicate-word tag bug was fixed.
    """
    return len(tag) + 2 if " " in tag else len(tag)


def sanitize_youtube_tags(
    raw_tags,
    max_tags=MAX_YOUTUBE_TAGS,
    max_total_chars=MAX_YOUTUBE_TAG_CHARS,
):
    cleaned_tags = []
    seen = set()
    total_chars = 0

    for raw_tag in raw_tags or []:
        if raw_tag is None:
            continue

        tag = str(raw_tag)
        tag = re.sub(r"[\x00-\x1f\x7f]", " ", tag)
        tag = tag.replace(",", " ").replace("#", "")
        # YouTube rejects the entire upload (reason: invalidTags) if any
        # single tag contains certain punctuation. Many topic titles carry
        # question marks, colons, or parentheses, so strip it defensively
        # rather than relying on every caller to pre-clean tags.
        tag = re.sub(r'[?!():;"<>]', " ", tag)
        # Collapse any immediately-repeated word (case-insensitive), e.g.
        # a tag built as "<core> explained" where <core> itself already
        # ends in "explained" — safety net on top of the root-cause fix
        # in _build_core_tag_variants().
        tag = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", tag, flags=re.IGNORECASE)
        tag = re.sub(r"\s+", " ", tag).strip()

        if not tag:
            continue

        tag = tag[:100].strip()
        key = tag.casefold()

        if key in seen:
            continue

        separator_length = 1 if cleaned_tags else 0
        tag_cost = _youtube_tag_char_cost(tag)
        new_total = total_chars + separator_length + tag_cost

        if new_total > max_total_chars:
            continue

        cleaned_tags.append(tag)
        seen.add(key)
        total_chars = new_total

        if len(cleaned_tags) >= max_tags:
            break

    return cleaned_tags


# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────
def get_authenticated_service():
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"{TOKEN_FILE} does not exist.")

    credentials = Credentials.from_authorized_user_file(
        str(TOKEN_FILE),
        SCOPES,
    )

    if credentials.expired:
        if not credentials.refresh_token:
            raise RuntimeError(
                "Google credentials are expired and have no refresh token."
            )
        credentials.refresh(Request())
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")

    service = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    expected_handle = os.environ.get(
        "EXPECTED_CHANNEL_HANDLE", ""
    ).lstrip("@").casefold()

    response = service.channels().list(
        part="snippet",
        mine=True,
    ).execute()

    items = response.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel was found for this OAuth token.")

    channel = items[0]
    snippet = channel.get("snippet", {})

    actual_title = snippet.get("title", "UNKNOWN")
    actual_handle = snippet.get("customUrl", "")
    actual_handle = actual_handle.lstrip("@").casefold()

    print(
        f"[AUTH] Uploading as channel: "
        f"{actual_title} ({actual_handle or 'no handle'})"
    )

    if expected_handle and actual_handle and expected_handle != actual_handle:
        raise RuntimeError(
            f"OAuth token belongs to @{actual_handle}, "
            f"but @{expected_handle} was expected."
        )

    return service


# ─────────────────────────────────────────
# GEMINI — 5-ACT STRUCTURE SCRIPT PROMPT
# ─────────────────────────────────────────
# ---------- v3.3.0: terminal blocks, real stories, technical review ----------
_TERMINAL_BLOCK_RE = re.compile(r"\[\[TERMINAL\]\](.*?)\[\[/TERMINAL\]\]", re.DOTALL | re.IGNORECASE)
STORIES_FILE = Path(os.environ.get("STORIES_FILE", "stories.yaml"))
SCRIPT_REVIEW = os.environ.get("SCRIPT_REVIEW", "true").strip().lower() not in ("0", "false", "no", "off")


def _strip_terminal_blocks(text: str) -> str:
    return _TERMINAL_BLOCK_RE.sub(" ", text or "")


def _spoken_word_count(script: str) -> int:
    """Words that are actually narrated: terminal blocks are on-screen only."""
    return len(_strip_terminal_blocks(script).split())


def _parse_terminal_lines(block: str) -> list:
    """[[TERMINAL]] body -> [("cmd"|"out", text), ...]"""
    lines = []
    for raw in (block or "").strip("\n").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("$ "):
            lines.append(("cmd", line.lstrip()[2:].strip()))
        else:
            lines.append(("out", line))
    return lines[:14]


def _load_stories() -> list:
    if not STORIES_FILE.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(STORIES_FILE.read_text(encoding="utf-8")) or {}
        items = data.get("stories", []) if isinstance(data, dict) else data
        out = []
        for it in items or []:
            if isinstance(it, dict) and str(it.get("story", "")).strip():
                tags = [str(t).strip().lower() for t in (it.get("tags") or []) if str(t).strip()]
                out.append({"tags": tags, "story": re.sub(r"\s+", " ", str(it["story"])).strip()})
        return out
    except Exception as exc:
        print(f"[STORIES] Could not read {STORIES_FILE}: {exc}")
        return []


def _stories_prompt_block(topic: str) -> str:
    """Real experiences the channel owner wrote in stories.yaml, matched to
    today's topic by tags. These are the ONLY first-hand stories the script
    may tell - original experience is what separates the channel from
    template content."""
    t = topic.lower()
    scored = []
    for st in _load_stories():
        score = sum(1 for tag in st["tags"] if tag and tag in t)
        if score:
            scored.append((score, st["story"]))
    scored.sort(key=lambda x: -x[0])
    picked = [story for _, story in scored[:2]]
    if not picked:
        return ("REAL EXPERIENCES: none provided for this topic. Do not tell any first-person "
                "\"this happened to me / my team\" story.")
    print(f"[STORIES] Using {len(picked)} real experience(s) from {STORIES_FILE}.")
    joined = "\n".join(f"- {x}" for x in picked)
    return ("REAL EXPERIENCES from the channel's creator (a senior DevOps engineer). Weave the most "
            "relevant one into ACT 1 or ACT 2 as \"a real incident from our team\" - keep its facts "
            "exactly as written, do not embellish numbers:\n" + joined)


def _technical_review(client, model: str, topic: str, script: str) -> str:
    """Second Gemini pass acting as a senior SRE reviewer. Only accepted if
    it keeps the structure and length; otherwise the original stays."""
    if not SCRIPT_REVIEW:
        return script
    prompt = f"""You are a senior SRE doing a technical accuracy review of a YouTube script
about "{topic}". Fix ONLY technical problems: wrong commands, flags or output formats,
outdated or invented API versions, wrong claims about how the tool behaves, and statistics
presented as fact without a source. Do not change the tone, structure, length or wording
otherwise. Keep every "=== CHAPTER: X ===" marker and every [[TERMINAL]] ... [[/TERMINAL]]
block in place and in the same format.

Return only JSON: {{"script": "the full corrected script", "changes": ["one short note per fix"]}}

SCRIPT:
{script}
"""
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        new = str(data.get("script", ""))
        markers_ok = len(re.findall(r"===\s*CHAPTER:", new)) == len(re.findall(r"===\s*CHAPTER:", script))
        w0, w1 = _spoken_word_count(script), _spoken_word_count(new)
        blocks_ok = len(_TERMINAL_BLOCK_RE.findall(new)) >= len(_TERMINAL_BLOCK_RE.findall(script)) - 1
        if markers_ok and blocks_ok and w0 and 0.85 <= w1 / w0 <= 1.15:
            changes = [str(c) for c in (data.get("changes") or [])][:10]
            print(f"[REVIEW] Technical review applied ({len(changes)} fix(es)).")
            for c in changes:
                print(f"[REVIEW]   - {c[:200]}")
            return new
        print(f"[REVIEW] Review output rejected (markers_ok={markers_ok}, blocks_ok={blocks_ok}, "
              f"words {w0}->{w1}) - keeping the original script.")
    except Exception as exc:
        print(f"[REVIEW] Technical review skipped: {str(exc)[:200]}")
    return script


def generate_with_gemini(topic: str, day_num: int, next_topic: str = "") -> dict:
    if not HAS_GEMINI:
        raise RuntimeError("google-genai is not installed.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    # Hard per-request timeout: run #251 sat 5 minutes on one dead
    # connection ("Server disconnected without sending a response")
    # before the first retry even started. Value is in milliseconds.
    client = genai.Client(api_key=api_key, http_options={"timeout": GEMINI_TIMEOUT_SEC * 1000})
    core = topic.split("—")[0].strip()
    next_core = (next_topic.split("—")[0].strip() if next_topic else "")

    stories_block = _stories_prompt_block(topic)
    prompt = f"""
You are the lead scriptwriter for DevOps Genius Zone, a daily YouTube
channel for working DevOps engineers and people breaking into DevOps in
the US. Every episode is a "Production Incident File": one realistic
production problem that working DevOps/SRE engineers actually hit, walked
through the way a senior engineer would really debug it on call. Goal: a
viewer who hits this problem at work can fix it after watching, and keeps
watching because the story pulls them through.

Write Day {day_num} of 365 for this topic:

{topic}

{"Tomorrow's video will cover: " + next_topic if next_topic else ""}

The video is 10-12 minutes long. Most viewers decide in the first 30
seconds and leave around 1:40, so the opening must drop them into the
incident and every paragraph must earn the next one. Sound like one
experienced engineer talking to another on a call: natural, direct,
spoken language, never a lecture and never marketing fluff.

The script must contain exactly these four sections, in this order, each
starting with its own chapter marker:

=== CHAPTER: HOOK ===
=== CHAPTER: ACT 1 ===
=== CHAPTER: ACT 2 ===
=== CHAPTER: ACT 3 ===

HOOK - THE INCIDENT (70-100 words, about 30 seconds spoken):
Cold open inside the incident for {core}: the alert, the time, the
business impact (for example "2:13 AM. The pager goes off. Checkout is
throwing 5xx errors for 38 percent of users."). No greeting, no "welcome
back", no "in this video", no channel name. Then why the obvious first
move is wrong, and a promise of the exact fix plus how to make sure it
never happens again. End on an open loop the viewer needs answered.

ACT 1 - SYMPTOMS AND THE WRONG FIRST MOVE (400-500 words):
What the engineer actually sees: the exact error messages, dashboards and
command output. The mental model people are missing. The 2-3 common wrong
moves (restart it, scale it up, roll back blindly) and what each one costs
in production. After the first genuinely useful insight, one short,
natural line asking for a like so more engineers with this problem find
the video.

ACT 2 - DEBUG, ROOT CAUSE, FIX (800-1000 words):
The real debugging path, step by step, in the order a senior engineer
would do it, with the exact commands and what to look for in their
output. Name the root cause clearly. Then the fix, with the specific
config keys, flags or code involved, and how to verify the fix worked in
production. Mention one trade-off or gotcha of the fix.

ACT 3 - PREVENT IT: PRODUCTION BEST PRACTICES (300-400 words):
How a mature team makes sure this never pages anyone again: 3-5 concrete
best practices (alerts with the right thresholds, limits/quotas, policy
checks in CI, runbooks, chaos or load tests - whatever truly fits this
topic). Then how this exact scenario shows up as an interview question
and how to answer it in two sentences. One action item the viewer can do
in the next 10 minutes, one specific question for the comments, then a
like/subscribe ask with a real reason: new production incident breakdown
every day{", including tomorrow's on " + next_core if next_core else ""}. End with "See you tomorrow."

TERMINAL BLOCKS (very important - these become animated terminal scenes):
Put 4-7 terminal blocks inside ACT 1 and ACT 2 (at most 1 in the HOOK).
Each block is its own paragraph, exactly in this format, with NO blank
line inside the block:
[[TERMINAL]]
$ kubectl get pods -n checkout
NAME                           READY   STATUS             RESTARTS   AGE
checkout-api-7d9f8c6b5-x2k4q   0/1     CrashLoopBackOff   7          12m
[[/TERMINAL]]
Rules: lines starting with "$ " are commands, every other line is output.
2-10 lines per block, max 90 characters per line. Commands and output
must be technically correct and realistic for current tool versions (no
fake flags, no invented API versions). The spoken paragraph right AFTER
each block must talk the viewer through that exact command and its
output. Terminal blocks are shown on screen only - never read them aloud
and never repeat raw output lines in the spoken text.

{stories_block}

SCRIPT RULES:
- {SCRIPT_TARGET_WORDS[0]}-{SCRIPT_TARGET_WORDS[1]} SPOKEN words total (terminal blocks don't count). Do NOT exceed {SCRIPT_TARGET_WORDS[1]}.
- Continuous spoken paragraphs separated by blank lines, contractions,
  direct address ("you"). Vary sentence length; short punchy sentences
  are good. Commands in spoken text should be said naturally ("run
  kubectl describe pod on it"), never as raw syntax.
- No bullet points, headers, markdown, stage directions or emojis inside
  the spoken text.
- Honesty: never invent statistics presented as fact, and never claim a
  personal experience unless it comes from REAL EXPERIENCES above. Frame
  the incident as "here's a scenario that happens all the time" /
  "picture this", not as something that happened to you.
- Return only one valid JSON object, nothing else.

TITLE RULES:
- Under 60 characters. Specific and outcome- or problem-driven, e.g.
  "Deploy to EKS with GitHub Actions and ArgoCD", "Terraform State
  Locking: Stop Corrupting Your State", "Build a Zero-Downtime CI/CD
  Pipeline From Scratch".
- Name the tool. Lead with an action verb ("Build", "Deploy", "Fix",
  "Stop") or the concrete problem.
- Never use generic filler like "Full Guide for DevOps Engineers",
  "Everything You Need to Know", "A Step-by-Step Walkthrough",
  "What Senior Engineers Actually Know", "The Practical Guide".
- Add a year only if the topic is genuinely time-sensitive.

JSON FORMAT:
{{
  "title": "Title following the TITLE RULES",
  "title_alternatives": ["Alternative 1", "Alternative 2"],
  "description": "YouTube description, 1500-2500 characters: first line states the problem this video solves, then a short list of what the viewer will learn, then the exact literal line [[CHAPTERS]] on its own line (do NOT write timestamps yourself - this placeholder is replaced with real, audio-measured chapter timestamps automatically after generation), then a subscribe line mentioning tomorrow's topic, then hashtags",
  "script": "The complete four-section spoken script",
  "tags": ["15-25 specific, searched YouTube tags, no duplicates"],
  "thumbnail_headline": "2-4 words, uppercase, the payoff or the pain, not just the tool name (e.g. 'DEPLOY ON EVERY PUSH', 'STOP STATE LOCKS')",
  "thumbnail_subtext": "Max six words, the tool/topic name or a reason to click"
}}
"""

    # Each model gets GEMINI_MAX_RETRIES attempts with a short backoff;
    # a 404 / "not found" (retired model name) skips straight to the next
    # model. Only when every model fails do we use the offline generator.
    last_exc = None
    best_short = None
    for model in GEMINI_MODELS:
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            raw = ""
            try:
                print(f"[AI] Generating with {model} (attempt {attempt}/{GEMINI_MAX_RETRIES})...")
                response = client.models.generate_content(model=model, contents=prompt)

                raw = (response.text or "").strip()
                if not raw:
                    raise RuntimeError("Gemini returned an empty response.")
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
                    raw = re.sub(r"\s*```$", "", raw)

                data = json.loads(raw)
                if not isinstance(data, dict) or not isinstance(data.get("script"), str):
                    raise ValueError("Gemini response is invalid.")

                data.setdefault("title_alternatives", [])
                data.setdefault("tags", [])
                data.setdefault("thumbnail_headline", core.upper()[:40])
                data.setdefault("thumbnail_subtext", core)
                data["_source"] = f"gemini:{model}"
                words = _spoken_word_count(data["script"])
                if words < SCRIPT_MIN_WORDS:
                    print(f"[AI] {model} script is only {words:,} words (min {SCRIPT_MIN_WORDS:,}) - trying the next model.")
                    if best_short is None or words > _spoken_word_count(best_short["script"]):
                        best_short = data
                    break  # same model tends to repeat the length; move on
                data["script"] = _technical_review(client, model, topic, data["script"])
                return data

            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                print(f"[AI] {model} error (attempt {attempt}/{GEMINI_MAX_RETRIES}): {msg[:300]}")
                if re.search(r"\b404\b|NOT_FOUND|not found|is not supported", msg):
                    print(f"[AI] {model} is unavailable for this key - trying the next model.")
                    break
                if attempt < GEMINI_MAX_RETRIES:
                    wait = 6 * attempt
                    print(f"[AI] Retrying {model} in {wait}s...")
                    time.sleep(wait)
        else:
            print(f"[AI] {model} failed {GEMINI_MAX_RETRIES}x - trying the next model.")

    if best_short is not None:
        print(f"[AI] No model hit {SCRIPT_MIN_WORDS:,} words - using the longest Gemini script "
              f"({_spoken_word_count(best_short['script']):,} words, {best_short['_source']}).")
        return best_short
    print(f"[AI] All Gemini models failed ({', '.join(GEMINI_MODELS)}): {last_exc}")
    raise last_exc


# ─────────────────────────────────────────
# OFFLINE FALLBACK — 5-ACT TEMPLATE
# ─────────────────────────────────────────
def _company_for_topic(topic: str) -> tuple:
    h = sum(ord(c) for c in topic)
    a = COMPANY_EXAMPLES[h % len(COMPANY_EXAMPLES)]
    b = COMPANY_EXAMPLES[(h + 3) % len(COMPANY_EXAMPLES)]
    return a, b

def _topic_parts(topic: str) -> tuple:
    """'CDK for Terraform — Write AWS Infrastructure in TypeScript' ->
    ('CDK for Terraform', 'Write AWS Infrastructure in TypeScript')."""
    parts = re.split(r"\s[—–]\s", topic, maxsplit=1)
    core = parts[0].strip()
    sub = parts[1].strip() if len(parts) > 1 else ""
    return core, sub


def _generate_long_fallback(topic: str, day_num: int, next_topic: str = "") -> str:
    """Offline script used only when every Gemini model fails. ~2,000
    words (10-12 min). Opens on the payoff - no greeting, no agenda."""
    core, sub = _topic_parts(topic)
    next_core = _topic_parts(next_topic)[0] if next_topic else "tomorrow's topic"
    company_a, company_b = _company_for_topic(topic)
    promise = sub.rstrip(".?!") if sub else f"how {core} actually works in production"

    script = f"""=== CHAPTER: HOOK ===
{core}: {promise}. That's exactly what you'll be able to do by the end of this video. Most engineers learn {core} just well enough to sound confident in a meeting, and it falls apart the first time production breaks at 2am. So here's the plan: the one mental model that makes {core} click, the three mistakes behind most of the pain, and a step-by-step fix you can use at work this week.

=== CHAPTER: ACT 1 ===
Here's the real problem with {core}, and it's not a knowledge gap, it's a mental model gap. Most engineers treat {core} as a one-time setup: configure it once, move on, forget it exists. But production is never static. Nodes fail, dependencies update, traffic spikes, and someone always makes a manual change under pressure at exactly the wrong moment. A one-time setup can't survive that.

What actually works is desired-state thinking. You define what the end result should look like, in code, and you build a system that keeps checking reality against that definition and corrects drift. Think thermostat, not space heater. You don't babysit the temperature, you declare it, and the system keeps nudging reality back toward it.

That one shift is what separates engineers who get paged and panic from engineers who get paged and calmly fix it. If that just reframed how you think about {core}, hit like. It's the signal YouTube uses to show this to the next engineer stuck on the same problem.

Now, the three mistakes. Mistake one: jumping straight into configuration with no written goal, so six months later nobody can explain why a setting exists, and every temporary fix quietly becomes permanent. Mistake two: secrets and credentials sitting in plain text instead of a secrets manager. That turns a small mistake into a security incident the moment that config lands in a log, a screenshot, or a public repo.

Mistake three is the big one: no rollback plan. Before you change anything about {core}, you should already know exactly how you'd undo it. Ask one question before every change: can I undo this in under a minute? If the answer is no, you don't have a rollback plan. You have a hope. And hope is not a strategy at 2am.

All three mistakes have the same root cause. The configuration lives in someone's head or someone's console session instead of in version control. If {core} isn't in git, you don't actually know what's running in production. You know what you think is running. Every change should go through a pull request, get reviewed by another human, and leave a record of who changed what and why. That turns "no idea why this is set this way" into a two-minute git blame.

There's one more trap worth naming, because it hides inside teams that do everything else right: staging that doesn't look like production. If your staging setup for {core} runs at a different scale, with different data and different network rules, then a green test in staging only proves it works somewhere that doesn't matter. It doesn't need to be a perfect mirror. It needs to be close enough that the failures you'd actually hit in production show up there first. Teams that skip this end up testing in production by accident, and that's the most expensive kind of testing there is, because the bill arrives as an incident instead of a failed pipeline.

And then there's ownership. {core} often sits on the boundary between two or three teams, and everyone assumes someone else is watching it. The fix isn't one hero who owns it forever. It's making ownership explicit, even if it rotates, so that when something drifts there's a name attached to "who gets paged first," not a group chat where three people each assume someone else already saw the alert.

=== CHAPTER: ACT 2 ===
So here's the fix, step by step, the way I'd walk a teammate through it.

Step one: write the goal down in one plain sentence, then define the smallest possible desired state in code. Just enough to prove the idea works end to end. Commit it before you apply anything.

Step two: apply least privilege from the start. Whatever runs {core} gets only the permissions it strictly needs, and credentials come from a secrets manager or short-lived identity, never from a file in the repo. Fixing this later is always harder than doing it on day one.

Step three: add complexity one piece at a time. Get the simple version working, confirm it behaves the way you expect, then layer in the next requirement, whether that's scaling, security policy, or a new integration. This is the difference between debugging one variable and debugging five at once. Experienced engineers aren't faster because they're smarter. They're faster because they change one thing at a time.

Step four: test it like real code. Validate and lint on every pull request, add a few small tests for the behavior you actually care about, and block merges that fail. This single habit catches a whole class of production incidents before they leave a pull request.

Step five: roll out in stages. Push the change to a small slice first. One environment, one region, or one low-risk service. Watch real signals, then expand. A staged rollout turns "the whole fleet is broken" into "one small slice is broken and I caught it first."

Step six: make drift visible. Run a scheduled check that compares desired state with actual state and alerts when they differ. If someone hot-fixes production by hand, you find out the same day, not during the next outage. Pair that with dashboards for the four golden signals: latency, traffic, errors, and saturation. Every alert should map to an action a human can take, or it's just noise.

Step seven: practice the rollback. Pick a quiet afternoon, make a small change, and actually undo it, end to end, while timing yourself. If it takes longer than a minute, simplify until it doesn't. The same goes for backups: a backup you've never test-restored is an assumption, not a backup.

Step eight: write a short runbook. What it does, why it's configured this way, what to check first when it breaks, and how to roll back. Half a page. The next on-call engineer, quite possibly future you, will thank you.

Let me make that concrete with what a single change should look like from start to finish. You open a branch and make one small change to {core}. The pipeline runs formatting, validation and your tests automatically, and posts a plan or a diff right on the pull request, so the reviewer sees exactly what will change before anything touches a real environment. A teammate reviews it, asks one question, you answer it in the PR, and it merges. The pipeline applies it to staging, runs a quick smoke test, then promotes to one production slice. Your dashboard stays green for ten minutes, and it rolls out to the rest. If anything looks off, the rollback is reverting that one commit. Notice what's missing from that story: nobody logged into a console, nobody ran a command from their laptop, and nobody had to remember anything at 2am.

Step nine: watch the cost, not just the correctness. Cloud bills spiral quietly when nobody owns them. Tag everything {core} creates so you can see what it actually costs, and start with your non-production environments, because that's almost always the fastest win. Scaling dev and staging down overnight and on weekends routinely cuts a big chunk of the bill, and it takes an afternoon to set up. That's the kind of result that gets noticed by people who control budget, not just by other engineers.

Step ten: treat every incident as free training data. When something does break, and eventually something will, run a blame-free postmortem that asks what the system allowed to happen, not who made the mistake. The output should be a specific change: an alert that should have fired, a test that should have existed, a runbook step that was missing. Teams that do this consistently get measurably safer over time, because the same failure can't happen the same way twice.

The cloud doesn't change the discipline. On AWS you'll lean on IAM, CloudWatch and CloudTrail. On Azure, RBAC, Azure Policy and Azure Monitor. On GCP, IAM, Organization Policy and Cloud Monitoring. The tool names change. Desired state, least privilege, staged rollout and tested rollback stay exactly the same, and that's what transfers with you when you switch jobs.

Here's what this looks like in real life. A team at {company_a} applied exactly these steps to {core} and cut their time to recover from incidents dramatically, because on-call went from guessing to reading a dashboard that showed exactly what had drifted. A team at {company_b} made small, reversible, staged changes the default, and their failed deployments dropped by more than half within a quarter. Neither team bought a new tool. They changed the process.

=== CHAPTER: ACT 3 ===
Let's bring it home. The problem with {core} was never that it's too hard. It's that people treat it as a one-time setup instead of an ongoing practice: desired state in git, least privilege, small staged changes, and a rollback you've actually tested.

Your action item for the next ten minutes: open a sandbox and build the smallest working version of what we just covered. Commit it, change one thing, and roll it back. That muscle memory is what turns "I watched a video about this" into "I can do this under pressure."

If you're on a small team and this sounds like a lot of process for four engineers, that's fair. You don't need all ten steps on day one. Start with version control and a tested rollback, because those protect you from the mistakes a small team can least afford, then add the rest as you grow.

And if you're interviewing, don't just define {core}. Tell a short story about a time it went wrong and what you'd do differently now. That's the signal senior interviewers are actually listening for.

Tell me in the comments: what's the one mistake with {core} that's bitten you personally? I read every comment, and the best ones become future videos.

If this helped, hit like and subscribe. There's a new DevOps video every day, and tomorrow we're covering {next_core}. See you tomorrow.
"""
    return script


# Patterns that mark a generic, low-CTR template title. Kept so titles
# coming from ANY source (old Gemini habits, old offline code) get cleaned.
TEMPLATE_TITLE_SUFFIXES = [
    "Full Guide for DevOps Engineers (2026)",
    "Full Guide for DevOps Engineers",
    "What Senior Engineers Actually Know (2026)",
    "What Senior Engineers Actually Know",
    "The Practical Guide for US DevOps Teams",
    "Real-World Guide + Common Mistakes (2026)",
    "Real-World Guide + Common Mistakes",
    "Everything You Need to Know in 2026",
    "Everything You Need to Know",
    "The Mistake Most Engineers Still Make",
    "A Step-by-Step Walkthrough for 2026",
    "A Step-by-Step Walkthrough",
]
_TEMPLATE_SUFFIX_RE = re.compile(
    r"\s*(?:[—–:|-]\s*)(?:" + "|".join(re.escape(s) for s in TEMPLATE_TITLE_SUFFIXES) + r")\s*$",
    re.IGNORECASE,
)


def _title_from_topic(topic: str) -> str:
    """Use the curriculum topic itself - it is already a specific,
    outcome-driven line - as the title: 'X — Y' -> 'X: Y'."""
    core, sub = _topic_parts(topic)
    if sub:
        full = f"{core}: {sub}"
        if len(full) <= 80:
            return full
    return core


def clean_title(title: str, topic: str) -> str:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    stripped = _TEMPLATE_SUFFIX_RE.sub("", t).strip(" —–-:|")
    if stripped != t:
        print(f"[SEO] Removed generic title suffix: {t!r}")
        # A bare tool name ("Helm vs Kustomize") is weaker than the
        # curriculum's own specific topic line - prefer that.
        if len(stripped) < 30:
            stripped = _title_from_topic(topic)
    t = stripped
    if len(t) < 8:
        t = _title_from_topic(topic)
    return t[:100]


def _thumbnail_headline_from_topic(topic: str) -> str:
    core, sub = _topic_parts(topic)
    sub_words = re.sub(r"[?!.]", "", sub).split()
    if 2 <= len(sub_words) <= 5 and len(" ".join(sub_words)) <= 40:
        return " ".join(sub_words).upper()
    out = ""
    for w in core.split():  # never cut a word in half
        if len(out) + len(w) + 1 > 28:
            break
        out = f"{out} {w}".strip()
    return (out or core[:28]).upper()


# Extra SEO tags layered on top of FALLBACK_TAGS for broader reach —
# beginner search intent, US job-market intent, and adjacent role titles
# that DevOps content also gets discovered under.
FALLBACK_EXTRA_TAGS = [
    "devops for beginners",
    "how to devops",
    "tech jobs usa",
    "software engineer career",
    "cloud engineer",
    "site reliability engineering",
    "sre",
    "devops roadmap",
    "devops best practices",
    "devops mistakes",
]


def _build_core_tag_variants(core: str) -> list:
    """Build "<core> <suffix>" style SEO tag variants without producing a
    nonsensical duplicated-word tag when `core` already ends with that
    suffix's word(s) — e.g. core="Docker Networking Explained" must NOT
    produce "docker networking explained explained". Many of the 365
    topics already end in words like "Explained" or "Mistakes", since for
    topics with no em-dash `core` is the entire topic title.
    """
    core_lower = core.lower()
    core_words = re.findall(r"[a-z0-9]+", core_lower)

    variants = [core_lower]

    def add_suffixed(text: str) -> None:
        suffix_words = re.findall(r"[a-z0-9]+", text.lower())
        # Skip this variant if the core already ends with these exact
        # trailing words (avoids "... explained explained", "... mistakes
        # mistakes", etc.)
        if suffix_words and core_words[-len(suffix_words):] == suffix_words:
            return
        variants.append(f"{core_lower} {text}")

    add_suffixed("tutorial")
    add_suffixed("2026")
    add_suffixed("explained")
    add_suffixed("for beginners")
    add_suffixed("mistakes")
    variants.append(f"learn {core_lower}")

    return variants


def generate_fallback_content(topic: str, day_num: int, next_topic: str = "") -> dict:
    core = topic.split("—")[0].strip()
    next_core = (next_topic.split("—")[0].strip() if next_topic else "a new DevOps topic")
    script = _generate_long_fallback(topic, day_num, next_topic)

    title = _title_from_topic(topic)

    description = (
        f"Struggling with {core}? Here's the problem: most engineers learn it just deeply "
        f"enough to sound confident in a meeting, and it falls apart the moment something "
        f"actually breaks. In this video I break down exactly why {topic} trips people up, "
        f"and the concrete, step-by-step way to actually get it right.\n\n"
        f"By the end of this video you'll know how to:\n"
        f"- Understand the real mental model behind {core}, not just the surface-level definition\n"
        f"- Spot and avoid the specific mistakes that cause most {core}-related incidents\n"
        f"- Apply a step-by-step fix you can use today, on AWS, Azure, or GCP\n"
        f"- Talk about {core} in an interview the way a senior engineer would\n\n"
        f"[[CHAPTERS]]\n\n"
        f"KEY TAKEAWAYS\n"
        f"1. The mental model behind {core}\n"
        f"2. The exact mistakes that cause most of the pain around it\n"
        f"3. A step-by-step fix, with a real-world result\n"
        f"4. How {core} affects cost, security, and compliance\n"
        f"5. One action item you can do in the next 10 minutes\n\n"
        f"New DevOps video every single day — tomorrow we're covering {next_core}. "
        f"Subscribe with notifications on so you don't miss it:\n{CHANNEL_URL}\n\n"
        f"Got a question or a war story about {core}? Drop it in the comments — I read and "
        f"respond to every one, and the best ones become future videos.\n\n"
        f"Day {day_num} of 365 | {CHANNEL_NAME}\n\n"
        f"{HASHTAGS}"
    )

    return {
        "title": title,
        "title_alternatives": [
            f"Stop Getting {core} Wrong: Here's the Fix",
        ],
        "description": description,
        "script": script,
        "tags": list(
            set(
                FALLBACK_TAGS
                + FALLBACK_EXTRA_TAGS
                + _build_core_tag_variants(core)
            )
        ),
        "thumbnail_headline": _thumbnail_headline_from_topic(topic),
        "thumbnail_subtext": core,
        "_source": "offline",
    }


# ─────────────────────────────────────────
# CONTENT ORCHESTRATOR
# ─────────────────────────────────────────
def _enforce_script_length(script: str, max_words: int = SCRIPT_MAX_WORDS) -> str:
    """Safety net for a model that ignores the word target: drop whole
    MIDDLE paragraphs of ACT 1 / ACT 2 (never the HOOK, never ACT 3, never
    the first or last paragraph of a chapter) until the script fits."""
    if _spoken_word_count(script) <= max_words:
        return script
    parts = re.split(r"(===\s*CHAPTER:\s*.*?\s*===)", script)
    # parts = [pre, marker, body, marker, body, ...]
    chapters = []
    for i in range(1, len(parts) - 1, 2):
        paras = [p for p in re.split(r"\n\s*\n", parts[i + 1].strip()) if p.strip()]
        chapters.append([parts[i], paras])

    def total():
        return sum(_spoken_word_count(" ".join(p)) for _, p in chapters)

    def _protected(paras, k):
        return bool(_TERMINAL_BLOCK_RE.search(paras[k])) or (k > 0 and bool(_TERMINAL_BLOCK_RE.search(paras[k - 1])))

    before = _spoken_word_count(script)
    trimmable = [c for c in chapters if re.search(r"ACT\s*[12]\b", c[0].upper())]
    while total() > max_words:
        best = None
        for c in trimmable:
            choices = [k for k in range(1, len(c[1]) - 1) if not _protected(c[1], k)]
            if choices:
                idx = max(choices, key=lambda k: len(c[1][k].split()))
                cand = (len(c[1]), c, idx)
                if best is None or cand[0] > best[0]:
                    best = cand
        if best is None:
            break
        best[1][1].pop(best[2])
    out = "\n\n".join(f"{marker}\n" + "\n\n".join(paras) for marker, paras in chapters)
    print(f"[CONTENT] Script was {before:,} spoken words - trimmed to {_spoken_word_count(out):,} (cap {max_words:,}).")
    return out


def generate_content(topic: str, day_num: int, next_topic: str = "") -> dict:
    data = None
    if HAS_GEMINI and os.environ.get("GEMINI_API_KEY"):
        try:
            print(f"[AI] Gemini models (in order): {', '.join(GEMINI_MODELS)}")
            data = generate_with_gemini(topic, day_num, next_topic)
            print(f"[AI] Gemini generation successful ({data.get('_source')}).")
        except Exception as exc:
            print(f"[AI] Gemini failed: {exc} - using offline generator.")
    else:
        print("[AI] Gemini is not configured - using offline generator.")

    if data is None:
        data = generate_fallback_content(topic, day_num, next_topic)

    data["title"] = clean_title(data.get("title", ""), topic)
    data["script"] = _enforce_script_length(str(data.get("script", "")))
    return data


# ─────────────────────────────────────────
# SCRIPT -> SLIDE SEGMENTS (shared by both the exact-sync ElevenLabs
# path and the approximate edge_tts fallback path)
# ─────────────────────────────────────────
# "Structural" slides carry no narration of their own (chapter dividers,
# CTA overlays, the title card, the outro card) - they get a fixed
# screen duration. "Spoken" slides (hook/tip/body) are real, contiguous
# substrings of the narration and get their EXACT spoken duration from
# ElevenLabs' character-level timestamps when that path is available.
# Shorter than before (was 5.0/4.5/4.0/5.0): every structural slide is
# dead air, and dead air is where viewers click away.
STRUCTURAL_SLIDE_DURATIONS = {"title": 3.0, "chapter": 2.5, "cta": 3.0, "outro": 4.0}
# "titlehook" = the opening slide: shows the title-card visual while the
# first lines of the HOOK are already being spoken (no silent intro).
SPOKEN_SLIDE_KINDS = {"titlehook", "hook", "tip", "body", "stat", "learn", "compare", "recap", "terminal"}

# v3.3.0: narration chunk text -> terminal lines [("cmd"|"out", text), ...]
# for "terminal" slides (filled by parse_script_to_segments()).
_TERMINAL_SCENES = {}


def _render_kind(kind: str) -> str:
    """Which visual layout a slide kind uses."""
    return "title" if kind == "titlehook" else kind


def _classic_kind(kind: str) -> str:
    """Layout for the classic (non-cinematic) renderers, which have no
    terminal layout - they show the narration on a body slide instead."""
    return "body" if kind == "terminal" else _render_kind(kind)


def _act_name_for_chapter(chap_title: str) -> str:
    for act in ACT_ORDER:
        if act in chap_title:
            return act
    if "INTRO" in chap_title:
        return "INTRO"
    return "HOOK"


def parse_script_to_segments(script: str) -> list:
    """Parse the raw === CHAPTER: X === script into the ordered list of
    (kind, text, act_name) slides - same structure/order/keyword-based
    hook-vs-tip-vs-body classification the video has always used, just
    extracted out of build_video() so both TTS paths (exact-sync
    ElevenLabs, approximate edge_tts fallback) can build the same slide
    list from a single source of truth instead of two independently
    re-implemented parsers drifting apart over time. No durations yet -
    see STRUCTURAL_SLIDE_DURATIONS / generate_synced_narration().
    """
    raw_sections = re.split(r"===\s*CHAPTER:\s*(.*?)\s*===", script)
    chapters = []
    i = 1
    while i < len(raw_sections) - 1:
        chap_title = raw_sections[i].strip().upper()
        chap_body = raw_sections[i + 1].strip() if i + 1 < len(raw_sections) else ""
        chapters.append((chap_title, chap_body))
        i += 2
    if not chapters:
        chapters = [("HOOK", script)]

    # v3.2.0: the video opens straight into narration. The first spoken
    # chunk is rendered on the title-card visual ("titlehook"), the HOOK
    # chapter gets no divider card, and the only mid-video CTA sits at the
    # ACT 2 boundary (the old 40%/80% positions put a silent CTA ~25s in).
    segments = []
    opened = False

    for ch_idx, (chap_title, chap_body) in enumerate(chapters):
        act_name = _act_name_for_chapter(chap_title)
        if ch_idx > 0:
            if act_name == "ACT 2":
                segments.append(("cta", "", act_name))
            segments.append(("chapter", chap_title, act_name))
        paras = [p.strip() for p in re.split(r"\n\s*\n", chap_body) if p.strip()]
        if not paras:
            paras = [chap_body] if chap_body else []

        pending_terminal = None
        for para in paras:
            # [[TERMINAL]] blocks are on-screen only: they become a
            # "terminal" slide shown while the NEXT spoken chunk explains it.
            blocks = _TERMINAL_BLOCK_RE.findall(para)
            if blocks:
                lines = _parse_terminal_lines(blocks[-1])
                if lines:
                    pending_terminal = lines
                para = _strip_terminal_blocks(para).strip()
                if not re.search(r"[A-Za-z0-9]", para):
                    continue
            is_hook = any(kw in para.lower() for kw in [
                "mistake", "never leave", "warning", "danger", "watch out", "be careful",
                "problem", "breaks", "trips people up", "wrong", "costs you", "goes wrong",
                "the real problem", "here's where it goes wrong",
            ])
            is_tip = any(kw in para.lower() for kw in [
                "pro tip", "best practice", "senior engineers", "i recommend",
                "here's the solution", "step by step", "step one", "step two", "step three",
                "the fix", "here's how", "here's exactly",
            ])
            kind = "hook" if is_hook else "tip" if is_tip else "body"

            sentences = [s.strip() for s in para.split(". ") if s.strip()]
            for c_start in range(0, len(sentences), 3):
                chunk = ". ".join(sentences[c_start: c_start + 3])
                if chunk and not chunk.endswith((".", "?", "!")):
                    chunk += "."
                if not re.search(r"[A-Za-z0-9]", chunk):
                    continue
                if not opened:
                    segments.append(("titlehook", chunk, act_name))
                    opened = True
                elif pending_terminal:
                    _TERMINAL_SCENES[chunk] = pending_terminal
                    segments.append(("terminal", chunk, act_name))
                    pending_terminal = None
                else:
                    segments.append((kind, chunk, act_name))

    segments.append(("cta", "", "ACT 3"))
    segments.append(("outro", "Start Applying It Today.\nSee you in the next video.", "ACT 3"))

    # Cinematic benefit slides (stat / learn / compare / recap) - see the
    # CINEMATIC VISUAL ENGINE block. Never allowed to break the video.
    if _VISUAL_CTX.get("topic"):
        try:
            plan = build_visual_plan(_VISUAL_CTX["topic"], _VISUAL_CTX.get("day", 0), segments)
            segments = _insert_benefit_slides(segments, plan)
            _VISUAL_CTX["plan"] = plan
            print(f"[VISUALS] Added benefit slides (stat/learn/compare/recap) - category: {plan['category']}.")
        except Exception as exc:
            _VISUAL_CTX.pop("plan", None)
            print(f"[VISUALS] Benefit slides skipped ({exc}).")
    return segments


# ─────────────────────────────────────────
# TTS + EXACT SLIDE SYNC — ELEVENLABS (primary) + EDGE_TTS (fallback)
# ─────────────────────────────────────────
# generate_synced_narration() is the single entry point: it turns a
# script into (slides_with_real_durations, audio_mp3, engine_used).
#
# Primary path (ElevenLabs configured): every "spoken" slide's on-screen
# duration is the EXACT time ElevenLabs took to say that slide's exact
# text (via the character-timestamp API), and every "structural" slide
# (title/chapter/cta/outro) gets real SILENCE inserted into the audio
# track for its fixed duration. The final audio.mp3 is built by
# concatenating one clip per slide, in slide order - so the video and
# the audio can never drift, by construction, not by averaging.
#
# Fallback path (edge_tts, or if the ElevenLabs attempt fails at any
# point): a single continuous narration track is generated for the full
# spoken text, and slide durations are approximated - structural slides
# keep their fixed duration, and the remaining time is split evenly
# across the spoken slides. This is the same approximation the bot
# always used; it's a reasonable degradation, not a broken one.
def _ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _generate_silence_clip(duration: float, dest_path: Path, sample_rate: int = 44100):
    # sample_rate must match the speech clips it gets concatenated with
    # (44.1 kHz ElevenLabs, 24 kHz edge_tts) or the concat glitches.
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", f"{max(duration, 0.1):.3f}", "-q:a", "9", str(dest_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _extract_audio_range(src_path: Path, start: float, end: float, dest_path: Path):
    duration = max(end - start, 0.05)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src_path), "-ss", f"{max(start, 0.0):.3f}",
            "-t", f"{duration:.3f}", "-q:a", "2", str(dest_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _concat_clips(clip_paths: list, output_mp3: Path):
    if len(clip_paths) == 1:
        if clip_paths[0] != output_mp3:
            clip_paths[0].replace(output_mp3)
        return
    concat_dir = output_mp3.parent
    concat_file = concat_dir / f"{output_mp3.stem}_concat.txt"
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.resolve().as_posix()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c:a", "libmp3lame", "-q:a", "2", str(output_mp3)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    concat_file.unlink(missing_ok=True)


_elevenlabs_voice_id_cache = None


def _resolve_elevenlabs_voice_id(client: "ElevenLabs") -> str:
    """Resolve ELEVENLABS_VOICE_NAME (default "Adam") to a voice_id via
    the account's live voice library instead of hardcoding an ID that
    ElevenLabs could retire or rename. Cached per-process since this bot
    only renders one video per run. Falls back to the historical Adam
    premade-voice ID (with a loud warning) if the name lookup comes back
    empty - e.g. a plan/library that no longer includes it by default.
    """
    global _elevenlabs_voice_id_cache
    if _elevenlabs_voice_id_cache:
        return _elevenlabs_voice_id_cache

    if ELEVENLABS_VOICE_ID:
        print(f"[TTS] Using pinned ELEVENLABS_VOICE_ID override: {ELEVENLABS_VOICE_ID}")
        _elevenlabs_voice_id_cache = ELEVENLABS_VOICE_ID
        return _elevenlabs_voice_id_cache

    try:
        resp = client.voices.search(search=ELEVENLABS_VOICE_NAME, page_size=10)
        candidates = list(getattr(resp, "voices", []) or [])
        exact = next(
            (v for v in candidates if (v.name or "").strip().casefold() == ELEVENLABS_VOICE_NAME.casefold()),
            None,
        )
        chosen = exact or (candidates[0] if candidates else None)
        if chosen:
            print(f"[TTS] Resolved voice '{ELEVENLABS_VOICE_NAME}' -> voice_id {chosen.voice_id} ({chosen.name}).")
            _elevenlabs_voice_id_cache = chosen.voice_id
            return _elevenlabs_voice_id_cache
    except Exception as exc:
        print(f"[TTS] Voice lookup for '{ELEVENLABS_VOICE_NAME}' failed: {exc}")

    print(
        f"[WARN] Could not find a voice named '{ELEVENLABS_VOICE_NAME}' in this account's "
        f"library. Falling back to the historical Adam voice_id "
        f"({ELEVENLABS_FALLBACK_ADAM_VOICE_ID}). Set ELEVENLABS_VOICE_ID to pin a voice "
        f"explicitly if this keeps happening."
    )
    _elevenlabs_voice_id_cache = ELEVENLABS_FALLBACK_ADAM_VOICE_ID
    return _elevenlabs_voice_id_cache


def _pack_spoken_segments_into_chunks(spoken: list, max_chars: int = ELEVENLABS_MAX_CHUNK_CHARS) -> list:
    """spoken is [(segment_index, text), ...]. Packs consecutive spoken
    segments into API-call-sized chunks WITHOUT ever splitting a single
    segment across two chunks (unlike the old sentence-level chunker) -
    that's what lets us map ElevenLabs' character timestamps straight
    back to "which slide" with simple offset arithmetic. Returns a list
    of chunks, each a list of (segment_index, text, local_start, local_end)
    describing where that segment's text falls inside the chunk's joined
    string.
    """
    chunks = []
    current = []  # list of (segment_index, text)
    current_len = 0
    for seg_idx, text in spoken:
        added_len = len(text) + (1 if current else 0)  # +1 for the joining space
        if current and current_len + added_len > max_chars:
            chunks.append(current)
            current, current_len = [], 0
            added_len = len(text)
        current.append((seg_idx, text))
        current_len += added_len
    if current:
        chunks.append(current)

    packed = []
    for chunk in chunks:
        entries = []
        joined = ""
        for seg_idx, text in chunk:
            if joined:
                joined += " "
            start = len(joined)
            joined += text
            end = len(joined)
            entries.append((seg_idx, text, start, end))
        packed.append({"text": joined, "entries": entries})
    return packed


_ELEVENLABS_KEY_EXHAUSTED_MARKERS = (
    "quota_exceeded", "exceeds your quota", "unusual_activity", "unusual activity",
    "free tier usage disabled", "payment_required", "invalid_api_key", "needs_authorization",
)


def _elevenlabs_key_exhausted(exc) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _ELEVENLABS_KEY_EXHAUSTED_MARKERS)


class _ElevenLabsPool:
    """Ordered list of ElevenLabs clients (free account first, then paid).
    advance() moves to the next account when the current one is out of
    credits / blocked, so a video can start on free credits and finish on
    the paid plan with the same voice, without a failed run."""

    def __init__(self, keys):
        self.entries = [(label, ElevenLabs(api_key=key)) for label, key in keys]
        self.i = 0
        self._voice_ids = {}
        self.used = [self.entries[0][0]] if self.entries else []

    @property
    def label(self):
        return self.entries[self.i][0]

    @property
    def client(self):
        return self.entries[self.i][1]

    def voice_id(self) -> str:
        """Resolved per account: the same voice NAME can have a different
        voice_id in a different account's library."""
        global _elevenlabs_voice_id_cache
        if self.label not in self._voice_ids:
            _elevenlabs_voice_id_cache = None
            self._voice_ids[self.label] = _resolve_elevenlabs_voice_id(self.client)
        return self._voice_ids[self.label]

    def advance(self) -> bool:
        if self.i + 1 >= len(self.entries):
            return False
        self.i += 1
        if self.label not in self.used:
            self.used.append(self.label)
        return True


def _elevenlabs_convert_with_timestamps(pool, voice_id, text, previous_text, next_text):
    last_exc = None
    attempt = 1
    while attempt <= ELEVENLABS_MAX_RETRIES:
        try:
            return pool.client.text_to_speech.convert_with_timestamps(
                voice_id=pool.voice_id(),
                text=text,
                model_id=ELEVENLABS_MODEL_ID,
                output_format=ELEVENLABS_OUTPUT_FORMAT,
                previous_text=previous_text,
                next_text=next_text,
            )
        except Exception as exc:
            last_exc = exc
            if _elevenlabs_key_exhausted(exc):
                short = str(exc)[-220:]
                prev = pool.label
                if pool.advance():
                    print(f"[TTS] ElevenLabs '{prev}' account is out of credits / blocked ({short}) - switching to '{pool.label}' account.")
                    continue  # same chunk, next account, attempt not consumed
                print(f"[TTS] ElevenLabs '{prev}' account is out of credits / blocked and no other account is left ({short}).")
                break
            wait = 2 ** attempt
            print(f"[TTS] ElevenLabs chunk attempt {attempt}/{ELEVENLABS_MAX_RETRIES} failed: {exc}")
            if attempt < ELEVENLABS_MAX_RETRIES:
                print(f"[TTS] Retrying in {wait}s...")
                time.sleep(wait)
            attempt += 1
    raise RuntimeError(f"ElevenLabs TTS failed: {last_exc}")


def _generate_synced_narration_elevenlabs(segments: list, clips_dir: Path) -> tuple:
    """The exact-sync path. Returns (slides_with_real_durations,
    clip_paths_in_slide_order). Raises on any failure - this is
    deliberately all-or-nothing: a network blip on chunk 3 of 6 should
    fall back to the old approximate method for the whole video, not
    ship a video that's exactly synced for the first half and guessed
    for the second.
    """
    if not HAS_ELEVENLABS:
        raise RuntimeError("elevenlabs package is not installed.")
    if not ELEVENLABS_KEYS:
        raise RuntimeError("No ElevenLabs API key is set (ELEVENLABS_API_KEY / ELEVENLABS_API_KEY_FREE).")

    pool = _ElevenLabsPool(ELEVENLABS_KEYS)
    print(f"[TTS] ElevenLabs accounts in order: {', '.join(label for label, _ in pool.entries)}.")
    voice_id = pool.voice_id()

    spoken = [(i, text) for i, (kind, text, act) in enumerate(segments) if kind in SPOKEN_SLIDE_KINDS and text.strip()]
    chunks = _pack_spoken_segments_into_chunks(spoken)
    print(f"[TTS] Generating {len(chunks)} ElevenLabs chunk(s) with exact per-slide timestamps (voice_id={voice_id}, model={ELEVENLABS_MODEL_ID})...")

    clips_dir.mkdir(exist_ok=True, parents=True)
    segment_clip = {}  # segment_index -> clip Path

    for c_idx, chunk in enumerate(chunks):
        previous_text = chunks[c_idx - 1]["text"][-500:] if c_idx > 0 else None
        next_text = chunks[c_idx + 1]["text"][:500] if c_idx < len(chunks) - 1 else None
        resp = _elevenlabs_convert_with_timestamps(pool, voice_id, chunk["text"], previous_text, next_text)

        alignment = resp.alignment
        if alignment is None or len(alignment.characters) != len(chunk["text"]):
            raise RuntimeError(
                f"ElevenLabs alignment length mismatch on chunk {c_idx} "
                f"({len(getattr(alignment, 'characters', []) or [])} chars returned, "
                f"{len(chunk['text'])} sent) - can't trust per-slide timing from this chunk."
            )

        chunk_audio_path = clips_dir / f"chunk_{c_idx:03d}.mp3"
        with open(chunk_audio_path, "wb") as f:
            f.write(base64.b64decode(resp.audio_base_64))

        starts = alignment.character_start_times_seconds
        ends = alignment.character_end_times_seconds
        for seg_idx, text, local_start, local_end in chunk["entries"]:
            t0 = starts[local_start]
            t1 = ends[local_end - 1]
            seg_clip = clips_dir / f"seg_{seg_idx:04d}.mp3"
            _extract_audio_range(chunk_audio_path, t0, t1, seg_clip)
            segment_clip[seg_idx] = seg_clip
        print(f"[TTS] Chunk {c_idx + 1}/{len(chunks)} done ({len(chunk['entries'])} slide(s), {len(chunk['text'])} chars).")

    slides, clip_paths = [], []
    for i, (kind, text, act_name) in enumerate(segments):
        if kind in SPOKEN_SLIDE_KINDS and i in segment_clip:
            clip_path = segment_clip[i]
        else:
            clip_path = clips_dir / f"seg_{i:04d}_silence.mp3"
            _generate_silence_clip(STRUCTURAL_SLIDE_DURATIONS.get(kind, 3.0), clip_path)
        duration = _ffprobe_duration(clip_path)
        slides.append((kind, text, duration, act_name))
        clip_paths.append(clip_path)

    print(f"[TTS] ElevenLabs accounts used for this video: {', '.join(pool.used)}.")
    return slides, clip_paths


def _edge_tts_clip(text: str, dest: Path):
    """One edge_tts request for one slide, with retry + backoff. Short
    requests fail fast and only the failing slide is retried - unlike the
    old single ~4,000-word request, where one dropped stream from
    Microsoft's endpoint (NoAudioReceived, run #250) killed the whole run."""
    last_exc = None
    for attempt in range(1, EDGE_TTS_MAX_RETRIES + 1):
        try:
            dest.unlink(missing_ok=True)
            edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE).save_sync(str(dest))
            if dest.exists() and dest.stat().st_size > 500:
                return
            raise RuntimeError("edge_tts wrote an empty file")
        except Exception as exc:
            last_exc = exc
            if attempt < EDGE_TTS_MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                print(f"[TTS] edge_tts attempt {attempt}/{EDGE_TTS_MAX_RETRIES} failed "
                      f"({type(exc).__name__}: {exc}) - retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"edge_tts failed after {EDGE_TTS_MAX_RETRIES} attempts on: "
                       f"{text[:80]!r}... ({type(last_exc).__name__}: {last_exc})")


def _generate_synced_narration_edge_tts(segments: list, clips_dir: Path) -> tuple:
    """Exact-sync edge_tts path: one clip per spoken slide (a few slides in
    parallel), real silence for structural slides, so each slide is on
    screen for exactly as long as its narration takes."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    clips_dir.mkdir(exist_ok=True, parents=True)
    jobs = {}
    for i, (kind, text, act_name) in enumerate(segments):
        if kind in SPOKEN_SLIDE_KINDS and re.search(r"[A-Za-z0-9]", text or ""):
            jobs[i] = clips_dir / f"edge_{i:04d}.mp3"

    print(f"[TTS] edge_tts ({EDGE_TTS_VOICE}, rate {EDGE_TTS_RATE}): {len(jobs)} spoken slide(s), "
          f"{EDGE_TTS_WORKERS} at a time, up to {EDGE_TTS_MAX_RETRIES} attempts each.")
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, EDGE_TTS_WORKERS)) as pool:
        futures = {pool.submit(_edge_tts_clip, segments[i][1], path): i for i, path in jobs.items()}
        for fut in as_completed(futures):
            fut.result()  # re-raise if a slide failed every retry
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"[TTS] edge_tts {done}/{len(jobs)} slides done.")

    # Decode every clip to PCM WAV before measuring/concatenating. MP3
    # frames carry encoder padding, so summing per-clip MP3 durations
    # drifts ~50 ms per slide (~2-3 s by the end of a video); WAV
    # durations are sample-exact, so slides and audio stay locked.
    slides, clip_paths = [], []
    for i, (kind, text, act_name) in enumerate(segments):
        wav = clips_dir / f"edge_{i:04d}.wav"
        if i in jobs:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(jobs[i]), "-ar", str(EDGE_TTS_SAMPLE_RATE), "-ac", "1",
                 "-c:a", "pcm_s16le", str(wav)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            dur = STRUCTURAL_SLIDE_DURATIONS.get(kind, 1.5 if kind in SPOKEN_SLIDE_KINDS else 3.0)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={EDGE_TTS_SAMPLE_RATE}:cl=mono",
                 "-t", f"{dur:.3f}", "-c:a", "pcm_s16le", str(wav)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        slides.append((kind, text, _ffprobe_duration(wav), act_name))
        clip_paths.append(wav)
    return slides, clip_paths


# ---------- Kokoro (default voice since v3.3.0) ----------
# Spoken-text normalization for the TTS engine ONLY (captions and slides
# keep the original spelling). Kokoro's espeak-based phonemizer reads
# DevOps jargon letter-by-letter or wrong ("kubectl" -> "kub-ectle").
_TTS_PRONUNCIATIONS = [
    (r"\bkubectl\b", "kube control"),
    (r"\bk8s\b", "kubernetes"),
    (r"\bK8s\b", "Kubernetes"),
    (r"\bk3s\b", "K three S"),
    (r"\bOOMKilled\b", "O O M killed"),
    (r"\bOOM\b", "O O M"),
    (r"\bCI/CD\b", "C I C D"),
    (r"\bYAML\b", "yammel"),
    (r"\byaml\b", "yammel"),
    (r"\bnginx\b", "engine X"),
    (r"\bNGINX\b", "engine X"),
    (r"\bPostgreSQL\b", "postgres Q L"),
    (r"\bSQL\b", "sequel"),
    (r"\bEKS\b", "E K S"),
    (r"\bAKS\b", "A K S"),
    (r"\bGKE\b", "G K E"),
    (r"\bIAM\b", "I am"),
    (r"\bJSON\b", "jason"),
    (r"\bCLI\b", "C L I"),
    (r"\bSRE\b", "S R E"),
    (r"\bRBAC\b", "R back"),
    (r"\bterraform\.tfstate\b", "terraform dot T F state"),
    (r"\b5xx\b", "five hundreds"),
    (r"\b4xx\b", "four hundreds"),
    (r"\bp99\b", "P ninety-nine"),
    (r"\bAPI\b", "A P I"),
    (r"\bAPIs\b", "A P Is"),
    (r"\bAWS\b", "A W S"),
    (r"\bGCP\b", "G C P"),
    (r"\bVPC\b", "V P C"),
    (r"\bS3\b", "S three"),
    (r"\bEC2\b", "E C two"),
    (r"\bDNS\b", "D N S"),
    (r"\bTLS\b", "T L S"),
    (r"\bCPU\b", "C P U"),
    (r"\bSSH\b", "S S H"),
    (r"\bargocd\b|\bArgoCD\b|\bArgo CD\b", "Argo C D"),
    (r"\bHPA\b", "H P A"),
    (r"\bPDB\b", "P D B"),
    (r"--", " "),
    (r"`", ""),
]


def _tts_normalize(text: str) -> str:
    out = text or ""
    for pat, rep in _TTS_PRONUNCIATIONS:
        out = re.sub(pat, rep, out)
    return re.sub(r"\s+", " ", out).strip()


_KOKORO = None


def _kokoro_engine():
    """Load kokoro-onnx once per run, downloading the model files from the
    kokoro-onnx GitHub release if they are not already cached."""
    global _KOKORO
    if _KOKORO is not None:
        return _KOKORO
    from kokoro_onnx import Kokoro  # imported lazily: optional dependency
    import urllib.request

    KOKORO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in KOKORO_MODEL_URLS.items():
        dest = KOKORO_MODEL_DIR / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            continue
        print(f"[TTS] Downloading Kokoro model file {name} ...")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    _KOKORO = Kokoro(str(KOKORO_MODEL_DIR / "kokoro-v1.0.onnx"), str(KOKORO_MODEL_DIR / "voices-v1.0.bin"))
    return _KOKORO


def _write_wav_pcm16(path: Path, samples, sample_rate: int):
    import wave
    import numpy as np
    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def _generate_synced_narration_kokoro(segments: list, clips_dir: Path) -> tuple:
    """Exact-sync Kokoro path: one WAV per spoken slide + real silence for
    structural slides, same contract as the edge_tts path."""
    engine = _kokoro_engine()
    clips_dir.mkdir(exist_ok=True, parents=True)
    spoken_total = sum(1 for k, t, _ in segments if k in SPOKEN_SLIDE_KINDS and re.search(r"[A-Za-z0-9]", t or ""))
    print(f"[TTS] Kokoro ({KOKORO_VOICE}, speed {KOKORO_SPEED}): {spoken_total} spoken slide(s).")
    slides, clip_paths = [], []
    done = 0
    t0 = time.time()
    for i, (kind, text, act_name) in enumerate(segments):
        wav = clips_dir / f"kokoro_{i:04d}.wav"
        if kind in SPOKEN_SLIDE_KINDS and re.search(r"[A-Za-z0-9]", text or ""):
            samples, sr = engine.create(_tts_normalize(text), voice=KOKORO_VOICE, speed=KOKORO_SPEED, lang="en-us")
            if sr != KOKORO_SAMPLE_RATE:
                raise RuntimeError(f"Kokoro returned {sr} Hz, expected {KOKORO_SAMPLE_RATE}")
            if len(samples) < sr * 0.2:
                raise RuntimeError(f"Kokoro produced almost no audio for slide {i}")
            # a short natural breath between slides
            import numpy as np
            samples = np.concatenate([samples, np.zeros(int(sr * 0.18), dtype="float32")])
            _write_wav_pcm16(wav, samples, sr)
            done += 1
            if done % 10 == 0 or done == spoken_total:
                print(f"[TTS] Kokoro {done}/{spoken_total} slides done ({time.time() - t0:.0f}s).")
        else:
            dur = STRUCTURAL_SLIDE_DURATIONS.get(kind, 1.5 if kind in SPOKEN_SLIDE_KINDS else 3.0)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={KOKORO_SAMPLE_RATE}:cl=mono",
                 "-t", f"{dur:.3f}", "-c:a", "pcm_s16le", str(wav)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        slides.append((kind, text, _ffprobe_duration(wav), act_name))
        clip_paths.append(wav)
    return slides, clip_paths


def _cleanup_dir(d: Path):
    for p in d.glob("*"):
        p.unlink(missing_ok=True)
    try:
        d.rmdir()
    except OSError:
        pass


def generate_synced_narration(script: str, output_mp3: Path) -> tuple:
    """Returns (slides, engine_used) where slides is the final ordered
    [(kind, text, duration, act_name), ...] list build_video() renders,
    and output_mp3 has been written. engine_used reflects what ACTUALLY
    generated the audio for this run, so upload_log.json stays accurate.

    v3.3.0: Kokoro (offline, same male voice every video) is the default.
    ElevenLabs is only tried when TTS_PROVIDER=elevenlabs. Whatever fails,
    edge_tts (also exact-sync) takes over.
    """
    segments = parse_script_to_segments(script)

    if TTS_PROVIDER == "elevenlabs":
        if HAS_ELEVENLABS and ELEVENLABS_KEYS:
            clips_dir = OUTPUT_DIR / "tts_clips"
            try:
                print(f"[TTS] Using ElevenLabs (voice: {ELEVENLABS_VOICE_NAME}) with exact per-slide sync.")
                slides, clip_paths = _generate_synced_narration_elevenlabs(segments, clips_dir)
                _concat_clips(clip_paths, output_mp3)
                return slides, "elevenlabs"
            except Exception as exc:
                print(f"[TTS] ElevenLabs failed: {str(exc)[:400]} - falling back to edge_tts.")
            finally:
                _cleanup_dir(clips_dir)
        else:
            print("[TTS] TTS_PROVIDER=elevenlabs but no key/SDK - using edge_tts.")
    elif TTS_PROVIDER == "kokoro":
        clips_dir = OUTPUT_DIR / "tts_clips_kokoro"
        try:
            slides, clip_paths = _generate_synced_narration_kokoro(segments, clips_dir)
            _concat_clips(clip_paths, output_mp3)
            return slides, "kokoro"
        except Exception as exc:
            print(f"[TTS] Kokoro failed: {type(exc).__name__}: {str(exc)[:400]} - falling back to edge_tts.")
        finally:
            _cleanup_dir(clips_dir)
    else:
        print(f"[TTS] TTS_PROVIDER={TTS_PROVIDER} - using edge_tts.")

    clips_dir = OUTPUT_DIR / "tts_clips_edge"
    try:
        slides, clip_paths = _generate_synced_narration_edge_tts(segments, clips_dir)
        _concat_clips(clip_paths, output_mp3)
    finally:
        _cleanup_dir(clips_dir)
    return slides, "edge_tts"


# ─────────────────────────────────────────
# VIDEO BUILDER — 5-ACT COLOR-CODED SLIDES
# ─────────────────────────────────────────
def _draw_rounded_rect(draw, xy, radius, fill, outline=None, width=2):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)
    if outline:
        draw.arc([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=outline, width=width)
        draw.arc([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=outline, width=width)
        draw.arc([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=outline, width=width)
        draw.arc([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=outline, width=width)
        draw.line([x0 + radius, y0, x1 - radius, y0], fill=outline, width=width)
        draw.line([x0 + radius, y1, x1 - radius, y1], fill=outline, width=width)
        draw.line([x0, y0 + radius, x0, y1 - radius], fill=outline, width=width)
        draw.line([x1, y0 + radius, x1, y1 - radius], fill=outline, width=width)


def _draw_act_structure_diagram(draw, W, H, active_act, fg, muted):
    n = len(ACT_ORDER)
    box_w, box_h = 320, 260
    gap = 24
    total_w = n * box_w + (n - 1) * gap
    x = (W - total_w) // 2
    y = H // 2 - box_h // 2 + 40

    for i, act in enumerate(ACT_ORDER):
        base_color = ACT_COLORS[act]
        is_active = act == active_act
        color = base_color if is_active else tuple(int(c * 0.35) for c in base_color)
        outline = (255, 255, 255) if is_active else None

        _draw_rounded_rect(
            draw,
            [x, y, x + box_w, y + box_h],
            16,
            fill=color,
            outline=outline,
            width=4 if is_active else 0,
        )

        label_font = _get_font(30, bold=True)
        lw = draw.textbbox((0, 0), act, font=label_font)[2]
        draw.text(
            (x + box_w // 2 - lw // 2, y + 20),
            act,
            fill=(255, 255, 255),
            font=label_font,
        )

        sub_lines = textwrap.wrap(ACT_SUBLABELS[act], width=14)
        sy = y + box_h - 20 - len(sub_lines) * 26
        for line in sub_lines:
            sf = _get_font(20)
            sw = draw.textbbox((0, 0), line, font=sf)[2]
            draw.text(
                (x + box_w // 2 - sw // 2, sy),
                line,
                fill=(255, 255, 255),
                font=sf,
            )
            sy += 26

        x += box_w + gap


def _render_slide(kind, text, progress, slide_num, total_slides, W=1920, H=1080, act_name="HOOK"):
    bg = BRAND["bg"]
    surf = BRAND["surface"]
    acc = BRAND["accent"]
    acc2 = BRAND["accent2"]
    acc3 = BRAND["accent3"]
    fg = BRAND["text"]
    muted = BRAND["muted"]
    grid = BRAND["grid"]

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=grid, width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=grid, width=1)

    draw.rectangle([0, 0, W, 64], fill=(12, 18, 34))
    draw.text((28, 18), CHANNEL_NAME, font=_get_font(24, bold=True), fill=acc)
    draw.text((W - 280, 18), CHANNEL_BRAND, font=_get_font(22), fill=muted)

    bar_h = 10
    draw.rectangle([0, H - bar_h, W, H], fill=(25, 32, 60))
    draw.rectangle([0, H - bar_h, int(W * min(progress, 1.0)), H], fill=acc)

    counter = f"{slide_num}/{total_slides}"
    draw.text((W - 120, H - bar_h - 30), counter, font=_get_font(20), fill=muted)

    if kind == "title":
        draw.rectangle([0, 80, 12, H - 20], fill=acc)
        lines = textwrap.wrap(text.upper(), width=26)
        y = (H - len(lines) * 100) // 2
        for line in lines:
            font = _get_font(72, bold=True)
            w_px = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((W - w_px) // 2, y), line, fill=fg, font=font)
            y += 100
        draw.text((80, H - 120), "A full deep dive for DevOps engineers.", font=_get_font(28), fill=muted)

    elif kind == "chapter":
        act_color = ACT_COLORS.get(act_name, acc)
        badge_text = act_name
        bf = _get_font(24, bold=True)
        bw = draw.textbbox((0, 0), badge_text, font=bf)[2]
        _draw_rounded_rect(draw, [80, 100, 80 + bw + 28, 140], 8, fill=act_color)
        draw.text((94, 102), badge_text, font=bf, fill=(255, 255, 255))

        lines = textwrap.wrap(text, width=42)
        y = 170
        for line in lines:
            font = _get_font(48, bold=True)
            draw.text((80, y), line, fill=fg, font=font)
            y += 62
        _draw_act_structure_diagram(draw, W, H, act_name, fg, muted)

    elif kind == "hook":
        draw.rectangle([0, 80, W, 90], fill=acc2)
        draw.text((80, 110), "⚠ THE PROBLEM", font=_get_font(28, bold=True), fill=acc2)
        lines = textwrap.wrap(text, width=60)
        y = 180
        for line in lines[:8]:
            font = _get_font(38, bold=True)
            draw.text((80, y), line, fill=fg, font=font)
            y += 52

    elif kind == "tip":
        _draw_rounded_rect(draw, [60, 90, W - 60, H - 90], 20, fill=(12, 40, 22), outline=acc3, width=3)
        draw.text((100, 120), "💡 THE FIX", font=_get_font(28, bold=True), fill=acc3)
        lines = textwrap.wrap(text, width=62)
        y = 200
        for line in lines[:10]:
            font = _get_font(36)
            draw.text((100, y), line, fill=fg, font=font)
            y += 50

    elif kind in ("body", "stat", "learn", "compare", "recap"):
        lines = textwrap.wrap(text, width=72)
        y = 110
        for line in lines[:16]:
            font = _get_font(34)
            draw.text((80, y), line, fill=fg, font=font)
            y += 48

    elif kind == "cta":
        mid = H // 2
        draw.text((W // 2 - 380, mid - 80), "🔔  LIKE THIS IF IT'S HELPING", font=_get_font(40, bold=True), fill=acc)
        draw.text((W // 2 - 340, mid), "Subscribe — new DevOps video every day", font=_get_font(34), fill=fg)
        draw.text((W // 2 - 200, mid + 60), CHANNEL_URL, font=_get_font(26), fill=muted)

    elif kind == "outro":
        draw.rectangle([0, 80, W, 90], fill=acc)
        lines = textwrap.wrap(text, width=36)
        y = (H - len(lines) * 80) // 2
        for line in lines:
            font = _get_font(58, bold=True)
            w_px = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((W - w_px) // 2, y), line, fill=fg, font=font)
            y += 80
        draw.text((W // 2 - 260, H - 160), f"See you tomorrow  |  {CHANNEL_NAME}", font=_get_font(30), fill=muted)

    return img


# ─────────────────────────────────────────
# SLIDES — REAL .PPTX DECK (source of truth) + LIBREOFFICE RASTERIZER
# ─────────────────────────────────────────
# The block above (_render_slide, _draw_rounded_rect,
# _draw_act_structure_diagram) renders slides straight to PNG with
# Pillow. That's now only the LAST-RESORT fallback path (see
# build_video()) if the pptx pipeline below can't run in this
# environment. The primary path builds an actual, human-editable
# PowerPoint file per video with python-pptx, then rasterizes each
# slide to a PNG frame with LibreOffice + poppler so the existing Ken
# Burns / crossfade motion pipeline can use it exactly like before.
#
# Coordinates below reuse the same 1920x1080 layout the PIL renderer
# used. PPTX_RENDER_DPI (144) is chosen so the pptx's 13.333in x 7.5in
# 16:9 slide rasterizes to exactly 1920x1080px, so pixel positions from
# the PIL design translate 1:1 via _px_x()/_px_y(), and font sizes
# translate via _px_pt() (144 DPI = 2px per point, so pt = px / 2).
# ─────────────────────────────────────────
# CINEMATIC VISUAL ENGINE (v3.2.0) - code-drawn "dark cinematic tech" art
# ─────────────────────────────────────────
# Every slide = ONE background picture drawn with Pillow (gradient + glow +
# perspective floor + glass cards + icons + server rack / dashboard /
# terminal mockups) + EDITABLE python-pptx text on top. No stock photos,
# no external services, nothing to fail on the network: if anything in
# here raises, build_slide_deck() falls back to the classic slide for
# that one slide (and the PIL renderer is still the last resort).
#
# Benefit slides for a US audience (all spoken, so the video never sits
# in silence): "stat" (verified U.S. BLS career numbers), "learn"
# (what you'll learn), "compare" (before / after), "recap" (do this today).
import math
import random
from PIL import ImageChops, ImageFilter

VISUALS_STYLE = os.environ.get("VISUALS_STYLE", "cinematic").strip().lower()
VIS_W, VIS_H = 1920, 1080
VIS_ART_DIR = OUTPUT_DIR / "art"
PURPLE = (150, 90, 255)
SOFT_TEXT = (205, 216, 238)

NEW_SPOKEN_KINDS = {"stat", "learn", "compare", "recap"}

# Verified U.S. Bureau of Labor Statistics figures (Occupational Outlook
# Handbook, May 2025 wage data; projections 2025-2035). Re-check yearly
# (BLS publishes new wage data every spring) - see SETUP_NOTES.md.
BLS_SOURCE = "Source: U.S. Bureau of Labor Statistics, Occupational Outlook Handbook (May 2025 wages)"
BLS_STATS = {
    "dev": {"role": "software developers", "short": "Software developers", "pay": 135980, "growth": None},
    "sec": {"role": "information security analysts", "short": "Info security analysts", "pay": 129180, "growth": 21},
    "net": {"role": "network and computer systems administrators", "short": "Network & systems admins", "pay": 99130, "growth": None},
}

# topic category -> keyword regexes, checked in this priority order
_VIS_CATEGORIES = [
    ("security", r"security|rbac|secret|devsecops|vulnerab|zero trust|compliance"),
    ("cost", r"\bcost\b|finops|cloud bill|optimi[sz]"),
    ("ai", r"\bai\b|copilot|chatgpt|claude|aiops|\bllm\b|gpt|agent"),
    ("iac", r"terraform|crossplane|infrastructure as code|\biac\b|ansible"),
    ("k8s", r"kubernetes|\bk8s\b|\bk3s\b|helm|kustomize|kubectl|\bpod|cluster|gitops|statefulset|ingress|gateway"),
    ("cicd", r"ci/cd|cicd|github actions|pipeline|jenkins|deploy"),
    ("obs", r"monitor|observab|prometheus|grafana|incident|\bsre\b|on-call|logging"),
    ("career", r"career|junior|salary|interview|roadmap|future of devops|is devops dead"),
]

_VIS_CATEGORY_DATA = {
    "k8s": {
        "recap": ['Move your manifests or Helm charts into Git and review every change by pull request.', 'Run a dry run before every deploy so surprises show up early.', 'Write a one-page rollback runbook for your most important service.'],
        "before": ["Hand-edited YAML and one-off kubectl fixes", "Config drift nobody can explain", "Late-night pages after a bad rollout", "Know-how stuck in one engineer's head"],
        "after": ["Declarative config reviewed in Git", "Every cluster matches the repo", "Safe rollouts with fast rollbacks", "Runbooks the whole team can follow"],
        "trap": "The Kubernetes mistakes that waste time and money",
        "term": [("cmd", "kubectl get pods"), ("out", "NAME        READY   STATUS"), ("ok", "web-7f9c    1/1     Running"), ("ok", "api-5d2b    1/1     Running"), ("cmd", "kubectl rollout status deploy/web"), ("ok", "successfully rolled out")],
    },
    "iac": {
        "recap": ['Pick one manually built resource and recreate it as code.', 'Run a plan and review the diff before every apply.', 'Store your state remotely and lock it, so two people never collide.'],
        "before": ["Click-ops in the cloud console", "Environments that quietly differ", "No record of who changed what", "Rebuilding by hand after an outage"],
        "after": ["Infrastructure defined as code", "Identical dev, staging and prod", "Every change reviewed and versioned", "Rebuild an environment on demand"],
        "trap": "The infrastructure-as-code traps teams fall into",
        "term": [("cmd", "terraform plan"), ("out", "Plan: 3 to add, 0 to change, 0 to destroy"), ("cmd", "terraform apply"), ("ok", "Apply complete! Resources: 3 added"), ("ok", "state saved to remote backend")],
    },
    "cicd": {
        "recap": ['Make every push run your build and tests automatically.', 'Add one security scan to your pipeline this week.', 'Practice a rollback, so it is boring when it matters.'],
        "before": ["Manual deploys on a Friday evening", "Tests run only when someone remembers", "Rollbacks done in a panic", "Releases that need a whole meeting"],
        "after": ["Every push builds and tests itself", "Deploys are boring and repeatable", "One-click rollback to a good build", "Ship small changes with confidence"],
        "trap": "The pipeline mistakes that slow every release",
        "term": [("cmd", "git push origin main"), ("ok", "build passed"), ("ok", "tests passed"), ("ok", "security scan clean"), ("ok", "deployed to production")],
    },
    "security": {
        "recap": ['List who has admin access today and remove what is not needed.', 'Move one secret out of a config file and into a vault.', 'Turn on audit logs and review them once this week.'],
        "before": ["Shared admin access for everyone", "Secrets pasted into config files", "Audits that mean weeks of scrambling", "Finding out about a breach from a customer"],
        "after": ["Least-privilege access by default", "Secrets in a proper vault", "Audit trails generated automatically", "Issues caught before they ship"],
        "trap": "The security gaps hiding in everyday setups",
        "term": [("cmd", "kubectl auth can-i list secrets"), ("out", "no"), ("cmd", "kubectl auth can-i get pods"), ("ok", "yes"), ("ok", "least privilege verified")],
    },
    "ai": {
        "recap": ['Pick one repetitive task and ask an AI assistant to draft it.', 'Review and test everything it writes before you merge.', 'Never paste secrets or customer data into a prompt.'],
        "before": ["Googling every error message", "Writing boilerplate config by hand", "Reviews that miss obvious flaws", "Hours lost on repetitive toil"],
        "after": ["An AI pair-programmer explains the error", "Drafts generated, then reviewed by you", "Automated checks catch flaws early", "Your time goes to design decisions"],
        "trap": "The mistakes people make when they trust AI blindly",
        "term": [("cmd", "Explain this error and suggest a fix"), ("ok", "root cause identified"), ("ok", "fix drafted for your review"), ("out", "you review, test and approve"), ("ok", "merged")],
    },
    "cost": {
        "recap": ['Open your cloud bill and find your three biggest line items.', 'Right-size one oversized workload using real usage data.', 'Set a budget alert so surprises reach you early.'],
        "before": ["Surprise cloud bills at month end", "Oversized resources nobody revisits", "Idle environments running all weekend", "No idea which team spends what"],
        "after": ["Right-sized workloads with real data", "Idle resources shut down automatically", "Spend visible per team and service", "Savings you can show in a review"],
        "trap": "The hidden costs quietly inflating your bill",
        "term": [("cmd", "kubectl top pods"), ("out", "NAME        CPU    MEMORY"), ("out", "web-7f9c    35m    210Mi"), ("ok", "requests tuned to real usage"), ("ok", "idle nodes removed")],
    },
    "obs": {
        "recap": ['Review your noisiest alert and fix it or delete it.', 'Add one dashboard that shows user-facing errors.', 'Write down the cause and the fix after your next incident.'],
        "before": ["Alerts that nobody trusts", "Guessing at the cause during an outage", "Logs scattered across ten tools", "The same incident, again and again"],
        "after": ["Alerts tied to real user impact", "Dashboards that show the cause fast", "One place to search every signal", "Post-incident fixes that stick"],
        "trap": "The monitoring mistakes that hide real problems",
        "term": [("cmd", "promtool check rules alerts.yml"), ("ok", "SUCCESS: 12 rules found"), ("out", "error rate  0.2%"), ("ok", "SLO healthy"), ("ok", "on-call: quiet night")],
    },
    "career": {
        "recap": ['Choose one skill from this video and build a small project with it.', 'Put it on GitHub with a clear README.', 'Add it to your resume and LinkedIn this week.'],
        "before": ["Learning random tools with no plan", "Tutorials but no real projects", "Unsure what employers want", "Waiting to feel ready"],
        "after": ["A clear skills roadmap", "Real projects you can show", "Skills matched to U.S. job posts", "Momentum from shipping weekly"],
        "trap": "The career mistakes that slow engineers down",
        "term": [("cmd", "git commit -m \"add project to portfolio\""), ("ok", "1 file changed"), ("cmd", "git push origin main"), ("ok", "portfolio updated")],
    },
    "general": {
        "recap": ['Pick one real task at work and apply this today.', 'Write down what you changed and why.', 'Share it with a teammate and ask for feedback.'],
        "before": ["Fixing problems by hand, one at a time", "Knowledge that lives in people's heads", "Surprises in production", "Hours lost on repetitive work"],
        "after": ["Repeatable, automated workflows", "Everything documented and in Git", "Problems caught before production", "Time freed for higher-value work"],
        "trap": "The mistakes that waste time and money",
        "term": [("cmd", "git commit -m \"automate the boring part\""), ("ok", "1 file changed"), ("cmd", "git push origin main"), ("ok", "checks passed"), ("ok", "deployed")],
    },
}

_VISUAL_CTX = {}


def _vis_category(topic: str) -> str:
    t = topic.lower()
    for name, pattern in _VIS_CATEGORIES:
        if re.search(pattern, t):
            return name
    return "general"


def _short_phrase(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "..."


def set_visual_context(topic: str, day_num: int, next_topic: str = ""):
    """Called from main() before narration is generated. Without it (or with
    VISUALS_STYLE=classic) the old slide design/slide list is used."""
    _VISUAL_CTX.clear()
    if VISUALS_STYLE != "cinematic" or not topic:
        return
    _VISUAL_CTX.update({"topic": topic, "day": day_num, "next_topic": next_topic})


def _usd(n: int) -> str:
    return f"${n:,.0f}"


def build_visual_plan(topic: str, day_num: int, segments: list) -> dict:
    """Everything the 4 benefit slides show AND say, derived from the topic
    and the real script - no invented numbers (stats are the verified BLS
    figures above; before/after lines are qualitative)."""
    core = _short_phrase(re.split(r"\s[—–-]\s|\?|:", topic)[0].strip() or topic, 58)
    cat = _vis_category(topic)
    data = _VIS_CATEGORY_DATA[cat]
    stat_key = "sec" if cat == "security" else "dev"
    stat = BLS_STATS[stat_key]

    recap = list(data["recap"])

    learn = [
        ("The core idea", f"What {core} really means, in plain English"),
        ("Avoid the traps", data["trap"]),
        ("Apply it this week", "A step-by-step plan you can use at work"),
    ]

    pay = _usd(stat["pay"])
    stat_narr = (
        f"Here is why this matters for your career. The U.S. Bureau of Labor Statistics reports a median pay of "
        f"{pay} a year for {stat['role']} in America, as of May 2025."
    )
    if stat.get("growth"):
        stat_narr += f" And the field is projected to grow {stat['growth']} percent over the next decade."
    stat_narr += f" Learning {core} properly is one way to start building toward that."

    b, a = data["before"], data["after"]
    return {
        "topic": topic, "core": core, "category": cat, "day": day_num,
        "stat_key": stat_key, "stat": stat, "learn": learn, "recap": recap,
        "before": b, "after": a, "term": data["term"],
        "narr": {
            "stat": stat_narr,
            "learn": (
                f"By the end of this video you will know three things. First, what {core} really means, without the jargon. "
                f"Second, {data['trap'].lower().replace('the ', 'the ', 1)}. Third, how to apply it at work this week."
            ),
            "compare": (
                f"Before and after. The manual way: {b[0].lower()}, and {b[1].lower()}. "
                f"The smart way: {a[0].lower()}, and {a[1].lower()}."
            ),
            "recap": (
                "Quick recap. Do these three things today. "
                + " ".join(f"{n}. {r}" for n, r in zip(("One", "Two", "Three"), recap))
            ),
        },
    }


def _insert_benefit_slides(segments: list, plan: dict) -> list:
    """segments is the classic [(kind, text, act), ...] list. Adds compare
    right after the ACT 2 chapter card, stat right after the ACT 3 card,
    recap before the final CTA."""
    segs = list(segments)
    if len(segs) < 6:
        return segs
    # v3.2.0: nothing is inserted in the opening any more - the old
    # "stat" (salary) + "learn" (agenda) pair added ~25s of preamble right
    # where analytics show viewers leave. "learn" is dropped entirely;
    # "stat" moves to the start of ACT 3 as a motivation beat.
    out = []
    act2_chapter = next((i for i, s in enumerate(segs) if s[0] == "chapter" and s[2] == "ACT 2"), None)
    act3_chapter = next((i for i, s in enumerate(segs) if s[0] == "chapter" and s[2] == "ACT 3"), None)
    recap_at = max(1, len(segs) - 2)  # before the final cta + outro
    for i, seg in enumerate(segs):
        if i == recap_at:
            out.append(("recap", plan["narr"]["recap"], "ACT 3"))
        out.append(seg)
        if act2_chapter is not None and i == act2_chapter:
            out.append(("compare", plan["narr"]["compare"], "ACT 2"))
        if act3_chapter is not None and i == act3_chapter:
            out.append(("stat", plan["narr"]["stat"], "ACT 3"))
    return out


# ---------- text fitting (measured with DejaVu = the widest common fallback) ----------
def _wrap_lines(text: str, font, max_w: float) -> list:
    lines, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit_single(text: str, w: float, h: float, max_px: int, min_px: int = 22, bold: bool = True, lh: float = 1.22) -> int:
    for size in range(max_px, min_px - 1, -2):
        font = _get_font(size, bold)
        if len(_wrap_lines(text, font, w)) * size * lh <= h:
            return size
    return min_px


def _fit_paras(paras: list, w: float, h: float, lh: float = 1.22) -> list:
    """paras = [{"text","size","bold","color","after"}]; returns the same
    list with sizes scaled down together until everything fits in w x h."""
    for scale in [1.0 - 0.04 * k for k in range(0, 15)]:
        total = 0.0
        sized = []
        for p in paras:
            size = max(20, int(p["size"] * scale))
            n = len(_wrap_lines(p["text"], _get_font(size, p.get("bold", False)), w))
            total += n * size * lh + p.get("after", 0)
            sized.append({**p, "size": size})
        if total <= h:
            return sized
    return [{**p, "size": max(20, int(p["size"] * 0.55))} for p in paras]


# ---------- Pillow art primitives ----------
class _AD:
    """ImageDraw wrapper that alpha-BLENDS translucent fills/outlines. Plain
    ImageDraw on an RGBA image overwrites pixels instead of blending, which
    turned every translucent tile and track solid white."""

    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    @staticmethod
    def _translucent(kw):
        for key in ("fill", "outline"):
            v = kw.get(key)
            if isinstance(v, tuple) and len(v) == 4 and v[3] < 255:
                return True
        return False

    def __getattr__(self, name):
        fn = getattr(self.d, name)

        def call(*args, **kw):
            if self._translucent(kw):
                layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
                getattr(ImageDraw.Draw(layer), name)(*args, **kw)
                self.img.alpha_composite(layer)
                return None
            return fn(*args, **kw)

        return call


def _vis_bg(glows, seed=0, floor=True, particles=70):
    W, H = VIS_W, VIS_H
    grad = Image.linear_gradient("L").resize((W, H), Image.BILINEAR)
    img = Image.composite(Image.new("RGB", (W, H), (11, 17, 38)), Image.new("RGB", (W, H), (4, 7, 16)), grad)
    qw, qh = W // 4, H // 4
    glow = Image.new("RGB", (qw, qh), (0, 0, 0))
    for col, x, y, r, s in glows:
        layer = Image.new("RGB", (qw, qh), (0, 0, 0))
        ImageDraw.Draw(layer).ellipse([(x - r) / 4, (y - r) / 4, (x + r) / 4, (y + r) / 4], fill=tuple(int(c * s) for c in col))
        glow = ImageChops.add(glow, layer.filter(ImageFilter.GaussianBlur(max(2, r / 4 * 0.6))))
    img = ImageChops.add(img, glow.resize((W, H), Image.BICUBIC)).convert("RGBA")

    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    if floor:
        horizon = int(H * 0.74)
        for i in range(1, 15):
            t = (i / 14) ** 2.2
            y = horizon + int((H - horizon) * t)
            d.line([(0, y), (W, y)], fill=(40, 120, 200, int(10 + 40 * t)), width=1)
        for k in range(-14, 15):
            d.line([(W // 2 + k * 16, horizon), (W // 2 + k * 190, H)], fill=(40, 120, 200, 26), width=1)
    rnd = random.Random(seed)
    for _ in range(particles):
        x, y, r = rnd.randint(0, W), rnd.randint(70, int(H * 0.85)), rnd.choice((1, 1, 2, 2, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(160, 210, 255, rnd.randint(25, 90)))
    img.alpha_composite(over)

    vm = Image.new("L", (240, 135), 255)
    ImageDraw.Draw(vm).ellipse([-30, -22, 270, 157], fill=0)
    vm = vm.filter(ImageFilter.GaussianBlur(26)).resize((W, H), Image.BICUBIC)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vm.point(lambda p: int(p * 0.55)))
    img.alpha_composite(dark)

    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    bd.rectangle([0, 0, W, 64], fill=(7, 11, 24, 235))
    bd.rectangle([0, 63, W, 65], fill=(0, 190, 255, 90))
    img.alpha_composite(bar)
    return img


def _glow_layer(size, draw_fn, blur):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _glass(img, box, r=26, glow=None, base=(9, 15, 34, 215), border=(120, 180, 255, 70)):
    if glow:
        img.alpha_composite(_glow_layer(img.size, lambda d: d.rounded_rectangle(box, r, outline=(*glow, 230), width=7), 14))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, r, fill=base, outline=border, width=2)
    x0, y0, x1, _ = box
    d.line([(x0 + r, y0 + 2), (x1 - r, y0 + 2)], fill=(255, 255, 255, 38), width=2)
    img.alpha_composite(layer)


def _icon(name, size, color):
    S = 4
    n = size * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (*color, 255)
    dark = (6, 10, 22, 255)

    def P(*pts):
        return [(x * n, y * n) for x, y in pts]

    if name == "warning":
        d.polygon(P((.5, .07), (.96, .9), (.04, .9)), fill=c)
        d.rounded_rectangle(P((.45, .36), (.55, .65)), 10, fill=dark)
        d.ellipse(P((.45, .72), (.55, .82)), fill=dark)
    elif name in ("check", "cross"):
        d.ellipse(P((.04, .04), (.96, .96)), fill=c)
        if name == "check":
            d.line(P((.27, .52), (.44, .69), (.74, .33)), fill=dark, width=int(.1 * n), joint="curve")
        else:
            d.line(P((.3, .3), (.7, .7)), fill=dark, width=int(.1 * n))
            d.line(P((.7, .3), (.3, .7)), fill=dark, width=int(.1 * n))
    elif name == "bolt":
        d.polygon(P((.6, .04), (.2, .56), (.46, .56), (.36, .96), (.82, .4), (.54, .4)), fill=c)
    elif name == "shield":
        d.polygon(P((.5, .04), (.9, .18), (.86, .58), (.5, .96), (.14, .58), (.1, .18)), fill=c)
        d.line(P((.3, .5), (.45, .65), (.72, .33)), fill=dark, width=int(.09 * n), joint="curve")
    elif name == "gear":
        for k in range(8):
            a = k * math.pi / 4
            cx, cy, rr = .5, .5, .44
            pts = []
            for da, rad in ((-.17, rr * .78), (-.17, rr), (.17, rr), (.17, rr * .78)):
                pts.append((cx + rad * math.cos(a + da), cy + rad * math.sin(a + da)))
            d.polygon(P(*pts), fill=c)
        d.ellipse(P((.18, .18), (.82, .82)), fill=c)
        d.ellipse(P((.36, .36), (.64, .64)), fill=(0, 0, 0, 0))
    elif name == "chart":
        for x0, top in ((.12, .55), (.4, .3), (.68, .1)):
            d.rounded_rectangle(P((x0, top), (x0 + .2, .9)), 8, fill=c)
    elif name == "cloud":
        d.ellipse(P((.1, .4), (.5, .8)), fill=c)
        d.ellipse(P((.3, .2), (.7, .7)), fill=c)
        d.ellipse(P((.5, .35), (.92, .8)), fill=c)
        d.rectangle(P((.28, .55), (.72, .8)), fill=c)
    elif name == "rocket":
        d.polygon(P((.5, .04), (.7, .3), (.7, .72), (.3, .72), (.3, .3)), fill=c)
        d.polygon(P((.3, .5), (.1, .8), (.3, .72)), fill=c)
        d.polygon(P((.7, .5), (.9, .8), (.7, .72)), fill=c)
        d.polygon(P((.4, .74), (.6, .74), (.5, .98)), fill=(255, 170, 40, 255))
        d.ellipse(P((.4, .3), (.6, .5)), fill=dark)
    elif name == "clock":
        d.ellipse(P((.06, .06), (.94, .94)), outline=c, width=int(.08 * n))
        d.line(P((.5, .5), (.5, .24)), fill=c, width=int(.07 * n))
        d.line(P((.5, .5), (.7, .6)), fill=c, width=int(.07 * n))
    elif name == "dollar":
        d.ellipse(P((.04, .04), (.96, .96)), fill=c)
        f = _get_font(int(n * .62), True)
        d.text((n / 2, n / 2), "$", font=f, fill=dark, anchor="mm")
    elif name == "lock":
        d.rounded_rectangle(P((.18, .44), (.82, .94)), 16, fill=c)
        d.arc(P((.3, .08), (.7, .8)), 180, 360, fill=c, width=int(.09 * n))
        d.ellipse(P((.44, .62), (.56, .74)), fill=dark)
    elif name == "bell":
        d.polygon(P((.22, .72), (.78, .72), (.7, .55), (.7, .38), (.3, .38), (.3, .55)), fill=c)
        d.ellipse(P((.3, .12), (.7, .6)), fill=c)
        d.ellipse(P((.42, .74), (.58, .9)), fill=c)
    elif name == "play":
        d.polygon(P((.3, .2), (.3, .8), (.82, .5)), fill=c)
    elif name == "target":
        d.ellipse(P((.05, .05), (.95, .95)), outline=c, width=int(.07 * n))
        d.ellipse(P((.27, .27), (.73, .73)), outline=c, width=int(.07 * n))
        d.ellipse(P((.44, .44), (.56, .56)), fill=c)
    elif name == "server":
        for k in range(3):
            y0 = .08 + k * .31
            d.rounded_rectangle(P((.08, y0), (.92, y0 + .24)), 10, fill=c)
            d.ellipse(P((.18, y0 + .08), (.26, y0 + .16)), fill=dark)
    return im.resize((size, size), Image.LANCZOS)


def _paste_icon(img, name, x, y, size, color, glow=True):
    ic = _icon(name, size, color)
    if glow:
        halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
        halo.paste(ic, (int(x), int(y)), ic)
        a = halo.split()[3].filter(ImageFilter.GaussianBlur(size * 0.28))
        tinted = Image.new("RGBA", img.size, (*color, 0))
        tinted.putalpha(a.point(lambda p: min(255, int(p * 1.6))))
        img.alpha_composite(tinted)
    img.alpha_composite(ic, (int(x), int(y)))


def _art_rack(img, x, y, w, h, accent=(0, 190, 255), seed=3):
    rnd = random.Random(seed)
    _glass(img, (x, y, x + w, y + h), r=22, glow=accent, base=(8, 13, 30, 235))
    units = 8
    uh = (h - 44) / units
    led = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(led)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(units):
        y0 = y + 22 + i * uh + 4
        y1 = y0 + uh - 9
        d.rounded_rectangle([x + 18, y0, x + w - 18, y1], 8, fill=(17, 25, 50, 255), outline=(48, 72, 122, 255), width=2)
        for s in range(4):
            sx = x + 120 + s * 62
            d.rounded_rectangle([sx, y0 + 12, sx + 46, y1 - 12], 4, fill=(10, 16, 34, 255), outline=(36, 56, 100, 255))
        for k in range(3):
            cx = x + 40 + k * 22
            cy = (y0 + y1) / 2
            col = rnd.choice(((80, 255, 140), (0, 200, 255), (80, 255, 140), (255, 190, 60)))
            ld.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(*col, 255))
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(*col, 255))
        for v in range(5):
            vx = x + w - 120 + v * 16
            d.line([(vx, y0 + 12), (vx, y1 - 12)], fill=(36, 54, 96, 255), width=3)
    img.alpha_composite(layer)
    img.alpha_composite(led.filter(ImageFilter.GaussianBlur(9)))


def _chart_points(rnd, n, theme):
    pts = []
    v = 0.55
    for i in range(n):
        if theme == "alert":
            v = 0.62 + rnd.uniform(-0.05, 0.05) if i < n - 4 else min(0.97, 0.62 + (i - (n - 5)) * 0.1)
        elif theme == "ok":
            v = 0.3 + i / n * 0.45 + rnd.uniform(-0.05, 0.05)
        else:
            v = 0.5 + 0.22 * math.sin(i / 2.3) + rnd.uniform(-0.05, 0.05)
        pts.append(max(0.08, min(0.97, v)))
    return pts


def _art_dashboard(img, box, theme="neutral", seed=5):
    col = {"alert": (255, 80, 80), "ok": (80, 255, 140), "neutral": (0, 190, 255)}[theme]
    x0, y0, x1, y1 = box
    _glass(img, box, glow=col)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for k, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([x0 + 26 + k * 26, y0 + 22, x0 + 40 + k * 26, y0 + 36], fill=(*c, 255))
    d.rounded_rectangle([x0 + 130, y0 + 24, x0 + 330, y0 + 34], 5, fill=(255, 255, 255, 40))
    cx0, cy0, cx1, cy1 = x0 + 36, y0 + 70, x1 - 36, y0 + (y1 - y0) * 0.66
    for g in range(5):
        gy = cy0 + (cy1 - cy0) * g / 4
        d.line([(cx0, gy), (cx1, gy)], fill=(255, 255, 255, 22), width=1)
    rnd = random.Random(seed)
    pts = _chart_points(rnd, 22, theme)
    xy = [(cx0 + (cx1 - cx0) * i / (len(pts) - 1), cy1 - (cy1 - cy0) * v) for i, v in enumerate(pts)]
    d.polygon(xy + [(cx1, cy1), (cx0, cy1)], fill=(*col, 46))
    img.alpha_composite(layer)
    img.alpha_composite(_glow_layer(img.size, lambda dd: dd.line(xy, fill=(*col, 255), width=9, joint="curve"), 9))
    ld = _AD(img)
    ld.line(xy, fill=(*col, 255), width=5, joint="curve")
    ex, ey = xy[-1]
    ld.ellipse([ex - 9, ey - 9, ex + 9, ey + 9], fill=(255, 255, 255, 255), outline=(*col, 255), width=4)
    ty0 = cy1 + 34
    tw = (x1 - x0 - 72 - 40) / 3
    for k in range(3):
        tx = x0 + 36 + k * (tw + 20)
        ld.rounded_rectangle([tx, ty0, tx + tw, y1 - 34], 14, fill=(255, 255, 255, 14), outline=(255, 255, 255, 36), width=1)
        bh = (y1 - 34 - ty0 - 36)
        for b in range(4):
            hh = bh * rnd.uniform(0.25, 0.95) if not (theme == "alert" and k == 2) else bh * (0.4 + 0.18 * b)
            bx = tx + 18 + b * ((tw - 36) / 4)
            ld.rounded_rectangle([bx, y1 - 52 - hh, bx + (tw - 36) / 4 - 8, y1 - 52], 5, fill=(*col, 190 if b == 3 else 110))


def _art_terminal(img, box, lines, theme="neutral", font_size=30):
    col = {"alert": (255, 80, 80), "ok": (80, 255, 140), "neutral": (0, 190, 255)}[theme]
    x0, y0, x1, y1 = box
    _glass(img, box, glow=col, base=(5, 9, 20, 235))
    d = _AD(img)
    for k, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([x0 + 26 + k * 26, y0 + 22, x0 + 40 + k * 26, y0 + 36], fill=(*c, 255))
    d.line([(x0 + 2, y0 + 58), (x1 - 2, y0 + 58)], fill=(255, 255, 255, 28), width=1)
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    try:
        font = ImageFont.truetype(mono, font_size)
    except Exception:
        font = _get_font(font_size)
    y = y0 + 84
    max_w = (x1 - x0) - 70
    for kind, text in lines:
        if y > y1 - font_size - 24:
            break
        if kind == "cmd":
            prefix, pc, tc = "$ ", (0, 190, 255), (235, 240, 255)
        elif kind == "ok":
            prefix, pc, tc = "✔ ", (80, 255, 140), (180, 240, 205)
        elif kind == "err":
            prefix, pc, tc = "✖ ", (255, 90, 90), (255, 190, 190)
        else:
            prefix, pc, tc = "  ", (130, 145, 180), (150, 165, 200)
        shown = text
        while font.getlength(prefix + shown) > max_w and len(shown) > 8:
            shown = shown[:-2]
        d.text((x0 + 34, y), prefix, font=font, fill=(*pc, 255))
        d.text((x0 + 34 + font.getlength(prefix), y), shown, font=font, fill=(*tc, 255))
        y += int(font_size * 1.55)
    if y < y1 - font_size - 10:
        d.rectangle([x0 + 34, y + 2, x0 + 34 + font_size * 0.6, y + font_size], fill=(*col, 230))


# ---------- v3.3.0: real terminal scenes (static + typing animation) ----------
_TERMINAL_RENDER = {}  # slide index -> {"base": RGB image without lines, "box": ..., "lines": ...}
TERM_FONT_SIZE = 30
_TERM_ERR_RE = re.compile(r"error|failed|fail\b|crashloopbackoff|oomkilled|denied|refused|timed? ?out|evicted|backoff|fatal|panic|exit code: ?[1-9]|unhealthy|forbidden|not found|5\d\d\b", re.I)
_TERM_OK_RE = re.compile(r"\brunning\b|\bready\b|success|succeeded|healthy|\bok\b|created|configured|applied|rolled out|synced|passed|complete", re.I)


def _term_fonts(size=TERM_FONT_SIZE):
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    mono_b = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    try:
        return ImageFont.truetype(mono, size), ImageFont.truetype(mono_b, size)
    except Exception:
        f = _get_font(size)
        return f, _get_font(size, bold=True)


def _term_fit(text: str, font, max_w: float) -> str:
    if font.getlength(text) <= max_w:
        return text
    while text and font.getlength(text + "…") > max_w:
        text = text[:-1]
    return text + "…"


def _draw_terminal_lines(img, box, lines, reveal=None, cursor=True):
    """Draw terminal lines inside box. reveal=(line_idx, n_chars) shows lines
    before line_idx fully and n_chars of line line_idx (typing state);
    reveal=None shows everything (final state)."""
    x0, y0, x1, y1 = box
    font, font_b = _term_fonts()
    d = ImageDraw.Draw(img)
    lh = int(TERM_FONT_SIZE * 1.5)
    max_w = (x1 - x0) - 90
    y = y0 + 92
    last_xy = None
    upto = len(lines) if reveal is None else min(reveal[0] + 1, len(lines))
    for i in range(upto):
        kind, text = lines[i]
        if y > y1 - lh:
            break
        partial = reveal is not None and i == reveal[0]
        if kind == "cmd":
            shown = _term_fit(text, font_b, max_w - font.getlength("$ "))
            if partial:
                shown = shown[: reveal[1]]
            d.text((x0 + 40, y), "$", font=font_b, fill=(0, 200, 255))
            d.text((x0 + 40 + font.getlength("$ "), y), shown, font=font_b, fill=(240, 245, 255))
            last_xy = (x0 + 40 + font.getlength("$ ") + font_b.getlength(shown), y)
        else:
            if partial and reveal[1] == 0:
                break
            shown = _term_fit(text, font, max_w)
            col = (255, 125, 125) if _TERM_ERR_RE.search(text) else (130, 235, 165) if _TERM_OK_RE.search(text) else (178, 192, 222)
            d.text((x0 + 40, y), shown, font=font, fill=col)
            last_xy = (x0 + 40 + font.getlength(shown), y)
        y += lh
    if cursor:
        if reveal is None or (last_xy is None):
            cx, cy = x0 + 40, (y if reveal is None else y0 + 92)
            if reveal is None:
                d.text((cx, cy), "$", font=font_b, fill=(0, 200, 255))
                cx += font.getlength("$ ")
        else:
            cx, cy = last_xy[0] + 4, last_xy[1]
        if cy < y1 - lh:
            d.rectangle([cx, cy + 4, cx + TERM_FONT_SIZE * 0.55, cy + TERM_FONT_SIZE + 2], fill=(0, 200, 255))


def _terminal_window(img, box, title="bash — production"):
    x0, y0, x1, y1 = box
    _glass(img, box, r=22, glow=(0, 190, 255), base=(4, 8, 18, 245), border=(0, 190, 255, 120))
    d = _AD(img)
    for k, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([x0 + 26 + k * 30, y0 + 22, x0 + 44 + k * 30, y0 + 40], fill=(*c, 255))
    d.line([(x0 + 2, y0 + 62), (x1 - 2, y0 + 62)], fill=(255, 255, 255, 30), width=1)
    font, _ = _term_fonts(24)
    tw = font.getlength(title)
    d.text(((x0 + x1 - tw) / 2, y0 + 18), title, font=font, fill=(150, 165, 200, 255))


def _terminal_typing_timeline(lines, max_time: float):
    """[(t, (line_idx, n_chars)), ...] keyframes of the typing animation and
    the time the final state is reached. Commands type at ~30 chars/s,
    output lines print almost instantly, like a real shell."""
    events, t = [], 0.6
    for i, (kind, text) in enumerate(lines):
        if kind == "cmd":
            n = len(text)
            for c in range(0, n + 1, 2):
                events.append((t, (i, c)))
                t += 2 / 30.0
            events.append((t, (i, n)))
            t += 0.45
        else:
            events.append((t, (i, len(text))))
            t += 0.07
    total = t
    if total > max_time > 0:
        k = max_time / total
        events = [(et * k, st) for et, st in events]
        total = max_time
    return events, total


def _art_stepper(img, y, active_act):
    n = len(ACT_ORDER)
    x_start, x_end = 260, VIS_W - 260
    xs = [x_start + (x_end - x_start) * i / (n - 1) for i in range(n)]
    d = _AD(img)
    d.line([(xs[0], y), (xs[-1], y)], fill=(255, 255, 255, 40), width=6)
    act_i = ACT_ORDER.index(active_act) if active_act in ACT_ORDER else 0
    d.line([(xs[0], y), (xs[act_i], y)], fill=(*ACT_COLORS[ACT_ORDER[act_i]], 255), width=6)
    for i, (act, x) in enumerate(zip(ACT_ORDER, xs)):
        col = ACT_COLORS[act]
        if i == act_i:
            img.alpha_composite(_glow_layer(img.size, lambda dd, x=x, col=col: dd.ellipse([x - 30, y - 30, x + 30, y + 30], fill=(*col, 255)), 20))
            d.ellipse([x - 26, y - 26, x + 26, y + 26], fill=(*col, 255), outline=(255, 255, 255, 255), width=4)
        else:
            d.ellipse([x - 16, y - 16, x + 16, y + 16], fill=(*tuple(int(c * 0.5) for c in col), 255) if i < act_i else (30, 40, 70, 255), outline=(255, 255, 255, 60), width=2)
    return xs


def _save_art(img, key):
    VIS_ART_DIR.mkdir(parents=True, exist_ok=True)
    path = VIS_ART_DIR / f"{key}.png"
    if not path.exists():
        img.convert("RGB").save(path, optimize=True)
    return path


def _vis_first_sentence(text: str):
    text = re.sub(r"\s+", " ", text or "").strip()
    m = re.match(r"(.{25,260}?[.!?])\s+(.+)$", text)
    if m:
        return m.group(1), m.group(2)
    return text, ""


# ---------- per-slide layout: returns (art_path, [textspec...]) ----------
def _T(x, y, w, h, paras, align="left", anchor="top"):
    return {"x": x, "y": y, "w": w, "h": h, "paras": paras, "align": align, "anchor": anchor}


def _P(text, size, color=(235, 240, 255), bold=False, after=0):
    return {"text": text, "size": size, "color": color, "bold": bold, "after": after}


def _vis_layout(kind, text, act_name, idx, chap_no):
    plan = _VISUAL_CTX.get("plan") or {}
    acc, acc2, acc3 = BRAND["accent"], BRAND["accent2"], BRAND["accent3"]
    fg, muted = BRAND["text"], BRAND["muted"]
    act_col = ACT_COLORS.get(act_name, acc)
    texts = []

    if kind == "title":
        img = _vis_bg([(acc, 1500, 420, 520, 0.55), (PURPLE, 250, 900, 480, 0.35)], seed=11)
        _art_rack(img, 1210, 150, 480, 780, acc)
        for (name, cx, cy, col) in (("cloud", 1640, 230, acc), ("shield", 1730, 520, acc3), ("bolt", 1650, 790, (255, 190, 60))):
            _glass(img, (cx - 20, cy - 20, cx + 120, cy + 120), r=30, glow=col)
            _paste_icon(img, name, cx + 8, cy + 8, 84, col)
        topic = plan.get("topic") or _VISUAL_CTX.get("topic") or text
        head = re.split(r"\s[—–]\s", topic, maxsplit=1)
        headline = head[0].strip().upper()
        sub = head[1].strip() if len(head) > 1 else "A practical guide for U.S. DevOps & cloud engineers"
        series = re.sub(r"-?\d{4}$", "", SERIES_NAME).replace("-", " ").upper()
        d = _AD(img)
        _glass(img, (90, 120, 700, 186), r=33, glow=None, base=(0, 60, 90, 230), border=(0, 190, 255, 160))
        d.ellipse([112, 143, 130, 161], fill=(*acc3, 255))
        texts.append(_T(146, 128, 540, 50, [_P(f"DAY {plan.get('day', _VISUAL_CTX.get('day', ''))}  ·  {series}", 28, (210, 245, 255), True)], anchor="middle"))
        size = _fit_single(headline, 1010, 400, 96, 44, True, 1.12)
        texts.append(_T(90, 240, 1010, 430, [_P(headline, size, (255, 255, 255), True)], anchor="middle"))
        d.rectangle([90, 700, 330, 710], fill=(*acc, 255))
        texts.append(_T(90, 735, 1010, 170, [_P(sub, _fit_single(sub, 1010, 160, 40, 24, False), SOFT_TEXT)]))
        key = "title"
        return _save_art(img, key), texts

    if kind == "stat":
        st = plan.get("stat") or BLS_STATS["dev"]
        img = _vis_bg([(acc3, 420, 420, 480, 0.4), (acc, 1500, 500, 520, 0.4)], seed=21)
        d = _AD(img)
        _paste_icon(img, "dollar", 90, 110, 62, acc3)
        texts.append(_T(172, 112, 900, 60, [_P("WHY IT MATTERS FOR YOUR CAREER", 30, acc3, True)], anchor="middle"))
        big = _usd(st["pay"])
        size = _fit_single(big, 940, 240, 210, 80, True, 1.0)
        texts.append(_T(90, 230, 940, 250, [_P(big, size, (255, 255, 255), True)], anchor="middle"))
        texts.append(_T(90, 500, 940, 140, [_P(f"median yearly pay for U.S. {st['role']}", _fit_single(f"median yearly pay for U.S. {st['role']}", 940, 130, 46, 28, True), (225, 235, 255), True)]))
        if st.get("growth"):
            _glass(img, (90, 670, 770, 750), r=40, base=(10, 60, 40, 235), border=(80, 255, 140, 200))
            _paste_icon(img, "chart", 112, 686, 48, acc3, glow=False)
            texts.append(_T(176, 674, 580, 72, [_P(f"+{st['growth']}% projected job growth, 2025–2035", 30, (200, 255, 225), True)], anchor="middle"))
        core = plan.get("core") or "this skill"
        pill_y = 780 if st.get("growth") else 700
        _glass(img, (90, pill_y, 1010, pill_y + 90), r=45, base=(0, 50, 80, 235), border=(0, 190, 255, 200))
        _paste_icon(img, "target", 118, pill_y + 20, 50, acc, glow=False)
        pill_txt = f"Today's skill: {core}"
        texts.append(_T(190, pill_y + 4, 800, 82, [_P(pill_txt, _fit_single(pill_txt, 800, 78, 34, 22, True), (225, 245, 255), True)], anchor="middle"))
        texts.append(_T(90, 930, 1000, 60, [_P(BLS_SOURCE, 22, muted)]))
        box = (1090, 150, 1840, 900)
        _glass(img, box, glow=acc)
        texts.append(_T(1130, 180, 680, 50, [_P("U.S. MEDIAN PAY · MAY 2025", 26, muted, True)]))
        keys = ["dev", "sec", "net"]
        top = max(BLS_STATS[k]["pay"] for k in keys)
        for n, k in enumerate(keys):
            ry = 260 + n * 200
            s = BLS_STATS[k]
            is_active = k == plan.get("stat_key", "dev")
            col = acc3 if is_active else (70, 110, 170)
            texts.append(_T(1130, ry, 680, 44, [_P(s["short"], 30, (255, 255, 255) if is_active else (170, 185, 215), True)]))
            bw = int(640 * s["pay"] / top)
            d.rounded_rectangle([1130, ry + 56, 1130 + 640, ry + 104], 24, fill=(255, 255, 255, 22))
            if is_active:
                img.alpha_composite(_glow_layer(img.size, lambda dd, ry=ry, bw=bw: dd.rounded_rectangle([1130, ry + 56, 1130 + bw, ry + 104], 24, fill=(*acc3, 255)), 14))
            d.rounded_rectangle([1130, ry + 56, 1130 + bw, ry + 104], 24, fill=(*col, 255))
            texts.append(_T(1130, ry + 56, bw - 24, 48, [_P(_usd(s["pay"]), 28, (6, 12, 24) if is_active else (235, 240, 255), True)], align="right", anchor="middle"))
        return _save_art(img, f"stat_{plan.get('stat_key', 'dev')}"), texts

    if kind == "learn":
        img = _vis_bg([(PURPLE, 400, 300, 500, 0.4), (acc, 1500, 700, 520, 0.4)], seed=31)
        texts.append(_T(90, 105, 1500, 90, [_P("WHAT YOU'LL LEARN", 72, (255, 255, 255), True)], anchor="middle"))
        icons = [("target", acc), ("shield", acc2), ("rocket", acc3)]
        items = plan.get("learn") or [("The core idea", text[:60]), ("Avoid the traps", ""), ("Apply it", "")]
        for i, (head, body) in enumerate(items[:3]):
            x0 = 90 + i * 595
            col = icons[i][1]
            _glass(img, (x0, 250, x0 + 540, 880), glow=col)
            _glass(img, (x0 + 40, 290, x0 + 190, 440), r=40, base=(10, 16, 36, 240), border=(*col, 190))
            _paste_icon(img, icons[i][0], x0 + 72, 322, 86, col)
            texts.append(_T(x0 + 220, 310, 280, 110, [_P(f"0{i + 1}", 84, col, True)], anchor="middle"))
            texts.append(_T(x0 + 40, 480, 460, 120, [_P(head, _fit_single(head, 460, 110, 48, 28, True), (255, 255, 255), True)], anchor="middle"))
            d = _AD(img)
            d.rectangle([x0 + 40, 610, x0 + 130, 616], fill=(*col, 255))
            texts.append(_T(x0 + 40, 640, 460, 210, [_P(body, _fit_single(body, 460, 200, 36, 24, False, 1.28), SOFT_TEXT)]))
        return _save_art(img, "learn"), texts

    if kind == "compare":
        img = _vis_bg([(acc2, 450, 560, 520, 0.38), (acc3, 1470, 560, 520, 0.38)], seed=41)
        d = _AD(img)
        _glass(img, (80, 150, 920, 930), glow=acc2)
        _glass(img, (1000, 150, 1840, 930), glow=acc3)
        texts.append(_T(130, 180, 740, 70, [_P("BEFORE", 58, acc2, True)], anchor="middle"))
        texts.append(_T(130, 250, 740, 44, [_P("The manual way", 30, (225, 190, 190), False)]))
        texts.append(_T(1050, 180, 740, 70, [_P("AFTER", 58, acc3, True)], anchor="middle"))
        texts.append(_T(1050, 250, 740, 44, [_P("The smart way", 30, (190, 235, 205), False)]))
        d.rectangle([130, 310, 870, 313], fill=(*acc2, 140))
        d.rectangle([1050, 310, 1790, 313], fill=(*acc3, 140))
        before = (plan.get("before") or ["", "", "", ""])[:4]
        after = (plan.get("after") or ["", "", "", ""])[:4]
        for i in range(4):
            ry = 350 + i * 142
            _paste_icon(img, "cross", 130, ry + 32, 56, acc2, glow=False)
            _paste_icon(img, "check", 1050, ry + 32, 56, acc3, glow=False)
            texts.append(_T(215, ry, 650, 120, [_P(before[i], _fit_single(before[i], 650, 116, 36, 24, False, 1.2), (235, 225, 228))], anchor="middle"))
            texts.append(_T(1135, ry, 650, 120, [_P(after[i], _fit_single(after[i], 650, 116, 36, 24, False, 1.2), (225, 245, 232))], anchor="middle"))
        img.alpha_composite(_glow_layer(img.size, lambda dd: dd.ellipse([900, 470, 1020, 590], fill=(*acc, 255)), 22))
        d.ellipse([904, 474, 1016, 586], fill=(6, 12, 28, 255), outline=(*acc, 255), width=5)
        d.polygon([(938, 510), (938, 550), (975, 550), (975, 570), (1004, 530), (975, 490), (975, 510)], fill=(*acc, 255))
        return _save_art(img, "compare"), texts

    if kind == "recap":
        img = _vis_bg([(acc3, 1500, 300, 520, 0.4), (acc, 300, 800, 520, 0.3)], seed=51)
        d = _AD(img)
        _paste_icon(img, "check", 90, 112, 78, acc3)
        texts.append(_T(190, 104, 1200, 94, [_P("DO THIS TODAY", 74, (255, 255, 255), True)], anchor="middle"))
        items = plan.get("recap") or ["Apply this at work today.", "Write down what you changed.", "Share it with a teammate."]
        for i, item in enumerate(items[:3]):
            ry = 250 + i * 215
            _glass(img, (90, ry, 1830, ry + 185), glow=acc3 if i == 0 else None)
            img.alpha_composite(_glow_layer(img.size, lambda dd, ry=ry: dd.ellipse([130, ry + 35, 245, ry + 150], fill=(*acc3, 255)), 14))
            d.ellipse([132, ry + 37, 243, ry + 148], fill=(10, 60, 40, 255), outline=(*acc3, 255), width=5)
            texts.append(_T(132, ry + 37, 111, 111, [_P(str(i + 1), 64, acc3, True)], align="center", anchor="middle"))
            texts.append(_T(290, ry + 14, 1400, 157, [_P(item, _fit_single(item, 1400, 150, 46, 26, True, 1.22), (255, 255, 255), True)], anchor="middle"))
            _paste_icon(img, "check", 1730, ry + 62, 62, acc3, glow=False)
        texts.append(_T(90, 925, 1700, 60, [_P("Screenshot this checklist  ·  Subscribe for the next one", 30, muted)]))
        return _save_art(img, "recap"), texts

    if kind == "chapter":
        img = _vis_bg([(act_col, 520, 460, 520, 0.7), (acc, 1500, 300, 420, 0.25)], seed=61 + hash(act_name) % 7)
        d = _AD(img)
        _glass(img, (90, 120, 90 + 300, 190), r=20, base=(*tuple(int(c * 0.55) for c in act_col), 240), border=(*act_col, 230))
        texts.append(_T(90, 120, 300, 70, [_P(act_name, 36, (255, 255, 255), True)], align="center", anchor="middle"))
        sub = ACT_SUBLABELS.get(act_name, "")
        label = text.strip().title() if text.strip().upper() not in ACT_ORDER else (sub.replace(" / ", "  ·  "))
        big = text.strip().upper() if text.strip().upper() not in ACT_ORDER else act_name
        texts.append(_T(90, 260, 1500, 250, [_P(big, _fit_single(big, 1500, 240, 130, 50, True, 1.1), (255, 255, 255), True)], anchor="middle"))
        if sub:
            texts.append(_T(90, 540, 1500, 70, [_P(sub.replace(" / ", "  ·  "), 38, (210, 225, 250), False)]))
        xs = _art_stepper(img, 800, act_name)
        for act, x in zip(ACT_ORDER, xs):
            texts.append(_T(x - 120, 842, 240, 40, [_P(act, 26, (255, 255, 255) if act == act_name else (130, 145, 180), act == act_name)], align="center"))
        return _save_art(img, f"chapter_{act_name.replace(' ', '')}_{'a' if text.strip().upper() in ACT_ORDER else 'b'}"), texts

    if kind == "terminal":
        import hashlib
        lines = _TERMINAL_SCENES.get(text) or [("cmd", "kubectl get pods -A"), ("out", "No resources found")]
        img = _vis_bg([(acc, 1600, 300, 520, 0.35), (PURPLE, 260, 980, 460, 0.25)], seed=91, floor=False, particles=40)
        _paste_icon(img, "server", 90, 92, 52, acc)
        core = (plan.get("core") or _topic_parts(_VISUAL_CTX.get("topic", "") or "Terminal")[0])
        texts.append(_T(160, 90, 1500, 56, [_P(f"IN THE TERMINAL  ·  {core.upper()}", 30, acc, True)], anchor="middle"))
        box = (90, 170, 1830, 900)
        _terminal_window(img, box)
        _TERMINAL_RENDER[idx] = {"base": img.convert("RGB"), "box": box, "lines": lines}
        final = img.copy()
        _draw_terminal_lines(final, box, lines, reveal=None)
        key = "terminal_" + hashlib.md5(repr(lines).encode()).hexdigest()[:12]
        _TERMINAL_RENDER[idx]["final"] = final.convert("RGB")
        return _save_art(final, key), texts

    if kind in ("hook", "tip", "body"):
        theme = {"hook": "alert", "tip": "ok", "body": "neutral"}[kind]
        col = {"hook": acc2, "tip": acc3, "body": acc}[kind]
        variant = idx % 3 if kind == "body" else 0
        img = _vis_bg([(col, 1550, 520, 520, 0.42), ((PURPLE if kind == "body" else col), 200, 950, 420, 0.22)], seed=71 + variant)
        term = plan.get("term") or [("cmd", "git push origin main"), ("ok", "deployed")]
        if kind == "hook":
            _art_dashboard(img, (1150, 170, 1850, 590), "alert", seed=idx)
            _art_terminal(img, (1150, 630, 1850, 940), [("cmd", "deploy --env production"), ("err", "health check failed"), ("err", "error rate above threshold"), ("out", "rolling back...")], "alert", 26)
        elif kind == "tip":
            _art_terminal(img, (1150, 170, 1850, 590), term, "ok", 26)
            _art_dashboard(img, (1150, 630, 1850, 940), "ok", seed=idx)
        elif variant == 0:
            _art_dashboard(img, (1150, 190, 1850, 890), "neutral", seed=idx)
        elif variant == 1:
            _art_rack(img, 1300, 150, 480, 800, acc, seed=idx)
        else:
            _art_terminal(img, (1150, 250, 1850, 830), term, "neutral", 26)
        tag_y = 112
        body_y = 150
        if kind in ("hook", "tip"):
            icon = "warning" if kind == "hook" else "check"
            _paste_icon(img, icon, 90, tag_y - 6, 62, col)
            texts.append(_T(170, tag_y - 6, 700, 62, [_P("THE PROBLEM" if kind == "hook" else "THE FIX", 34, col, True)], anchor="middle"))
            body_y = 205
        first, rest = _vis_first_sentence(text)
        paras = [_P(first, 50, (255, 255, 255), True, 22 if rest else 0)]
        if rest:
            paras.append(_P(rest, 36, SOFT_TEXT, False))
        paras = _fit_paras(paras, 1000, 960 - body_y)
        texts.append(_T(90, body_y, 1000, 960 - body_y, paras, anchor="middle"))
        return _save_art(img, f"{kind}_{variant}"), texts

    if kind == "cta":
        img = _vis_bg([(acc2, 960, 540, 560, 0.45), (acc, 300, 300, 420, 0.25)], seed=81)
        d = _AD(img)
        texts.append(_T(260, 300, 1400, 80, [_P("ENJOYING THIS VIDEO?", 52, (255, 255, 255), True)], align="center", anchor="middle"))
        img.alpha_composite(_glow_layer(img.size, lambda dd: dd.rounded_rectangle([610, 450, 1310, 590], 70, fill=(255, 40, 40, 255)), 26))
        d.rounded_rectangle([610, 450, 1310, 590], 70, fill=(235, 30, 36, 255), outline=(255, 120, 120, 255), width=3)
        _paste_icon(img, "bell", 660, 485, 70, (255, 255, 255), glow=False)
        texts.append(_T(750, 450, 520, 140, [_P("SUBSCRIBE", 60, (255, 255, 255), True)], align="center", anchor="middle"))
        texts.append(_T(260, 670, 1400, 70, [_P("Free U.S.-focused DevOps & AI career videos", 40, SOFT_TEXT)], align="center"))
        texts.append(_T(260, 750, 1400, 50, [_P(CHANNEL_URL, 30, muted)], align="center"))
        return _save_art(img, "cta"), texts

    if kind == "outro":
        img = _vis_bg([(acc, 960, 500, 600, 0.5), (PURPLE, 1500, 900, 420, 0.3)], seed=91)
        for i, (name, col) in enumerate((("cloud", acc), ("shield", acc3), ("bolt", (255, 190, 60)), ("rocket", acc2))):
            _paste_icon(img, name, 600 + i * 190, 190, 90, col)
        t = (text or "Start applying it today.").replace("tomorrow", "in the next video")
        main_line = t.split("\n")[0]
        texts.append(_T(160, 340, 1600, 260, [_P(main_line.upper(), _fit_single(main_line.upper(), 1600, 250, 112, 48, True, 1.1), (255, 255, 255), True)], align="center", anchor="middle"))
        sub = "\n".join(t.split("\n")[1:]).strip() or "See you in the next video."
        texts.append(_T(160, 640, 1600, 80, [_P(sub, 44, SOFT_TEXT)], align="center"))
        texts.append(_T(160, 880, 1600, 50, [_P(f"{CHANNEL_NAME}  ·  {CHANNEL_BRAND}", 32, muted)], align="center"))
        return _save_art(img, "outro"), texts

    # unknown kind -> render like a body slide
    return _vis_layout("body", text, act_name, idx, chap_no)


def _pptx_add_rich(slide, spec):
    box = slide.shapes.add_textbox(
        Inches(_px_x(spec["x"])), Inches(_px_y(spec["y"])), Inches(_px_x(spec["w"])), Inches(_px_y(spec["h"])),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE}[spec.get("anchor", "top")]
    align = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[spec.get("align", "left")]
    paras = spec["paras"]
    if not spec.get("_fitted"):
        paras = _fit_paras(paras, spec["w"], spec["h"]) if len(paras) > 1 else paras
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        if p.get("after"):
            para.space_after = Pt(_px_pt(p["after"]))
        run = para.add_run()
        run.text = p["text"]
        run.font.size = Pt(_px_pt(p["size"]))
        run.font.bold = bool(p.get("bold"))
        run.font.name = "Arial"
        run.font.color.rgb = _rgb(p["color"])
    return box


def _pptx_render_slide_v2(prs, kind, text, progress, slide_num, total_slides, act_name, idx, chap_no):
    art_path, texts = _vis_layout(kind, text, act_name, idx, chap_no)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(str(art_path), 0, 0, width=prs.slide_width, height=prs.slide_height)
    acc, muted = BRAND["accent"], BRAND["muted"]
    _pptx_add_text(slide, 28, 14, 600, 40, CHANNEL_NAME, size_px=24, color=acc, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    _pptx_add_text(slide, 1500, 14, 392, 40, CHANNEL_BRAND, size_px=22, color=muted, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    for spec in texts:
        _pptx_add_rich(slide, spec)
    bar_h = 10
    _pptx_add_rect(slide, 0, 1080 - bar_h, 1920, bar_h, fill=(25, 32, 60))
    _pptx_add_rect(slide, 0, 1080 - bar_h, max(1, int(1920 * min(progress, 1.0))), bar_h, fill=acc)
    _pptx_add_text(slide, 1760, 1080 - bar_h - 36, 140, 28, f"{slide_num}/{total_slides}", size_px=20, color=muted, align=PP_ALIGN.RIGHT)
    return slide


def _px_x(px: float) -> float:
    return (px / 1920.0) * PPTX_SLIDE_WIDTH_IN


def _px_y(px: float) -> float:
    return (px / 1080.0) * PPTX_SLIDE_HEIGHT_IN


def _px_pt(px: float) -> float:
    return px / 2.0


def _rgb(color_tuple) -> "RGBColor":
    return RGBColor(*color_tuple)


def _pptx_add_rect(slide, x_px, y_px, w_px, h_px, fill, line_color=None, line_pt=0, rounded=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type,
        Inches(_px_x(x_px)), Inches(_px_y(y_px)),
        Inches(_px_x(w_px)), Inches(_px_y(h_px)),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    if line_color:
        shape.line.color.rgb = _rgb(line_color)
        shape.line.width = Pt(line_pt or 2)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _pptx_add_text(
    slide, x_px, y_px, w_px, h_px, text, size_px, color,
    bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font_name="Arial",
):
    box = slide.shapes.add_textbox(
        Inches(_px_x(x_px)), Inches(_px_y(y_px)),
        Inches(_px_x(w_px)), Inches(_px_y(h_px)),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = str(text).split("\n") or [""]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = Pt(_px_pt(size_px))
        run.font.bold = bold
        run.font.name = font_name
        run.font.color.rgb = _rgb(color)
    return box


def _pptx_act_structure_diagram(slide, active_act):
    n = len(ACT_ORDER)
    box_w, box_h = 320, 260
    gap = 24
    total_w = n * box_w + (n - 1) * gap
    x = (1920 - total_w) // 2
    y = 1080 // 2 - box_h // 2 + 40

    for act in ACT_ORDER:
        base_color = ACT_COLORS[act]
        is_active = act == active_act
        color = base_color if is_active else tuple(int(c * 0.35) for c in base_color)
        _pptx_add_rect(
            slide, x, y, box_w, box_h, fill=color,
            line_color=(255, 255, 255) if is_active else None,
            line_pt=2.5 if is_active else 0,
            rounded=True,
        )
        _pptx_add_text(
            slide, x, y + 16, box_w, 44, act, size_px=30, color=(255, 255, 255),
            bold=True, align=PP_ALIGN.CENTER,
        )
        _pptx_add_text(
            slide, x + 12, y + box_h - 90, box_w - 24, 80, ACT_SUBLABELS[act],
            size_px=20, color=(255, 255, 255), align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM,
        )
        x += box_w + gap


def _pptx_render_slide(prs, kind, text, progress, slide_num, total_slides, act_name):
    layout = prs.slide_layouts[6]  # blank layout
    slide = prs.slides.add_slide(layout)

    bg = BRAND["bg"]
    acc = BRAND["accent"]
    acc2 = BRAND["accent2"]
    acc3 = BRAND["accent3"]
    fg = BRAND["text"]
    muted = BRAND["muted"]

    # Background
    _pptx_add_rect(slide, 0, 0, 1920, 1080, fill=bg)

    # Header
    _pptx_add_rect(slide, 0, 0, 1920, 64, fill=(12, 18, 34))
    _pptx_add_text(slide, 28, 14, 500, 40, CHANNEL_NAME, size_px=24, color=acc, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    _pptx_add_text(slide, 1640, 14, 260, 40, CHANNEL_BRAND, size_px=22, color=muted, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

    # Footer progress bar
    bar_h = 10
    _pptx_add_rect(slide, 0, 1080 - bar_h, 1920, bar_h, fill=(25, 32, 60))
    _pptx_add_rect(slide, 0, 1080 - bar_h, max(1, int(1920 * min(progress, 1.0))), bar_h, fill=acc)
    _pptx_add_text(slide, 1800, 1080 - bar_h - 34, 120, 28, f"{slide_num}/{total_slides}", size_px=20, color=muted, align=PP_ALIGN.RIGHT)

    if kind == "title":
        _pptx_add_rect(slide, 0, 80, 12, 1080 - 100, fill=acc)
        _pptx_add_text(
            slide, 120, 340, 1680, 380, text.upper(), size_px=68, color=fg,
            bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
        )
        _pptx_add_text(slide, 80, 960, 1000, 60, "A full deep dive for DevOps engineers.", size_px=28, color=muted)

    elif kind == "chapter":
        act_color = ACT_COLORS.get(act_name, acc)
        _pptx_add_rect(slide, 80, 100, 220, 40, fill=act_color, rounded=True)
        _pptx_add_text(slide, 80, 100, 220, 40, act_name, size_px=24, color=(255, 255, 255), bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        _pptx_add_text(slide, 80, 165, 1760, 130, text, size_px=46, color=fg, bold=True)
        _pptx_act_structure_diagram(slide, act_name)

    elif kind == "hook":
        _pptx_add_rect(slide, 0, 80, 1920, 10, fill=acc2)
        _pptx_add_text(slide, 80, 105, 800, 44, "⚠ THE PROBLEM", size_px=28, color=acc2, bold=True)
        _pptx_add_text(slide, 80, 175, 1760, 700, text, size_px=38, color=fg, bold=True)

    elif kind == "tip":
        _pptx_add_rect(slide, 60, 90, 1800, 900, fill=(12, 40, 22), line_color=acc3, line_pt=2.5, rounded=True)
        _pptx_add_text(slide, 100, 115, 700, 44, "💡 THE FIX", size_px=28, color=acc3, bold=True)
        _pptx_add_text(slide, 100, 190, 1720, 760, text, size_px=36, color=fg)

    elif kind == "body":
        _pptx_add_text(slide, 80, 105, 1760, 850, text, size_px=34, color=fg)

    elif kind == "cta":
        _pptx_add_text(slide, 260, 420, 1400, 70, "\U0001f514  LIKE THIS IF IT'S HELPING", size_px=40, color=acc, bold=True, align=PP_ALIGN.CENTER)
        _pptx_add_text(slide, 260, 500, 1400, 60, "Subscribe — new DevOps video every day", size_px=34, color=fg, align=PP_ALIGN.CENTER)
        _pptx_add_text(slide, 260, 560, 1400, 50, CHANNEL_URL, size_px=26, color=muted, align=PP_ALIGN.CENTER)

    elif kind == "outro":
        _pptx_add_rect(slide, 0, 80, 1920, 10, fill=acc)
        _pptx_add_text(
            slide, 260, 380, 1400, 260, text, size_px=56, color=fg, bold=True,
            align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
        )
        _pptx_add_text(slide, 460, 920, 1000, 50, f"See you tomorrow  |  {CHANNEL_NAME}", size_px=30, color=muted, align=PP_ALIGN.CENTER)

    return slide


def build_slide_deck(slides: list, day_num: int, topic: str, audio_dur: float) -> Path:
    """Build the real, editable .pptx source-of-truth deck for one day's
    video from the same (kind, text, duration, act_name) slide list that
    drives the video timing. Saved under SLIDES_DIR and kept (not a temp
    file) so it can be opened, tweaked, and re-rendered by hand later.
    """
    if not HAS_PPTX:
        raise RuntimeError("python-pptx is not installed.")

    prs = Presentation()
    prs.slide_width = Inches(PPTX_SLIDE_WIDTH_IN)
    prs.slide_height = Inches(PPTX_SLIDE_HEIGHT_IN)

    cumulative = 0.0
    chap_no = 0
    v2_failures = 0
    for i, (kind, text, dur, act_name) in enumerate(slides):
        progress = cumulative / audio_dur if audio_dur > 0 else 0
        if kind == "chapter":
            chap_no += 1
        rkind = _render_kind(kind)
        if kind == "titlehook":
            text = _topic_parts(topic)[0]  # title card shows the topic, not the narration
        rendered = False
        if VISUALS_STYLE == "cinematic":
            try:
                _pptx_render_slide_v2(prs, rkind, text, progress, i + 1, len(slides), act_name, i, chap_no)
                rendered = True
            except Exception as exc:
                v2_failures += 1
                print(f"[VISUALS] Slide {i + 1} ({kind}) fell back to the classic design: {exc}")
        if not rendered:
            _pptx_render_slide(prs, _classic_kind(kind), text, progress, i + 1, len(slides), act_name)
        cumulative += dur
    if v2_failures:
        print(f"[VISUALS] {v2_failures} slide(s) used the classic design.")

    SLIDES_DIR.mkdir(exist_ok=True, parents=True)
    safe_topic = re.sub(r"[^a-z0-9]+", "-", topic.split("—")[0].strip().lower()).strip("-")[:60]
    pptx_path = SLIDES_DIR / f"day_{day_num:03d}_{safe_topic}.pptx"
    prs.save(str(pptx_path))
    print(f"[SLIDES] Built {pptx_path} ({len(slides)} slides).")
    return pptx_path


def render_pptx_to_frames(pptx_path: Path, frames_dir: Path, timeout_sec: int = 300) -> list:
    """Rasterize every slide of pptx_path to a PNG frame in frames_dir,
    in slide order, at PPTX_RENDER_DPI. LibreOffice's --convert-to png
    only exports a single slide, so the reliable headless path (used
    across most CI pptx-rendering pipelines) is: pptx -> single PDF via
    LibreOffice, then PDF page -> PNG per page via poppler's pdftoppm.
    Raises on any failure so the caller can fall back to the PIL
    renderer instead of failing the whole day's video.
    """
    frames_dir.mkdir(exist_ok=True, parents=True)
    pdf_path = frames_dir / (pptx_path.stem + ".pdf")

    subprocess.run(
        [
            "soffice", "--headless", "--norestore", "--convert-to", "pdf",
            "--outdir", str(frames_dir), str(pptx_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_sec,
    )
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not produce {pdf_path}.")

    prefix = frames_dir / "slide"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(PPTX_RENDER_DPI), str(pdf_path), str(prefix)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_sec,
    )
    pdf_path.unlink(missing_ok=True)

    def _page_num(p: Path) -> int:
        m = re.search(r"-(\d+)$", p.stem)
        return int(m.group(1)) if m else 0

    frame_files = sorted(frames_dir.glob("slide-*.png"), key=_page_num)
    if not frame_files:
        raise RuntimeError("pdftoppm produced no frame PNGs.")
    return frame_files


# ---------- v3.3.0: overlays (terminal typing, AI host) + burned captions ----------
BURN_CAPTIONS = os.environ.get("BURN_CAPTIONS", "true").strip().lower() not in ("0", "false", "no", "off")
HOST_ENABLED = os.environ.get("HOST_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
HOST_IMAGE = Path(os.environ.get("HOST_IMAGE", "assets/host.png"))
HOST_MODE = os.environ.get("HOST_MODE", "key").strip().lower()          # key | all
HOST_MAX_SECONDS = float(os.environ.get("HOST_MAX_SECONDS", "240"))
HOST_TIMEOUT_MIN = float(os.environ.get("HOST_TIMEOUT_MIN", "45"))
HOST_ELIGIBLE_KINDS = {"titlehook", "hook", "tip", "body"}  # layouts whose right half is decorative art
# Host panel geometry (1920x1080 frame). The cinematic layouts keep text in
# x<1100, so the presenter replaces the decorative art on the right.
HOST_PANEL_CINEMATIC = (1220, 170, 560, 720)   # x, y, w, h
HOST_BACKDROP_CINEMATIC = (1120, 130, 1904, 952)  # dark glass that hides the decorative art behind the panel
HOST_PANEL_CLASSIC = (1520, 560, 340, 438)     # small corner cam on classic slides


def _slide_starts(slides: list) -> list:
    starts, t = [], 0.0
    for s in slides:
        starts.append(t)
        t += s[2]
    return starts


def select_host_segments(slides: list, mode: str = HOST_MODE, max_seconds: float = HOST_MAX_SECONDS) -> list:
    """Which parts of the narration the AI presenter appears for.
    key (default): the whole cold open, the first explanation after each
    chapter card, and the closing call to action - about 2-4 minutes, which
    keeps the free Kaggle GPU budget to ~15 min per video. all: every
    eligible slide (capped by max_seconds)."""
    starts = _slide_starts(slides)
    eligible = [i for i, s in enumerate(slides) if s[0] in HOST_ELIGIBLE_KINDS and s[2] > 0.5]
    chosen = set()
    if mode == "all":
        chosen = set(eligible)
    else:
        for i in eligible:                      # cold open (HOOK chapter)
            if slides[i][3] != "HOOK":
                break
            chosen.add(i)
        for k, s in enumerate(slides):          # first explanation after each chapter card
            if s[0] == "chapter":
                nxt = [i for i in eligible if i > k][:1]
                if nxt and nxt[0] - k <= 3:
                    chosen.add(nxt[0])
                    if slides[nxt[0]][2] < 12 and nxt[0] + 1 in eligible:
                        chosen.add(nxt[0] + 1)
        tail, acc = [], 0.0                     # closing CTA (last eligible ACT 3 slides)
        for i in reversed(eligible):
            if slides[i][3] != "ACT 3" or acc > 25:
                break
            tail.append(i)
            acc += slides[i][2]
        chosen.update(tail)
    # contiguous runs -> segments
    segs, run = [], []
    for i in sorted(chosen):
        if run and i != run[-1] + 1:
            segs.append(run)
            run = []
        run.append(i)
    if run:
        segs.append(run)
    out = [{"start": starts[r[0]], "end": starts[r[-1]] + slides[r[-1]][2], "slides": r} for r in segs]
    # budget: keep the opening and the ending, drop middle segments first
    while out and sum(o["end"] - o["start"] for o in out) > max_seconds and len(out) > 2:
        mid = sorted(range(1, len(out) - 1), key=lambda k: out[k]["end"] - out[k]["start"], reverse=True)[0]
        out.pop(mid)
    if out and sum(o["end"] - o["start"] for o in out) > max_seconds:
        out[0]["end"] = min(out[0]["end"], out[0]["start"] + max_seconds)
        out = out[:1]
    for n, o in enumerate(out):
        o["id"] = f"seg_{n:02d}"
    return out


def _host_backdrop(box) -> Path:
    """Full-frame transparent PNG with a dark glass card where the
    decorative art was, so no art peeks out around the presenter."""
    from PIL import ImageFilter as _IF
    d = OUTPUT_DIR / "host_assets"
    d.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = box
    img = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, img.width - 1, img.height - 1], 30, fill=(6, 10, 24, 246),
                                          outline=(0, 190, 255, 70), width=2)
    p = d / f"backdrop_{x1 - x0}x{y1 - y0}.png"
    img.save(p)
    return p


def _host_assets(w: int, h: int) -> tuple:
    """Rounded-corner alpha mask + glowing border frame for the presenter panel."""
    from PIL import ImageFilter as _IF
    d = OUTPUT_DIR / "host_assets"
    d.mkdir(parents=True, exist_ok=True)
    r = 28
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
    mask_p = d / f"mask_{w}x{h}.png"
    mask.save(mask_p)
    pad = 24
    frame = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    glow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([pad - 2, pad - 2, pad + w + 1, pad + h + 1], r + 2, outline=(0, 190, 255, 200), width=8)
    frame.alpha_composite(glow.filter(_IF.GaussianBlur(10)))
    ImageDraw.Draw(frame).rounded_rectangle([pad - 2, pad - 2, pad + w + 1, pad + h + 1], r + 2, outline=(120, 220, 255, 230), width=3)
    frame_p = d / f"frame_{w}x{h}.png"
    frame.save(frame_p)
    return mask_p, frame_p, pad


def _render_terminal_typing_clip(entry: dict, show_dur: float, out_path: Path) -> tuple:
    """Opaque crop of the terminal window, typing from empty to the exact
    final state of the static slide, then held. Returns (x, y, w, h)."""
    base, box, lines = entry["base"], entry["box"], entry["lines"]
    m = 30
    x0, y0 = max(0, box[0] - m), max(0, box[1] - m)
    x1, y1 = min(base.width, box[2] + m), min(base.height, box[3] + m)
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    x1, y1 = x0 + w, y0 + h
    events, type_dur = _terminal_typing_timeline(lines, max_time=max(1.0, show_dur * 0.7))
    n_frames = max(1, int(type_dur * RENDER_FPS) + 1)
    hold = max(0.05, show_dur - n_frames / RENDER_FPS)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(RENDER_FPS), "-i", "-",
         "-vf", f"tpad=stop_mode=clone:stop_duration={hold:.3f}", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-pix_fmt", "yuv420p", str(out_path)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ei = 0
    state = (0, 0)
    for f in range(n_frames):
        t = f / RENDER_FPS
        while ei < len(events) and events[ei][0] <= t:
            state = events[ei][1]
            ei += 1
        frame = base.copy()
        final = f == n_frames - 1
        blink = (int(t * 2) % 2 == 0)
        _draw_terminal_lines(frame, box, lines, reveal=None if final else state, cursor=final or blink)
        proc.stdin.write(frame.crop((x0, y0, x1, y1)).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the terminal typing clip")
    return x0, y0, w, h


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    sec, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def build_burned_captions_ass(slides: list, output_path: Path) -> Path:
    """Word-by-word highlighted captions (current word yellow) for burning
    into the video. Word times are distributed across each slide's exact
    narration duration by word length (+ pauses after punctuation) - close
    enough for 3-6 word caption lines because every slide boundary is exact."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H70000000,&H70000000,1,0,0,0,100,100,0,0,3,12,0,2,120,120,58,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    t = 0.0
    for kind, text, dur, act in slides:
        clean = re.sub(r"\s+", " ", text or "").strip()
        if kind in SPOKEN_SLIDE_KINDS and clean and dur > 0.3:
            words = clean.split(" ")
            weights = [len(w) + 2 + (4 if re.search(r"[.!?]$", w) else 2 if re.search(r"[,;:]$", w) else 0) for w in words]
            speak = max(0.1, dur - 0.25)
            total_w = float(sum(weights)) or 1.0
            times, cur = [], t + 0.05
            for w_, wt in zip(words, weights):
                d = speak * wt / total_w
                times.append((cur, cur + d))
                cur += d
            # group into caption lines: <= 6 words / 38 chars, break after sentence ends
            groups, g = [], []
            for k, w_ in enumerate(words):
                if g and (len(g) >= 6 or len(" ".join(words[j] for j in g + [k])) > 38):
                    groups.append(g)
                    g = []
                g.append(k)
                if re.search(r"[.!?]$", w_):
                    groups.append(g)
                    g = []
            if g:
                groups.append(g)
            for grp in groups:
                for k in grp:
                    st, en = times[k]
                    if k == grp[-1]:
                        en = times[k][1]
                    parts = []
                    for j in grp:
                        wtxt = _ass_escape(words[j])
                        parts.append("{\\c&H00D7FF&}" + wtxt + "{\\c&HFFFFFF&}" if j == k else wtxt)
                    events.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Cap,,0,0,0,,{' '.join(parts)}")
        t += dur
    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output_path


def _compose_final(temp_video: Path, audio_path: Path, output_video: Path, overlays: list, ass_path):
    """One pass: terminal typing clips + AI host panel + burned captions +
    audio mux. Without overlays/captions it is the old stream-copy mux."""
    if not overlays and not ass_path:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(temp_video), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(output_video)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    inputs = ["-i", str(temp_video)]
    n_in = 1
    parts = []
    base = "0:v"
    for k, ov in enumerate(overlays):
        st, dur = ov["start"], ov["dur"]
        fi = min(0.3, dur / 4)
        if ov.get("backdrop"):
            bx, by, bpath = ov["backdrop"]
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(bpath)]
            bi = n_in
            n_in += 1
            parts.append(f"[{bi}:v]format=rgba,fade=t=in:st=0:d={fi:.3f}:alpha=1,fade=t=out:st={max(0.0, dur - fi):.3f}:d={fi:.3f}:alpha=1,setpts=PTS+{st:.3f}/TB[bd{k}]")
            parts.append(f"[{base}][bd{k}]overlay=x={bx}:y={by}:eof_action=pass:enable='between(t,{st:.3f},{st + dur:.3f})'[bb{k}]")
            base = f"bb{k}"
        inputs += ["-i", str(ov["path"])]
        vid = n_in
        n_in += 1
        chain = f"[{vid}:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,scale={ov['w']}:{ov['h']},format=yuva420p"
        if ov.get("mask"):
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(ov["mask"])]
            mi = n_in
            n_in += 1
            parts.append(f"[{mi}:v]scale={ov['w']}:{ov['h']},format=gray,setpts=PTS-STARTPTS[mk{k}]")
            parts.append(chain + f"[ov{k}a]")
            parts.append(f"[ov{k}a][mk{k}]alphamerge[ov{k}m]")
            chain = f"[ov{k}m]format=yuva420p"
        if ov.get("fade_in", True):
            chain += f",fade=t=in:st=0:d={fi:.3f}:alpha=1"
        chain += f",fade=t=out:st={max(0.0, dur - fi):.3f}:d={fi:.3f}:alpha=1,setpts=PTS+{st:.3f}/TB[ov{k}]"
        parts.append(chain)
        out = f"b{k}"
        parts.append(f"[{base}][ov{k}]overlay=x={ov['x']}:y={ov['y']}:eof_action=pass:enable='between(t,{st:.3f},{st + dur:.3f})'[{out}]")
        base = out
        if ov.get("frame"):
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(ov["frame"])]
            fi_idx = n_in
            n_in += 1
            parts.append(f"[{fi_idx}:v]format=rgba,fade=t=in:st=0:d={fi:.3f}:alpha=1,fade=t=out:st={max(0.0, dur - fi):.3f}:d={fi:.3f}:alpha=1,setpts=PTS+{st:.3f}/TB[fr{k}]")
            parts.append(f"[{base}][fr{k}]overlay=x={ov['x'] - ov['pad']}:y={ov['y'] - ov['pad']}:eof_action=pass:enable='between(t,{st:.3f},{st + dur:.3f})'[bf{k}]")
            base = f"bf{k}"
    if ass_path:
        fontsdir = "/usr/share/fonts/truetype/dejavu"
        parts.append(f"[{base}]ass=filename={Path(ass_path).as_posix()}:fontsdir={fontsdir}[vout]")
    else:
        parts.append(f"[{base}]null[vout]")
    inputs += ["-i", str(audio_path)]
    audio_idx = n_in
    graph = OUTPUT_DIR / "compose_graph.txt"
    graph.write_text(";\n".join(parts), encoding="utf-8")
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex_script", str(graph), "-map", "[vout]", "-map", f"{audio_idx}:a:0",
        "-r", str(RENDER_FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_video),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"final compose failed: {res.stderr[-1500:]}")
    graph.unlink(missing_ok=True)


def build_video(slides: list, audio_path: Path, output_video: Path, day_num: int = 0, topic: str = "",
                host_future=None) -> tuple:
    """slides is the final [(kind, text, duration, act_name), ...] list
    from generate_synced_narration() - real per-slide durations. Returns
    (slides_engine_used, extras) where extras reports which v3.3.0 layers
    (terminal typing, AI host, burned captions) actually made it in.
    host_future: optional concurrent.futures.Future from the Kaggle host
    job (started earlier so it renders while the slides render)."""
    audio_dur = _ffprobe_duration(audio_path)
    print(f"[VIDEO] Audio duration: {audio_dur:.1f}s ({audio_dur / 60:.1f} min)")

    frames_dir = OUTPUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)
    img_paths = []
    durations = [s[2] for s in slides]
    _TERMINAL_RENDER.clear()

    # Primary path: build the real .pptx deck and rasterize it via
    # LibreOffice + poppler. Falls back to Pillow-rendered frames if pptx
    # isn't available or the conversion fails - a broken slide pipeline
    # should never be the reason a whole day's video doesn't ship.
    slides_engine_used = None
    if HAS_PPTX:
        try:
            pptx_path = build_slide_deck(slides, day_num, topic, audio_dur)
            frame_files = render_pptx_to_frames(pptx_path, frames_dir)
            if len(frame_files) != len(slides):
                raise RuntimeError(
                    f"Rendered {len(frame_files)} frames but the slide list has {len(slides)} entries."
                )
            img_paths = list(zip(frame_files, durations))
            slides_engine_used = "pptx"
            print(f"[SLIDES] Using {len(frame_files)} PPTX-rendered frames from {pptx_path.name}.")
        except Exception as exc:
            print(f"[SLIDES] PPTX pipeline failed ({exc}) - falling back to the built-in PIL slide renderer.")
            img_paths = []
            for p in frames_dir.glob("*"):
                p.unlink()
    else:
        print("[SLIDES] python-pptx not installed - using the built-in PIL slide renderer.")

    if not img_paths:
        slides_engine_used = "pil"
        _TERMINAL_RENDER.clear()
        cumulative = 0.0
        for i, (kind, text, dur, act_name) in enumerate(slides):
            progress = cumulative / audio_dur if audio_dur > 0 else 0
            img = None
            if kind == "terminal" and VISUALS_STYLE == "cinematic":
                try:
                    art_path, _ = _vis_layout("terminal", text, act_name, i, 0)
                    img = Image.open(art_path).convert("RGB")
                except Exception as exc:
                    print(f"[SLIDES] Terminal slide {i + 1} fell back to a body slide: {exc}")
                    _TERMINAL_RENDER.pop(i, None)
            if img is None:
                shown = _topic_parts(topic)[0] if kind == "titlehook" else text
                img = _render_slide(_classic_kind(kind), shown, progress, i + 1, len(slides), 1920, 1080, act_name=act_name)
            fpath = frames_dir / f"slide_{i:05d}.png"
            img.save(fpath)
            img_paths.append((fpath, dur))
            cumulative += dur

    temp_video = OUTPUT_DIR / "temp_video.mp4"

    if ENABLE_MOTION:
        print("[VIDEO] Rendering slides with Ken Burns zoom + crossfade transitions...")
        _render_with_motion(img_paths, temp_video, 1920, 1080)
    else:
        concat_file = OUTPUT_DIR / "concat.txt"
        with open(concat_file, "w") as f:
            for img_path, dur in img_paths:
                f.write(f"file '{img_path.resolve().as_posix()}'\n")
                f.write(f"duration {dur:.4f}\n")
            f.write(f"file '{img_paths[-1][0].resolve().as_posix()}'\n")

        print("[VIDEO] Rendering slides to video (static)...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-vf", "scale=1920:1080", "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-r", str(RENDER_FPS), str(temp_video)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        concat_file.unlink(missing_ok=True)

    extras = {"terminal_scenes": 0, "host_segments": 0, "host_seconds": 0.0, "burned_captions": False}
    starts = _slide_starts(slides)
    overlays = []

    # Terminal typing overlays. The Ken Burns zoom is skipped for these
    # slides' overlay region on purpose: the terminal window is a fixed
    # screen element, and the zoom is subtle (<=8%) at that point in a clip.
    ov_dir = OUTPUT_DIR / "overlays"
    ov_dir.mkdir(exist_ok=True)
    if ENABLE_MOTION:
        print("[VIDEO] Note: terminal slides get a static (non-zooming) typing window.")
    for i, entry in sorted(_TERMINAL_RENDER.items()):
        if i >= len(slides) or slides[i][0] != "terminal":
            continue
        try:
            clip = ov_dir / f"terminal_{i:04d}.mp4"
            x, y, w, h = _render_terminal_typing_clip(entry, slides[i][2], clip)
            overlays.append({"path": clip, "start": starts[i], "dur": slides[i][2], "x": x, "y": y, "w": w, "h": h, "fade_in": False})
            extras["terminal_scenes"] += 1
        except Exception as exc:
            print(f"[VIDEO] Terminal typing for slide {i + 1} skipped: {exc}")
    if extras["terminal_scenes"]:
        print(f"[VIDEO] {extras['terminal_scenes']} animated terminal scene(s).")

    # AI host (Kaggle lip-sync job, started in main() while slides rendered)
    if host_future is not None:
        try:
            print("[HOST] Waiting for the AI presenter clips from Kaggle...")
            host_clips = host_future.result()
        except Exception as exc:
            host_clips = []
            print(f"[HOST] AI presenter skipped - video ships without it: {str(exc)[:500]}")
        if host_clips:
            cinematic = slides_engine_used == "pptx" and VISUALS_STYLE == "cinematic"
            px, py, pw, ph = HOST_PANEL_CINEMATIC if cinematic else HOST_PANEL_CLASSIC
            mask_p, frame_p, pad = _host_assets(pw, ph)
            backdrop = (HOST_BACKDROP_CINEMATIC[0], HOST_BACKDROP_CINEMATIC[1], _host_backdrop(HOST_BACKDROP_CINEMATIC)) if cinematic else None
            for hc in host_clips:
                dur = hc["end"] - hc["start"]
                overlays.append({"path": hc["path"], "start": hc["start"], "dur": dur, "x": px, "y": py, "w": pw, "h": ph,
                                 "mask": mask_p, "frame": frame_p, "pad": pad, "backdrop": backdrop})
                extras["host_segments"] += 1
                extras["host_seconds"] += dur
            print(f"[HOST] AI presenter on screen in {extras['host_segments']} segment(s), {extras['host_seconds']:.0f}s total.")

    ass_path = None
    if BURN_CAPTIONS:
        try:
            ass_path = build_burned_captions_ass(slides, OUTPUT_DIR / "captions_burn.ass")
        except Exception as exc:
            print(f"[CAPTIONS] Burned captions skipped: {exc}")

    print("[VIDEO] Final pass: overlays + captions + audio...")
    try:
        _compose_final(temp_video, audio_path, output_video, overlays, ass_path)
        extras["burned_captions"] = bool(ass_path)
    except Exception as exc:
        # Never lose the day's video over an overlay: retry captions-only, then plain mux.
        print(f"[VIDEO] {str(exc)[:800]}")
        print("[VIDEO] Retrying the final pass without overlays...")
        extras.update({"terminal_scenes": 0, "host_segments": 0, "host_seconds": 0.0})
        try:
            _compose_final(temp_video, audio_path, output_video, [], ass_path)
            extras["burned_captions"] = bool(ass_path)
        except Exception as exc2:
            print(f"[VIDEO] Captions pass failed too ({str(exc2)[:300]}) - plain mux.")
            _compose_final(temp_video, audio_path, output_video, [], None)
            extras["burned_captions"] = False

    temp_video.unlink(missing_ok=True)
    for p in frames_dir.glob("*"): p.unlink()
    try: frames_dir.rmdir()
    except OSError: pass
    for p in ov_dir.glob("*"): p.unlink()
    try: ov_dir.rmdir()
    except OSError: pass

    return slides_engine_used, extras


def _render_with_motion(img_paths, output_path: Path, W: int, H: int):
    clips_dir = OUTPUT_DIR / "clips"
    clips_dir.mkdir(exist_ok=True)
    clip_paths = []

    # Each xfade overlaps two clips, so it shortens the timeline by the
    # crossfade length. Pre-v3.2.0 that lost (n-1) x 0.4s (~26s on a
    # 67-slide video): slides drifted ahead of the narration and
    # "-shortest" cut the outro audio. Every clip except the last is now
    # rendered xfade seconds LONGER, so slide i still starts exactly at
    # the sum of the previous slides' audio durations.
    n_slides = len(img_paths)
    xfade = min(CROSSFADE_SEC, min(d for _, d in img_paths) * 0.4) if n_slides > 1 else 0.0

    for i, (img_path, base_dur) in enumerate(img_paths):
        dur = base_dur + (xfade if i < n_slides - 1 else 0.0)
        clip_path = clips_dir / f"clip_{i:05d}.mp4"
        frames = max(2, int(round(dur * RENDER_FPS)))
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='min(zoom+{(KEN_BURNS_MAX_ZOOM - 1) / frames:.6f},{KEN_BURNS_MAX_ZOOM})':"
              f"d={frames}:s={W}x{H}:fps={RENDER_FPS}")
        # NOTE: "veryfast" here, not "fast" - this per-slide clip gets
        # re-encoded again in the xfade merge below (the merge is the
        # actual final-quality pass, this is just an intermediate), so
        # spending extra CPU time on this pass buys no visible quality.
        # Running N times (once per slide) makes this the single biggest
        # lever on total render time - benchmarked in isolation (one
        # 15s/24fps 1080p Ken Burns clip): "fast" took 8.5s, "veryfast"
        # took 3.9s, ~55% faster, with no visible difference in the final
        # output since it's re-encoded again downstream.
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-vf", vf, "-t", f"{dur:.3f}",
            "-r", str(RENDER_FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", str(clip_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clip_paths.append((clip_path, dur))

    n = len(clip_paths)
    if n == 1:
        clip_paths[0][0].replace(output_path)
        return

    inputs = []
    for cp, _ in clip_paths:
        inputs += ["-i", str(cp)]

    filter_parts = []
    prev_label = "0:v"
    cumulative = clip_paths[0][1]
    for i in range(1, n):
        offset = max(0.0, cumulative - xfade)
        out_label = f"v{i}" if i < n - 1 else "vout"
        filter_parts.append(f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade:.3f}:offset={offset:.3f}[{out_label}]")
        prev_label = out_label
        cumulative = offset + clip_paths[i][1]

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(filter_parts), "-map", "[vout]", "-r", str(RENDER_FPS),
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "22", str(output_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─────────────────────────────────────────
# THUMBNAIL GENERATOR
# ─────────────────────────────────────────
def generate_thumbnail(title: str, headline: str, subtext: str, day_num: int, host_image=None) -> Path:
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), BRAND["bg"])
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 660, H], fill=(14, 20, 40))
    draw.rectangle([0, 0, 8, H], fill=BRAND["accent"])
    draw.rectangle([660, 0, W, H], fill=(8, 12, 24))

    for x in range(660, W, 60): draw.line([(x, 0), (x, H)], fill=BRAND["grid"], width=1)
    for y in range(0, H, 60): draw.line([(660, y), (W, y)], fill=BRAND["grid"], width=1)

    badge = f"DAY {day_num}/365"
    bf = _get_font(22, bold=True)
    bw = draw.textbbox((0, 0), badge, font=bf)[2]
    _draw_rounded_rect(draw, [W - bw - 40, 20, W - 20, 58], 8, fill=BRAND["accent"])
    draw.text((W - bw - 26, 26), badge, font=bf, fill=BRAND["bg"])

    draw.text((700, H - 54), CHANNEL_NAME, font=_get_font(26, bold=True), fill=BRAND["accent"])

    # Mobile-legibility cap: most viewers see this thumbnail shrunk to
    # ~120x68px in a feed, so more than ~3 short headline lines or a
    # wrapped multi-line subtext both turn into unreadable mush at that
    # size. Cap the headline to 3 lines and force the subtext onto a
    # single, slightly larger line instead of letting it wrap - a short,
    # bold hook reads far better small than a longer explanatory one.
    # v3.2.0: headline is FITTED to the left panel (it used to overflow
    # into the right panel on long words like "INFRASTRUCTURE"), and the
    # right panel shows the tool/topic name big instead of repeating the
    # full video title - YouTube already prints the title right under it.
    def _fit_lines(text, max_w, max_lines, start_px, min_px):
        words = text.split()
        for px in range(start_px, min_px - 1, -4):
            font = _get_font(px, bold=True)
            lines, cur = [], ""
            for w in words:
                trial = f"{cur} {w}".strip()
                if draw.textlength(trial, font=font) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in lines):
                return lines, font, px
        return lines[:max_lines], font, px

    headline_lines, hfont, hpx = _fit_lines(headline.upper(), 600, 3, 104, 52)
    line_h = int(hpx * 1.12)
    y = max(70, (H - len(headline_lines) * line_h) // 2)
    for line in headline_lines:
        draw.text((30, y), line, fill=(255, 255, 255), font=hfont)
        y += line_h

    draw.rectangle([30, y + 8, 260, y + 18], fill=BRAND["accent"])

    tool = (re.split(r"\s[—–]\s|:", title, maxsplit=1)[0] or title).strip().upper()
    if subtext and len(subtext) <= 40:
        tool = subtext.upper()
    host = None
    if host_image is not None:
        try:
            host = Image.open(host_image).convert("RGB")
        except Exception as exc:
            print(f"[THUMB] Presenter image not used: {exc}")
    if host is not None:
        # v3.3.0: the same presenter face on every thumbnail (channel
        # recognition in the feed). Face fills the right panel, the tool
        # name sits on a dark band at the bottom.
        pw, ph = W - 660, H
        hw, hh = host.size
        scale = max(pw / hw, ph / hh)
        host = host.resize((int(hw * scale) + 1, int(hh * scale) + 1), Image.LANCZOS)
        left = (host.width - pw) // 2
        host = host.crop((left, 0, left + pw, ph))
        fade = Image.linear_gradient("L").rotate(90, expand=True).resize((90, ph))
        mask = Image.new("L", (pw, ph), 255)
        mask.paste(fade.transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
        img.paste(host, (660, 0), mask)
        band = Image.new("RGBA", (pw, 150), (5, 8, 18, 215))
        img.paste(band, (660, H - 150), band)
        tool_lines, tfont, tpx = _fit_lines(tool, pw - 60, 2, 56, 30)
        ty = H - 150 + (150 - len(tool_lines) * int(tpx * 1.12)) // 2
        for line in tool_lines:
            draw.text((690, ty), line, fill=BRAND["accent"], font=tfont)
            ty += int(tpx * 1.12)
        _draw_rounded_rect(draw, [W - bw - 40, 20, W - 20, 58], 8, fill=BRAND["accent"])
        draw.text((W - bw - 26, 26), badge, font=bf, fill=BRAND["bg"])
    else:
        tool_lines, tfont, tpx = _fit_lines(tool, 540, 3, 78, 38)
        t_line_h = int(tpx * 1.15)
        ty = (H - len(tool_lines) * t_line_h) // 2
        for line in tool_lines:
            draw.text((690, ty), line, fill=BRAND["accent"], font=tfont)
            ty += t_line_h

    thumb_path = OUTPUT_DIR / "thumbnail.jpg"
    img.save(thumb_path, "JPEG", quality=95)
    return thumb_path


# ─────────────────────────────────────────
# YOUTUBE UPLOAD
# ─────────────────────────────────────────
def compute_publish_at():
    """Return a UTC RFC3339 string for today's publish hour in IST, or None
    to publish immediately. Falls back to None (immediate public) when the
    feature is off, the hour is invalid, the target is < 15 min away or
    already past (job ran late), or > 14 h away (job started after midnight
    - never hold a video back until the NEXT evening)."""
    raw = PUBLISH_AT_IST_HOUR_RAW
    if raw in ("", "off", "none", "false", "-1"):
        return None
    try:
        hour = int(raw)
    except ValueError:
        print(f"[UPLOAD] PUBLISH_AT_IST_HOUR={raw!r} is not a number - publishing immediately.")
        return None
    if not 0 <= hour <= 23:
        print(f"[UPLOAD] PUBLISH_AT_IST_HOUR={hour} out of range - publishing immediately.")
        return None
    now_ist = datetime.now(IST_TIMEZONE)
    target = now_ist.replace(hour=hour, minute=0, second=0, microsecond=0)
    wait_min = (target - now_ist).total_seconds() / 60
    if wait_min < 15 or wait_min > 14 * 60:
        print(f"[UPLOAD] Publish slot {target:%H:%M} IST is not usable "
              f"({wait_min:.0f} min away) - publishing immediately.")
        return None
    return target.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_video(service, video_file: Path, title: str, desc: str, tags: list, day_num: int,
                 contains_synthetic_media: bool = False) -> str:
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:100]
    desc = str(desc or "").strip()
    tags = sanitize_youtube_tags(tags)

    if not title or not tags:
        raise RuntimeError("Upload aborted: Invalid title or empty tags.")

    # Use YouTube's real per-tag cost (quote-wrapping adds +2 for any tag
    # with a space) so this pre-flight check matches sanitize_youtube_tags()
    # and actually catches an over-budget tag list before it reaches the API.
    total_tag_chars = sum(_youtube_tag_char_cost(tag) for tag in tags) + max(0, len(tags) - 1)
    if total_tag_chars > MAX_YOUTUBE_TAG_CHARS:
        raise RuntimeError(f"Upload aborted: Tags too long ({total_tag_chars} chars).")

    print(f"[UPLOAD] Using {len(tags)} tags ({total_tag_chars} characters). "
          f"containsSyntheticMedia={bool(contains_synthetic_media)}")

    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": "27",  # Education
            "defaultLanguage": "en-US",
            "defaultAudioLanguage": "en-US",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            # YouTube's "altered or synthetic content" disclosure. Required
            # when a realistic AI-generated person appears on screen; YouTube
            # labels undisclosed realistic AI content automatically anyway.
            "containsSyntheticMedia": bool(contains_synthetic_media),
        },
    }

    publish_at = compute_publish_at()
    if publish_at:
        body["status"]["privacyStatus"] = "private"   # required by YouTube for publishAt
        body["status"]["publishAt"] = publish_at
        print(f"[UPLOAD] Scheduled: private now, YouTube will make it PUBLIC at {publish_at} "
              f"({PUBLISH_AT_IST_HOUR_RAW}:00 IST).")
    else:
        print("[UPLOAD] Publishing immediately (public).")

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_file), chunksize=10*1024*1024, resumable=True),
    )

    response = None
    print("[UPLOAD] Uploading video...")

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[UPLOAD] {int(status.progress() * 100)}%", end="\r", flush=True)
        except ResumableUploadError:
            raise

    print("\n[UPLOAD] Upload complete.")
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube returned no video ID.")
    return video_id


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    hh, rem_ms = divmod(total_ms, 3_600_000)
    mm, rem_ms = divmod(rem_ms, 60_000)
    ss, ms = divmod(rem_ms, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def build_captions_srt(slides: list, output_path: Path) -> Path:
    """Real English closed captions built from the exact same slide
    timeline as the video (slides = [(kind, text, duration, act_name),
    ...] from generate_synced_narration()) - one cue per spoken slide,
    timed to the real audio. This is segment-level accuracy (one cue per
    slide's narration chunk, a few seconds to ~15s each), not word-level
    karaoke-style timing - ElevenLabs' character timestamps aren't
    retained past duration computation, only the per-slide durations
    are. That's still meaningfully more accurate than YouTube's own
    auto-captions (which mishear technical/DevOps terms constantly) and
    it's free since we already have the real timing. Structural
    (silent) slides - title/chapter/cta/outro - have no speech, so they
    get no cue.
    """
    cues = []
    t = 0.0
    idx = 1
    for kind, text, duration, act_name in slides:
        clean = re.sub(r"\s+", " ", text or "").strip()
        if kind in SPOKEN_SLIDE_KINDS and clean and duration > 0:
            start = _srt_timestamp(t)
            end = _srt_timestamp(t + duration)
            cues.append(f"{idx}\n{start} --> {end}\n{clean}\n")
            idx += 1
        t += duration

    output_path.write_text("\n".join(cues), encoding="utf-8")
    return output_path


def upload_captions(service, video_id: str, srt_path: Path):
    """Non-fatal by design, same as set_thumbnail()/add_video_to_playlist()
    below - if the OAuth token doesn't have the youtube.force-ssl scope
    yet (see the SCOPES comment above), this 403s and the run still
    completes; you just don't get captions on that video until you
    re-authorize."""
    try:
        service.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": "en",
                    "name": "English",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(str(srt_path), mimetype="application/octet-stream"),
        ).execute()
        print("[UPLOAD] English captions uploaded.")
    except Exception as e:
        if "insufficient" in str(e).lower() and "scope" in str(e).lower():
            print("[UPLOAD] Captions skipped: token is missing the youtube.force-ssl scope. "
                  "Run reauth_youtube.py once locally and update the GOOGLE_CREDENTIALS secret.")
        else:
            print(f"[UPLOAD] Caption upload skipped: {e}")


def set_thumbnail(service, video_id: str, thumb_path: Path):
    try:
        service.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
        ).execute()
        print("[UPLOAD] Thumbnail set.")
    except Exception as e:
        print(f"[UPLOAD] Thumbnail skipped: {e}")


def add_video_to_playlist(service, video_id: str, playlist_id: str):
    try:
        service.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        ).execute()
        print(f"[UPLOAD] Added to playlist {playlist_id}.")
    except Exception as e:
        print(f"[UPLOAD] Playlist add skipped: {e}")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="DevOps Genius Zone YouTube Bot v3.3.0")
    parser.add_argument("day", type=int, nargs="?", default=None, help="Force a day number from 1 to 365.")
    parser.add_argument("--test", action="store_true", help="Build the video but skip YouTube upload.")
    parser.add_argument("--playlist", default=None, help="Optional YouTube playlist ID.")
    args = parser.parse_args()

    logs = load_log()
    if args.day is not None:
        if args.day < 1: raise ValueError("Day must be at least 1.")
        day_num = args.day
    else:
        # Only count uploads that belong to the CURRENT series (SERIES_NAME).
        # Older log entries from a previous topic curriculum have no
        # "series" field (or a different one) and are simply skipped, so a
        # new series always starts at Day 1 regardless of how many videos
        # were uploaded under the old curriculum.
        series_uploads = [
            e for e in logs
            if e.get("video_id") and e.get("video_id") != "TEST_MODE_NO_UPLOAD"
            and e.get("series") == SERIES_NAME
        ]
        day_num = len(series_uploads) + 1

    if day_num > 365: day_num = ((day_num - 1) % 365) + 1
    topic = TOPICS_365[day_num - 1]
    next_topic = TOPICS_365[day_num % 365]  # wraps 365 -> index 0 automatically
    today_str = datetime.now(IST_TIMEZONE).date().isoformat()

    print(f"\n{'=' * 64}")
    print(f"  {CHANNEL_NAME} | Day {day_num} of 365")
    print(f"  Date  : {today_str} IST")
    print(f"  Topic : {topic}")
    print(f"  Next  : {next_topic}")
    print(f"{'=' * 64}\n")

    content = generate_content(topic, day_num, next_topic)

    if day_num in MANUAL_SEO_OVERRIDES:
        override = MANUAL_SEO_OVERRIDES[day_num]
        print(f"[SEO] Manual SEO override active for Day {day_num} - using hand-tuned title/description/tags.")
        content = dict(content)  # don't mutate the generator's return value
        content["title"] = override["title"]
        content["description"] = override["description"]
        content["tags"] = override["tags"]

    title = str(content.get("title", topic)).strip()
    description = str(content.get("description", "")).strip()
    script_text = str(content.get("script", "")).strip()

    if not script_text: raise RuntimeError("The generated script is empty.")

    raw_tags = content.get("tags", []) or []
    raw_tags.extend(FALLBACK_TAGS)
    tags = sanitize_youtube_tags(raw_tags)
    if not tags: raise RuntimeError("No valid YouTube tags were generated.")

    thumbnail_headline = str(content.get("thumbnail_headline", title[:40].upper())).strip()
    thumbnail_subtext = str(content.get("thumbnail_subtext", "Full guide for DevOps engineers")).strip()

    word_count = _spoken_word_count(script_text)
    print(f"[CONTENT] Title          : {title}")
    print(f"[CONTENT] Script words   : {word_count:,}")
    print(f"[CONTENT] Thumbnail text : {thumbnail_headline}")
    print(f"[CONTENT] Tags           : {len(tags)}")

    audio_file = OUTPUT_DIR / "audio.mp3"
    print("[TTS] Generating audio + slide timing...")
    set_visual_context(topic, day_num, next_topic)
    slides, tts_engine_used = generate_synced_narration(script_text, audio_file)
    duration = _ffprobe_duration(audio_file)
    print(f"[TTS] Duration: {duration:.1f}s ({duration / 60:.1f} min) via {tts_engine_used}")

    # Real chapter timestamps, measured from the actual slide/audio
    # timeline we just built - replaces the [[CHAPTERS]] placeholder the
    # AI/offline generator left in the description. If for some reason
    # the placeholder isn't present (e.g. a MANUAL_SEO_OVERRIDES entry
    # with a hand-written description), the description is left exactly
    # as authored - real chapters are never force-inserted into
    # hand-tuned copy.
    real_chapters = compute_chapter_timestamps_from_slides(slides)
    if "[[CHAPTERS]]" in description:
        description = description.replace("[[CHAPTERS]]", f"CHAPTERS\n{real_chapters}")
    print("[SEO] Chapter timestamps computed from real audio/slide timing.")

    # v3.3.0: start the AI presenter lip-sync on Kaggle's GPU NOW, so it
    # renders while this runner builds the slides; build_video() waits for it.
    host_future, host_pool = None, None
    if HOST_ENABLED and not HOST_IMAGE.exists():
        print(f"[HOST] {HOST_IMAGE} not found - no AI presenter (run the 'Generate AI presenter' workflow once).")
    elif HOST_ENABLED:
        try:
            import host_lipsync
            ok, why = host_lipsync.kaggle_ready()
            if ok:
                host_segments = select_host_segments(slides)
                secs = sum(x["end"] - x["start"] for x in host_segments)
                print(f"[HOST] Presenter on {len(host_segments)} segment(s), {secs:.0f}s (mode={HOST_MODE}) - "
                      f"rendering on Kaggle in the background.")
                from concurrent.futures import ThreadPoolExecutor
                host_pool = ThreadPoolExecutor(max_workers=1)
                host_future = host_pool.submit(host_lipsync.render_host_clips, audio_file, host_segments,
                                               HOST_IMAGE, OUTPUT_DIR / "host_job", HOST_TIMEOUT_MIN)
            else:
                print(f"[HOST] No AI presenter today: {why}.")
        except Exception as exc:
            print(f"[HOST] No AI presenter today: {exc}")

    video_file = OUTPUT_DIR / "video.mp4"
    slides_engine_used, video_extras = build_video(slides, audio_file, video_file, day_num=day_num, topic=topic,
                                                   host_future=host_future)
    if host_pool is not None:
        host_pool.shutdown(wait=False, cancel_futures=True)

    disclosure_env = os.environ.get("SYNTHETIC_MEDIA_DISCLOSURE", "auto").strip().lower()
    host_used = video_extras.get("host_segments", 0) > 0
    contains_synthetic = host_used if disclosure_env == "auto" else disclosure_env in ("1", "true", "yes", "on")
    if host_used and "AI-generated avatar" not in description:
        description = description.rstrip() + (
            "\n\nTransparency: the on-screen presenter is an AI-generated avatar and the narration is "
            "AI text-to-speech. The incident scenarios are illustrative unless stated otherwise."
        )

    size_mb = video_file.stat().st_size / (1024 * 1024)
    print(f"[VIDEO] Done: {video_file} ({size_mb:.1f} MB)")

    thumbnail_path = generate_thumbnail(title, thumbnail_headline, thumbnail_subtext, day_num,
                                        host_image=HOST_IMAGE if host_used else None)
    print(f"[THUMB] Saved: {thumbnail_path}")

    captions_path = OUTPUT_DIR / "captions_en.srt"
    build_captions_srt(slides, captions_path)
    print(f"[CAPTIONS] Saved: {captions_path}")

    if args.test:
        video_id = "TEST_MODE_NO_UPLOAD"
        print("[TEST] Upload skipped because test mode is active.")
    else:
        service = get_authenticated_service()
        video_id = upload_video(service, video_file, title, description, tags, day_num,
                                contains_synthetic_media=contains_synthetic)
        set_thumbnail(service, video_id, thumbnail_path)
        upload_captions(service, video_id, captions_path)
        if args.playlist:
            add_video_to_playlist(service, video_id, args.playlist)
        if SERIES_PLAYLIST_ID and SERIES_PLAYLIST_ID != args.playlist:
            add_video_to_playlist(service, video_id, SERIES_PLAYLIST_ID)

    log_entry = {
        "day": day_num, "series": SERIES_NAME, "date": today_str, "topic": topic, "title": title,
        "video_id": video_id,
        "url": f"https://youtube.com/watch?v={video_id}" if video_id != "TEST_MODE_NO_UPLOAD" else None,
        "duration_min": round(duration / 60, 1), "word_count": word_count, "tags": tags,
        "ai_generated": str(content.get("_source", "")).startswith("gemini"),
        "content_source": content.get("_source", "unknown"),
        "tts_engine": tts_engine_used,
        "slides_engine": slides_engine_used,
        "terminal_scenes": video_extras.get("terminal_scenes", 0),
        "host_seconds": round(video_extras.get("host_seconds", 0.0), 1),
        "burned_captions": video_extras.get("burned_captions", False),
        "contains_synthetic_media": contains_synthetic,
        "test_mode": args.test,
    }
    save_log_entry(log_entry)

    print(f"\n{'=' * 64}")
    print(f"  Day {day_num} complete!")
    if args.test: print("  Upload: skipped")
    else: print(f"  Video ID: {video_id}")
    print(f"{'=' * 64}\n")

if __name__ == "__main__":
    main()
