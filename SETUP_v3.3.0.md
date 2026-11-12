# DevOps Genius Zone v3.3.0: setup guide

This release adds two phases:

- **Phase 1:** the "Production Incident File" script format, the Kokoro male voice, animated terminal scenes and burned-in word-by-word captions.
- **Phase 2:** an AI presenter with the same face in every video.

Everything is free. Phase 1 works as soon as you deploy. Phase 2 also needs a Kaggle account and a presenter image.

## 1. Files to put in the repo

| File | Where |
|---|---|
| `devops_365_bot.py` | repo root (replaces the old one; keep `main.py` identical if you still keep it) |
| `host_lipsync.py` | repo root (new) |
| `kaggle/sadtalker_kernel.py` | `kaggle/` folder (new) |
| `kaggle/host_image_kernel.py` | `kaggle/` folder (new) |
| `tools/generate_host_candidates.py` | `tools/` folder (new) |
| `stories.yaml` | repo root (new; fill it with your real incidents) |
| `requirements.txt` | repo root (replaces) |
| `daily_us_9pm_ist.yml` | `.github/workflows/` (replaces) |
| `generate-host-image.yml` | `.github/workflows/` (new) |

## 2. Phase 1: works right away

- **Voice:** Kokoro `am_michael`, offline on the runner. The roughly 350 MB model downloads once from the kokoro-onnx GitHub release and is then cached. If Kokoro fails, edge_tts takes over automatically.
- **Script:** each episode follows one incident: the incident, then the wrong first move, then debug → root cause → fix, then production best practices plus an interview answer.
  - Gemini adds `[[TERMINAL]]` blocks, which are shown on screen and never read aloud.
  - A second Gemini pass reviews technical accuracy. Its result is only kept if the structure and length stay intact.
- **Captions:** burned into the video with the current word in yellow. The `.srt` upload stays as before.
- **`stories.yaml`:** write your real production incidents here, 2–4 lines each, with tags. When the tags match the day's topic, the script tells that story as "a real incident from our team".
  - With no matching story, the script tells no first-person story at all.
  - This is what makes each video original, which YouTube's "inauthentic content" policy rewards.

## 3. Phase 2: AI presenter (one-time setup, about 15 minutes)

1. **Create a Kaggle account** at kaggle.com. Verify your phone number (Settings → Phone verification), because GPU and internet in notebooks need it.
2. **Get an API token** from kaggle.com → Settings → API → **Generate New Token**, and copy it.
3. **Add GitHub secrets** (repo → Settings → Secrets and variables → Actions):
   - `KAGGLE_USERNAME`: your Kaggle username
   - `KAGGLE_API_TOKEN`: the token from step 2
   - If you only have a legacy `kaggle.json` key, use `KAGGLE_KEY` instead of the token.
4. **Generate the face.** Go to Actions → **Generate AI presenter portrait (run once)** → Run workflow.
   - Leave "appearance" blank for the default: a fictional 34-year-old American male engineer with short dark hair and a navy t-shirt.
   - Or describe your own look.
   - The run takes about 10–15 minutes and uploads an artifact with 8 candidates plus `contact_sheet.jpg`.
5. **Pick one portrait.** Choose one that faces the camera with the mouth closed, no glasses, and no hands near the face. Commit it as **`assets/host.png`** (Add file → Upload files → path `assets/host.png`).
   - That exact file is reused every day, so the face never changes.
   - Don't use a photo of a real person or anything that resembles a celebrity.
6. **Test it.** Actions → daily workflow → Run workflow with `test_mode=true`. Download the `video-day-…` artifact and check the presenter.

### How it runs every day

- As soon as the audio is ready, the bot uploads the presenter segments to a **private** Kaggle dataset and starts a private GPU kernel (T4). That kernel animates the face with SadTalker, which is Apache-2.0.
- The kernel works while the runner renders the slides. The bot then composites the presenter into the right-hand panel of the hook, the chapter openers and the outro.
- **GPU budget:** `HOST_MODE=key` (the default) puts about 2–4 minutes of presenter on screen per video. That should take roughly 10–20 minutes of Kaggle GPU time.
  - Kaggle doesn't publish its weekly GPU quota; users commonly report about 30 hours a week. Check yours under Settings.
  - `host_mode=all` (a workflow input) puts the presenter on every explanation slide, which uses more GPU.
- **Fail-safe:** if anything fails (quota used up, Kaggle down, no face detected, timeout after `HOST_TIMEOUT_MIN=45`), the video still ships without the presenter.
- **Disclosure:** when the presenter is in the video, the upload sets YouTube's **altered/synthetic content** flag (`containsSyntheticMedia=true`) and adds a transparency line to the description. YouTube requires this for realistic AI people, and since May 2026 it auto-labels undisclosed AI content anyway.

### Knobs (workflow `env:`)

| Variable | Default | Meaning |
|---|---|---|
| `KOKORO_VOICE` | `am_michael` | Other male voices: `am_adam`, `am_eric`, `am_liam`, `am_onyx`, `am_fenrir`, `am_puck`, `am_echo` |
| `KOKORO_SPEED` | `1.0` | 0.9–1.15 |
| `HOST_FACE_SIZE` | `256` | `512` = sharper face, about 3× more GPU time |
| `HOST_ENHANCER` | `gfpgan` | `none` = faster, softer face |
| `HOST_MAX_SECONDS` | `240` | Cap on presenter seconds per video |
| `BURN_CAPTIONS` | `true` | `false` turns off the burned-in captions |
| `SCRIPT_REVIEW` | `true` | Technical review pass by Gemini |
| `SYNTHETIC_MEDIA_DISCLOSURE` | `auto` | `auto` = on whenever the presenter is used |

### Reading the run log

```
[HOST] Presenter on 4 segment(s), 150s (mode=key) - rendering on Kaggle in the background.
[HOST] Kaggle kernel status: running ... complete
[HOST] 4/4 presenter clip(s) ready
[HOST] AI presenter on screen in 4 segment(s), 150s total.
```

`upload_log.json` now also records these fields for each video: `terminal_scenes`, `host_seconds`, `burned_captions` and `contains_synthetic_media`.

## 4. Honest limits

- **Look:** SadTalker animates one photo, so the head mostly stays still and the lips, eyes and expression move. It looks good in a presenter panel but not identical to a filmed human. Use `HOST_FACE_SIZE=512` for a sharper face.
- **Scripts:** Gemini scripts are reviewed by a second pass, but nobody has checked the commands by hand. Skim the video in the private window before 9 PM when you can.
- **Kaggle:** free-tier limits and terms can change. Check them on your account.
