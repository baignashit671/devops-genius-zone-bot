#!/usr/bin/env python3
"""
DevOps Genius Zone - AI presenter portrait generator (free Kaggle GPU)
=====================================================================
Pushed by tools/generate_host_candidates.py. Generates N photoreal
candidate portraits of a FICTIONAL presenter with Stable Diffusion XL base
1.0 (CreativeML Open RAIL++-M license: commercial use allowed, subject to
its use restrictions). You pick one and commit it as assets/host.png; the
daily job reuses that exact file forever, so the face never changes.
"""
import json
import os
import subprocess
import sys
import time

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


def main():
    t0 = time.time()
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "diffusers>=0.30", "transformers", "accelerate",
                    "safetensors"], check=True)
    import torch
    from diffusers import StableDiffusionXLPipeline
    from PIL import Image, ImageDraw

    if not torch.cuda.is_available():
        raise SystemExit("No GPU in this Kaggle session.")
    pipe = StableDiffusionXLPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, variant="fp16",
                                                     use_safetensors=True).to("cuda")
    pipe.enable_vae_slicing()
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
    # contact sheet to compare quickly
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
    with open(os.path.join(OUT, "result.json"), "w") as f:
        json.dump({"run_id": RUN_ID, "ok": True, "files": files, "seconds": round(time.time() - t0)}, f)
    log(f"finished in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
