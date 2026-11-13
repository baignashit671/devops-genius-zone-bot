#!/usr/bin/env python3
"""
DevOps Genius Zone - AI presenter lip-sync kernel (runs on a free Kaggle GPU)
=============================================================================
Pushed by host_lipsync.py from the daily GitHub Actions job. It reads the
presenter image + narration audio segments from the attached private Kaggle
dataset, animates the SAME face for every segment with SadTalker
(Apache-2.0), and writes seg_XX.mp4 files + result.json to /kaggle/working,
where host_lipsync.py downloads them.

Placeholders below are filled in by host_lipsync.py on every push. The
script can also run locally for testing:
    SADTALKER_DIR=./SadTalker INPUT_DIR=./in OUTPUT_DIR=./out SKIP_SETUP=1 ALLOW_CPU=1 \
        python sadtalker_kernel.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

RUN_ID = "__RUN_ID__"
HOST_SIZE = int("__HOST_SIZE__") if "__HOST_SIZE__".isdigit() else 256        # 256 or 512 face model
HOST_ENHANCER = "__HOST_ENHANCER__" if not "__HOST_ENHANCER__".startswith("__") else "gfpgan"

SADTALKER_DIR = os.environ.get("SADTALKER_DIR", "/tmp/SadTalker")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/kaggle/working")
SKIP_SETUP = os.environ.get("SKIP_SETUP", "") == "1"
ALLOW_CPU = os.environ.get("ALLOW_CPU", "") == "1"
REPO = "https://github.com/OpenTalker/SadTalker"
CKPT_URLS = {
    "checkpoints/mapping_00109-model.pth.tar": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar",
    "checkpoints/mapping_00229-model.pth.tar": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar",
    "checkpoints/SadTalker_V0.0.2_256.safetensors": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors",
    "checkpoints/SadTalker_V0.0.2_512.safetensors": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_512.safetensors",
    "gfpgan/weights/alignment_WFLW_4HG.pth": "https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth",
    "gfpgan/weights/detection_Resnet50_Final.pth": "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
    "gfpgan/weights/GFPGANv1.4.pth": "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
    "gfpgan/weights/parsing_parsenet.pth": "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth",
}
PIP_PACKAGES = [
    "face_alignment", "imageio>=2.31", "imageio-ffmpeg>=0.5", "librosa", "resampy", "pydub",
    "kornia", "yacs", "basicsr", "facexlib", "gfpgan", "av", "safetensors", "joblib", "scikit-image",
    "audioop-lts; python_version >= '3.13'",   # Python 3.13 removed audioop; pydub needs it (Kaggle is on 3.13)
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write_result(payload):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload["run_id"] = RUN_ID
    with open(os.path.join(OUTPUT_DIR, "result.json"), "w") as f:
        json.dump(payload, f, indent=2)


def sh(cmd, **kw):
    log("$ " + (cmd if isinstance(cmd, str) else " ".join(cmd)))
    subprocess.run(cmd, check=True, shell=isinstance(cmd, str), **kw)


def find_input_dir():
    if os.environ.get("INPUT_DIR"):
        return os.environ["INPUT_DIR"]
    hits = glob.glob("/kaggle/input/**/manifest.json", recursive=True)
    if not hits:
        raise RuntimeError("manifest.json not found under /kaggle/input - is the dataset attached?")
    return os.path.dirname(hits[0])


# ---------------------------------------------------------------- setup
def setup():
    if not os.path.isdir(SADTALKER_DIR):
        sh(["git", "clone", "--depth", "1", REPO, SADTALKER_DIR])
    sh([sys.executable, "-m", "pip", "install", "-q", *PIP_PACKAGES])
    for rel, url in CKPT_URLS.items():
        if HOST_SIZE != 512 and "512" in rel:
            continue
        if HOST_ENHANCER != "gfpgan" and rel.endswith("GFPGANv1.4.pth"):
            continue
        dest = os.path.join(SADTALKER_DIR, rel)
        if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        sh(["curl", "-sSL", "--retry", "3", "-o", dest, url])


def apply_patches():
    """SadTalker (2023) vs today's torch/numpy/torchvision. Each fix is
    idempotent and was verified against a full local CPU run."""
    import torchvision.transforms as T
    shim = os.path.join(os.path.dirname(T.__file__), "functional_tensor.py")
    if not os.path.exists(shim):  # basicsr imports a module torchvision removed in 0.17
        with open(shim, "w") as f:
            f.write("from torchvision.transforms.functional import *\n"
                    "from torchvision.transforms.functional import rgb_to_grayscale\n")
    subs = [
        (r"\bnp\.float\b(?![\d_])", "np.float64"),
        (r"\bnp\.int\b(?![\d_])", "np.int64"),
        (r"\bnp\.bool\b(?![\d_])", "np.bool_"),
        (r"\bnp\.float_\b", "np.float64"),
        (r"\bnp\.complex_\b", "np.complex128"),
        (r"\bnp\.NaN\b", "np.nan"),
        (r"\bnp\.Inf\b", "np.inf"),
        # numpy 2 moved VisibleDeprecationWarning to np.exceptions
        (r"\bnp\.VisibleDeprecationWarning\b", "getattr(np, 'exceptions', np).VisibleDeprecationWarning"),
    ]
    for dp, _, fs in os.walk(os.path.join(SADTALKER_DIR, "src")):
        for fn in fs:
            if fn.endswith(".py"):
                p = os.path.join(dp, fn)
                s = open(p).read()
                o = s
                for a, b in subs:
                    s = re.sub(a, b, s)
                if s != o:
                    open(p, "w").write(s)
    exact = [
        # numpy 2: POS() returns t as a (2,1) array and s as a 1-element array
        ("src/face3d/util/preprocess.py",
         "    t, s = POS(lm5p.transpose(), lm3D.transpose())\n    s = rescale_factor/s\n",
         "    t, s = POS(lm5p.transpose(), lm3D.transpose())\n    t = np.ravel(t).astype(np.float64)\n"
         "    s = np.float64(rescale_factor / np.ravel(s)[0])\n"),
        ("src/utils/preprocess.py",
         "np.array([float(item) for item in np.hsplit(trans_params, 5)])",
         "np.array([float(np.ravel(item)[0]) for item in np.hsplit(trans_params, 5)])"),
        ("src/face3d/util/preprocess.py",
         "trans_params = np.array([w0, h0, s, t[0], t[1]])",
         "trans_params = np.array([w0, h0, s, float(np.ravel(t)[0]), float(np.ravel(t)[1])])"),
    ]
    for rel, a, b in exact:
        p = os.path.join(SADTALKER_DIR, rel)
        s = open(p).read()
        if a in s:
            open(p, "w").write(s.replace(a, b))


# ---------------------------------------------------------------- render
def render(input_dir):
    import torch
    with open(os.path.join(input_dir, "manifest.json")) as f:
        manifest = json.load(f)
    if manifest.get("run_id") != RUN_ID:
        raise RuntimeError(f"dataset is stale: manifest run_id={manifest.get('run_id')} expected {RUN_ID}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" and not ALLOW_CPU:
        raise RuntimeError("No GPU in this Kaggle session (turn on GPU / check your weekly quota).")
    log(f"device={device} size={HOST_SIZE} enhancer={HOST_ENHANCER} segments={len(manifest['segments'])}")

    os.chdir(SADTALKER_DIR)
    sys.path.insert(0, SADTALKER_DIR)
    from src.utils.preprocess import CropAndExtract
    from src.test_audio2coeff import Audio2Coeff
    from src.facerender.animate import AnimateFromCoeff
    from src.generate_batch import get_data
    from src.generate_facerender_batch import get_facerender_data
    from src.utils.init_path import init_path

    paths = init_path("./checkpoints", os.path.join(SADTALKER_DIR, "src/config"), HOST_SIZE, False, "full")
    preprocess_model = CropAndExtract(paths, device)
    audio_to_coeff = Audio2Coeff(paths, device)
    animate = AnimateFromCoeff(paths, device)

    work = "/tmp/st_work"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    pic = os.path.join(input_dir, manifest["image"])
    first_dir = os.path.join(work, "first_frame")
    os.makedirs(first_dir)
    log("3DMM extraction of the presenter image (once)")
    first_coeff, crop_pic, crop_info = preprocess_model.generate(pic, first_dir, "full", source_image_flag=True, pic_size=HOST_SIZE)
    if first_coeff is None:
        raise RuntimeError("No face found in the presenter image.")

    out_dir = OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    done, errors = [], []
    batch = 8 if device == "cuda" else 2
    for seg in manifest["segments"]:
        t0 = time.time()
        try:
            seg_dir = os.path.join(work, seg["id"])
            os.makedirs(seg_dir)
            audio = os.path.join(input_dir, seg["file"])
            data = get_data(first_coeff, audio, device, None, still=True)
            coeff = audio_to_coeff.generate(data, seg_dir, 0, None)
            fr = get_facerender_data(coeff, crop_pic, first_coeff, audio, batch, None, None, None,
                                     expression_scale=1.0, still_mode=True, preprocess="full", size=HOST_SIZE)
            result = animate.generate(fr, seg_dir, pic, crop_info,
                                      enhancer=HOST_ENHANCER if HOST_ENHANCER in ("gfpgan", "RestoreFormer") else None,
                                      background_enhancer=None, preprocess="full", img_size=HOST_SIZE)
            dest = os.path.join(out_dir, f"{seg['id']}.mp4")
            shutil.move(result, dest)
            done.append({"id": seg["id"], "file": f"{seg['id']}.mp4"})
            log(f"{seg['id']}: {seg.get('duration', 0):.1f}s audio rendered in {time.time() - t0:.0f}s")
        except Exception as exc:
            errors.append({"id": seg["id"], "error": f"{type(exc).__name__}: {exc}"})
            log(f"{seg['id']} FAILED: {exc}")
            traceback.print_exc()
        finally:
            shutil.rmtree(os.path.join(work, seg["id"]), ignore_errors=True)
    return done, errors


def main():
    t0 = time.time()
    try:
        input_dir = find_input_dir()
        if not SKIP_SETUP:
            import urllib.request
            try:
                urllib.request.urlopen("https://github.com", timeout=20).read(64)
            except Exception as exc:
                raise RuntimeError(f"No internet in this Kaggle session ({exc}). Kaggle enables internet only "
                                   "for phone-verified accounts: kaggle.com -> Settings -> Phone verification.")
            setup()
        apply_patches()
        done, errors = render(input_dir)
        write_result({"ok": bool(done), "clips": done, "errors": errors, "seconds": round(time.time() - t0)})
        log(f"finished: {len(done)} clip(s), {len(errors)} error(s), {time.time() - t0:.0f}s")
    except Exception as exc:
        traceback.print_exc()
        write_result({"ok": False, "clips": [], "errors": [{"id": "*", "error": f"{type(exc).__name__}: {exc}"}],
                      "seconds": round(time.time() - t0)})
        sys.exit(1)


if __name__ == "__main__":
    main()
