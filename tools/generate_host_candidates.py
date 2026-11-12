#!/usr/bin/env python3
"""Generate AI presenter portrait candidates on a free Kaggle GPU.

Used by .github/workflows/generate-host-image.yml (run it once, manually):
    python tools/generate_host_candidates.py --count 8 --appearance "..."
Downloads host_candidate_*.png + contact_sheet.jpg into host_candidates/.
Pick the best one and commit it to the repo as assets/host.png.

Tips for a portrait that animates well: face looking straight into the
camera, mouth closed, no hands near the face, no glasses, plain background.
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import host_lipsync as hl  # noqa: E402

BASE_PROMPT = (
    "professional head-and-shoulders portrait photo of {appearance}, looking straight into the camera, "
    "mouth closed, calm confident friendly expression, centered, upper chest visible, soft studio key light, "
    "dark softly blurred modern tech office background with subtle blue monitor glow, sharp focus on the eyes, "
    "natural skin texture, 85mm lens, f/2.8, photorealistic, high detail"
)
DEFAULT_APPEARANCE = ("a fictional 34-year-old American male DevOps engineer, short dark brown hair, "
                      "light stubble, wearing a plain navy blue crew-neck t-shirt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--appearance", default="")
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--out", default="host_candidates")
    ap.add_argument("--timeout-min", type=float, default=40)
    a = ap.parse_args()

    ok, why = hl.kaggle_ready()
    if not ok:
        raise SystemExit(f"Kaggle not configured: {why}")
    import os
    user = os.environ["KAGGLE_USERNAME"].strip()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    prompt = BASE_PROMPT.format(appearance=(a.appearance.strip() or DEFAULT_APPEARANCE))
    print(f"Prompt: {prompt}")

    work = Path("host_image_job")
    k_dir, out_dir = work / "kernel", Path(a.out)
    k_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    code = (hl.HERE / "kaggle" / "host_image_kernel.py").read_text()
    code = (code.replace('"__PROMPT__"', json.dumps(prompt))
                .replace("__RUN_ID__", run_id)
                .replace("__COUNT__", str(max(1, min(a.count, 16)))))
    (k_dir / "host_image_kernel.py").write_text(code)
    k_id = f"{user}/devops-host-portrait"
    (k_dir / "kernel-metadata.json").write_text(json.dumps({
        "id": k_id, "title": "devops-host-portrait", "code_file": "host_image_kernel.py",
        "language": "python", "kernel_type": "script", "is_private": True,
        "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": [],
    }))
    deadline = time.time() + a.timeout_min * 60
    args = ["kernels", "push", "-p", str(k_dir), "-t", str(int(a.timeout_min * 60))]
    if hl.ACCELERATOR:
        args += ["--accelerator", hl.ACCELERATOR]
    print(hl._kaggle(args).strip())
    hl._wait_kernel(k_id, deadline)
    hl._kaggle(["kernels", "output", k_id, "-p", str(out_dir), "-o", "-q"], timeout=900)
    res = json.loads((out_dir / "result.json").read_text())
    if res.get("run_id") != run_id:
        raise SystemExit("stale kernel output - run the workflow again")
    print(f"{len(res.get('files', []))} candidates in {out_dir}/ ({res.get('seconds')}s on Kaggle).")
    print("Open contact_sheet.jpg, pick one, and commit it as assets/host.png.")


if __name__ == "__main__":
    main()
