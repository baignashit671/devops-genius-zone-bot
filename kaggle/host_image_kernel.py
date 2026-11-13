#!/usr/bin/env python3
"""
DevOps Genius Zone - AI presenter portrait generator (free Kaggle GPU)
=====================================================================
Pushed by tools/generate_host_candidates.py. Generates N photoreal
candidate portraits of a FICTIONAL presenter with Stable Diffusion XL base
1.0 (CreativeML Open RAIL++-M license: commercial use allowed, subject to
its use restrictions). You pick one and commit it as assets/host.png; the
daily job reuses that exact file forever, so the face never changes.

Every failure is written to result.json and printed as one clear
"FATAL: ..." line, which tools/generate_host_candidates.py shows in the
GitHub Actions log.
"""
import importlib
import json
import os
import subprocess
import sys
import time
import traceback

RUN_ID = "__RUN_ID__"
PROMPT = "__PROMPT__"
COUNT = int("__COUNT__") if "__COUNT__".isdigit() else 8
MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
NEGATIVE = (
    "cartoon, anime, illustration, painting, 3d render, cgi, doll, plastic skin, airbrushed, deformed face, "
    "asymmetric eyes, extra fingers, hands, glasses, sunglasses, hat, headphones, open mouth, teeth showing, "
    "tilted head, side profile, looking away, multiple people, text, watermark, logo, signature, blurry, "
    "low quality, jpeg artifacts, celebrity, famous person"
)
OUT = "/kaggle/working"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def write_result(payload):
    payload["run_id"] = RUN_ID
    with open(os.path.join(OUT, "result.json"), "w") as f:
        json.dump(payload, f, indent=2)


def fatal(msg):
    log("FATAL: " + msg)
    write_result({"ok": False, "error": msg, "files": []})
    sys.exit(1)


def check_internet():
    import urllib.request
    for url in ("https://pypi.org/simple/diffusers/", "https://huggingface.co/api/models/" + MODEL):
        try:
            urllib.request.urlopen(url, timeout=20).read(64)
        except Exception as exc:
            fatal(f"No internet in this Kaggle session ({url} -> {type(exc).__name__}: {exc}). "
                  "Kaggle only enables internet for phone-verified accounts: kaggle.com -> Settings -> "
                  "Phone verification, then run the workflow again.")
    log("internet: OK")


def check_gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        out = ""
    if not out:
        fatal("No GPU in this Kaggle session. Check kaggle.com -> Settings: phone verified, and your weekly "
              "GPU quota is not used up. (The workflow requests accelerator NvidiaTeslaT4.)")
    log(f"GPU: {out}")


def ensure_packages():
    """Install only what's missing - upgrading Kaggle's preinstalled
    torch/transformers is the classic way to break the image."""
    need = []
    for mod, pkg in (("diffusers", "diffusers>=0.30"), ("accelerate", "accelerate"), ("transformers", "transformers"),
                     ("safetensors", "safetensors")):
        try:
            importlib.import_module(mod)
        except Exception:
            need.append(pkg)
    if need:
        log("pip install " + " ".join(need))
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", *need], capture_output=True, text=True)
        if r.returncode != 0:
            fatal("pip install failed: " + (r.stderr or r.stdout).strip()[-800:])
    import diffusers, transformers, torch  # noqa: E401
    log(f"torch {torch.__version__}, diffusers {diffusers.__version__}, transformers {transformers.__version__}")


def generate():
    import torch
    from diffusers import StableDiffusionXLPipeline
    from PIL import Image, ImageDraw

    log(f"loading {MODEL} (first run downloads ~7 GB)")
    kw = dict(variant="fp16", use_safetensors=True)
    try:   # diffusers >= 0.4x renamed torch_dtype -> dtype
        pipe = StableDiffusionXLPipeline.from_pretrained(MODEL, dtype=torch.float16, **kw)
    except TypeError:
        pipe = StableDiffusionXLPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, **kw)
    pipe = pipe.to("cuda")
    # VAE slicing only saves memory at decode time; the API moved between
    # diffusers versions (0.42 removed pipe.enable_vae_slicing), so it's optional.
    for fn in (lambda: pipe.vae.enable_slicing(), lambda: pipe.enable_vae_slicing()):
        try:
            fn()
            break
        except Exception:
            continue
    files = []
    for k in range(COUNT):
        seed = 1000 + k * 7919
        g = torch.Generator("cuda").manual_seed(seed)
        img = pipe(prompt=PROMPT, negative_prompt=NEGATIVE, width=896, height=1152,
                   num_inference_steps=34, guidance_scale=6.0, generator=g).images[0]
        name = f"host_candidate_{k + 1:02d}_seed{seed}.png"
        img.save(os.path.join(OUT, name))
        files.append(name)
        log(f"{name} done")
    thumbs = [Image.open(os.path.join(OUT, f)).resize((298, 384)) for f in files]
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 298, rows * 414), (10, 14, 28))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(thumbs):
        x, y = (i % cols) * 298, (i // cols) * 414
        sheet.paste(t, (x, y))
        d.text((x + 8, y + 390), f"#{i + 1}", fill=(255, 255, 255))
    sheet.save(os.path.join(OUT, "contact_sheet.jpg"), quality=90)
    return files


def main():
    t0 = time.time()
    log(f"python {sys.version.split()[0]}, run {RUN_ID}, {COUNT} candidate(s)")
    check_gpu()
    check_internet()
    ensure_packages()
    try:
        files = generate()
    except Exception as exc:
        traceback.print_exc()
        fatal(f"generation failed: {type(exc).__name__}: {str(exc)[:600]}")
    write_result({"ok": True, "files": files, "seconds": round(time.time() - t0)})
    log(f"finished in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
