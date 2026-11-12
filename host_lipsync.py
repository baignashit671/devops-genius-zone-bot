#!/usr/bin/env python3
"""
host_lipsync.py - renders the AI presenter's talking-head clips on a free
Kaggle GPU, driven from the daily GitHub Actions job (DevOps Genius Zone v3.3.0).

Flow (all through the official `kaggle` CLI):
  1. cut the chosen narration segments out of audio.mp3 (16 kHz mono WAV)
  2. upload them + assets/host.png + manifest.json as a NEW VERSION of a
     private Kaggle dataset (created on the first run), wait until "ready"
  3. push kaggle/sadtalker_kernel.py as a private GPU script kernel with that
     dataset attached (the run id is baked into the code, so a stale dataset
     version is detected instead of silently animating yesterday's audio)
  4. poll the kernel until it finishes, download seg_XX.mp4 + result.json
Any failure raises; devops_365_bot.py then ships the video without the
presenter, exactly like the other fallbacks.

Auth: KAGGLE_USERNAME + KAGGLE_API_TOKEN (new-style token from
kaggle.com/settings -> API -> Generate New Token) or legacy KAGGLE_KEY.
"""
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL_TEMPLATE = HERE / "kaggle" / "sadtalker_kernel.py"
DATASET_SLUG = os.environ.get("HOST_KAGGLE_DATASET", "devops-host-inputs").strip()
KERNEL_SLUG = os.environ.get("HOST_KAGGLE_KERNEL", "devops-host-lipsync").strip()
ACCELERATOR = os.environ.get("HOST_KAGGLE_ACCELERATOR", "NvidiaTeslaT4").strip()
HOST_SIZE = os.environ.get("HOST_FACE_SIZE", "256").strip()          # 256 (fast) or 512 (sharper, ~3x slower)
HOST_ENHANCER = os.environ.get("HOST_ENHANCER", "gfpgan").strip()    # gfpgan | none
PANEL_W, PANEL_H = 560, 720                                          # matches HOST_PANEL_CINEMATIC aspect


def _log(msg):
    print(f"[HOST] {msg}", flush=True)


def kaggle_ready() -> tuple:
    """(ok, reason). Checked before any work is started."""
    if not os.environ.get("KAGGLE_USERNAME", "").strip():
        return False, "KAGGLE_USERNAME is not set"
    if not (os.environ.get("KAGGLE_API_TOKEN", "").strip() or os.environ.get("KAGGLE_KEY", "").strip()):
        return False, "neither KAGGLE_API_TOKEN nor KAGGLE_KEY is set"
    if shutil.which("kaggle") is None:
        return False, "the kaggle CLI is not installed (pip install kaggle six)"
    if not KERNEL_TEMPLATE.exists():
        return False, f"{KERNEL_TEMPLATE} is missing"
    return True, ""


def _kaggle(args, timeout=300, check=True) -> str:
    env = dict(os.environ)
    if not env.get("KAGGLE_API_TOKEN"):
        env.pop("KAGGLE_API_TOKEN", None)
    if not env.get("KAGGLE_KEY"):
        env.pop("KAGGLE_KEY", None)
    res = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=timeout, env=env)
    out = (res.stdout or "") + (res.stderr or "")
    if check and res.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args[:2])} failed ({res.returncode}): {out.strip()[-800:]}")
    return out


def prepare_host_image(src: Path, dest: Path):
    """Center-crop the presenter photo to the panel aspect and resize. The same
    file is uploaded every day, so the face is always identical."""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    target = PANEL_W / PANEL_H
    if w / h > target:            # too wide -> crop sides
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:                         # too tall -> keep the top (face), crop the bottom
        nh = int(w / target)
        im = im.crop((0, 0, w, nh))
    im.resize((PANEL_W, PANEL_H), Image.LANCZOS).save(dest)


def _cut_wav(audio: Path, start: float, end: float, dest: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{max(0.2, end - start):.3f}", "-i", str(audio),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _upload_dataset(folder: Path, user: str, run_id: str):
    ds_id = f"{user}/{DATASET_SLUG}"
    (folder / "dataset-metadata.json").write_text(json.dumps({
        "title": DATASET_SLUG, "id": ds_id, "licenses": [{"name": "CC0-1.0"}],
    }))
    try:
        _kaggle(["datasets", "version", "-p", str(folder), "-m", f"run {run_id}", "-q", "-d"], timeout=600)
        _log(f"Uploaded a new version of the private dataset {ds_id}.")
    except RuntimeError as exc:
        if not re.search(r"404|not found|does not exist|NotFound", str(exc), re.I):
            raise
        _log(f"Dataset {ds_id} does not exist yet - creating it (private).")
        _kaggle(["datasets", "create", "-p", str(folder), "-q"], timeout=600)
    deadline = time.time() + 900
    while time.time() < deadline:
        st = _kaggle(["datasets", "status", ds_id], timeout=120, check=False).strip().lower()
        if "ready" in st:
            return ds_id
        if "error" in st or "failed" in st:
            raise RuntimeError(f"dataset processing failed: {st[-300:]}")
        time.sleep(15)
    raise TimeoutError("Kaggle dataset was not ready within 15 minutes")


def _push_kernel(folder: Path, user: str, ds_id: str, run_id: str, timeout_sec: int) -> str:
    k_id = f"{user}/{KERNEL_SLUG}"
    code = KERNEL_TEMPLATE.read_text(encoding="utf-8")
    code = (code.replace("__RUN_ID__", run_id)
                .replace("__HOST_SIZE__", HOST_SIZE if HOST_SIZE in ("256", "512") else "256")
                .replace("__HOST_ENHANCER__", HOST_ENHANCER or "none"))
    (folder / "sadtalker_kernel.py").write_text(code, encoding="utf-8")
    (folder / "kernel-metadata.json").write_text(json.dumps({
        "id": k_id, "title": KERNEL_SLUG, "code_file": "sadtalker_kernel.py",
        "language": "python", "kernel_type": "script", "is_private": True,
        "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [ds_id], "competition_sources": [], "kernel_sources": [], "model_sources": [],
    }, indent=2))
    args = ["kernels", "push", "-p", str(folder), "-t", str(timeout_sec)]
    if ACCELERATOR:
        args += ["--accelerator", ACCELERATOR]
    out = _kaggle(args, timeout=300)
    if re.search(r"error|invalid|not valid", out, re.I) and not re.search(r"successfully", out, re.I):
        raise RuntimeError(f"kernel push rejected: {out.strip()[-500:]}")
    _log(f"Kernel {k_id} pushed ({ACCELERATOR or 'default accelerator'}).")
    return k_id


def _wait_kernel(k_id: str, deadline: float):
    time.sleep(30)
    last = ""
    while time.time() < deadline:
        out = _kaggle(["kernels", "status", k_id], timeout=120, check=False)
        m = re.search(r'has status "([^"]+)"', out)
        st = (m.group(1) if m else out.strip()).lower()
        if st != last:
            _log(f"Kaggle kernel status: {st}")
            last = st
        if "complete" in st:
            return
        if "error" in st or "cancel" in st:
            raise RuntimeError(f"Kaggle kernel ended with '{st}': {out.strip()[-600:]}")
        time.sleep(30)
    raise TimeoutError("Kaggle kernel did not finish in time")


def render_host_clips(audio_path, segments: list, host_image, workdir, timeout_min: float = 45) -> list:
    """segments: [{"id", "start", "end"}, ...] on the final narration timeline.
    Returns [{"path", "start", "end"}] for every clip that came back valid."""
    ok, why = kaggle_ready()
    if not ok:
        raise RuntimeError(f"Kaggle not configured: {why}")
    if not segments:
        return []
    audio_path, host_image, workdir = Path(audio_path), Path(host_image), Path(workdir)
    deadline = time.time() + timeout_min * 60
    user = os.environ["KAGGLE_USERNAME"].strip()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

    shutil.rmtree(workdir, ignore_errors=True)
    ds_dir, k_dir, out_dir = workdir / "dataset", workdir / "kernel", workdir / "output"
    for d in (ds_dir, k_dir, out_dir):
        d.mkdir(parents=True)

    prepare_host_image(host_image, ds_dir / "host.png")
    manifest = {"run_id": run_id, "image": "host.png", "segments": []}
    for seg in segments:
        f = ds_dir / f"{seg['id']}.wav"
        _cut_wav(audio_path, seg["start"], seg["end"], f)
        manifest["segments"].append({"id": seg["id"], "file": f.name, "duration": round(seg["end"] - seg["start"], 3)})
    (ds_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    total = sum(s["duration"] for s in manifest["segments"])
    _log(f"{len(segments)} segment(s), {total:.0f}s of presenter video to render (run {run_id}).")

    ds_id = _upload_dataset(ds_dir, user, run_id)
    k_id = _push_kernel(k_dir, user, ds_id, run_id, timeout_sec=int(max(600, deadline - time.time())))
    _wait_kernel(k_id, deadline)

    _kaggle(["kernels", "output", k_id, "-p", str(out_dir), "-o", "-q"], timeout=900)
    res_file = out_dir / "result.json"
    if not res_file.exists():
        raise RuntimeError("Kaggle kernel produced no result.json")
    result = json.loads(res_file.read_text())
    if result.get("run_id") != run_id:
        raise RuntimeError(f"stale kernel output (run {result.get('run_id')}, expected {run_id})")
    for err in result.get("errors", []):
        _log(f"segment {err.get('id')} failed on Kaggle: {err.get('error', '')[:300]}")

    by_id = {s["id"]: s for s in segments}
    clips = []
    for c in result.get("clips", []):
        p = out_dir / c["file"]
        seg = by_id.get(c["id"])
        if not seg or not p.exists():
            continue
        want = seg["end"] - seg["start"]
        got = _duration(p)
        if abs(got - want) > max(0.6, want * 0.05):
            _log(f"{c['id']}: clip is {got:.2f}s but narration is {want:.2f}s - skipped (lip-sync would drift).")
            continue
        clips.append({"path": p, "start": seg["start"], "end": seg["end"]})
    _log(f"{len(clips)}/{len(segments)} presenter clip(s) ready ({result.get('seconds', '?')}s on Kaggle).")
    return clips
