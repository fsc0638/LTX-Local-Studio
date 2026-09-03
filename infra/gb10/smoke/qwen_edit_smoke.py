"""Qwen-Image-Edit-2509 multi-reference smoke test: same character, new angle.

Pass 1-3 --ref images. With --lightning the Edit-2509 8-step LoRA is fused and CFG is disabled.
"""
import argparse
import glob
import os
import time

import torch
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--ref", action="append", required=True, help="reference image; repeat up to 3 times")
parser.add_argument("--out", required=True)
parser.add_argument("--prompt", default="The same person as in the reference image, left three-quarter view, "
                    "same hair and coat, medium close-up, soft window light, neutral grey background")
parser.add_argument("--size", type=int, default=768)
parser.add_argument("--steps", type=int)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--lightning", action="store_true")
parser.add_argument("--model", default="Qwen/Qwen-Image-Edit-2509")
parser.add_argument("--lightning-repo", default="lightx2v/Qwen-Image-Lightning")
args = parser.parse_args()
if not 1 <= len(args.ref) <= 3:
    raise SystemExit("--ref accepts 1 to 3 images")

from diffusers import QwenImageEditPlusPipeline  # noqa: E402

started = time.time()
pipe = QwenImageEditPlusPipeline.from_pretrained(args.model, torch_dtype=torch.bfloat16).to("cuda")
load_seconds = time.time() - started
steps, cfg = args.steps, 4.0
if args.lightning:
    from huggingface_hub import snapshot_download
    folder = snapshot_download(args.lightning_repo, allow_patterns=["*Edit-2509*8steps*bf16*.safetensors"])
    files = sorted(glob.glob(os.path.join(folder, "**", "*Edit-2509*8steps*bf16*.safetensors"), recursive=True))
    if not files:
        raise SystemExit(f"Edit-2509 Lightning LoRA not found under {folder}")
    pipe.load_lora_weights(os.path.dirname(files[0]), weight_name=os.path.basename(files[0]))
    pipe.fuse_lora()
    steps, cfg = steps or 8, 1.0
    print("lightning LoRA:", os.path.basename(files[0]))
steps = steps or 40

refs = [Image.open(path).convert("RGB") for path in args.ref]
torch.cuda.reset_peak_memory_stats()
started = time.time()
image = pipe(image=refs, prompt=args.prompt, negative_prompt=" ", height=args.size, width=args.size,
             num_inference_steps=steps, true_cfg_scale=cfg, guidance_scale=1.0, num_images_per_prompt=1,
             generator=torch.Generator("cuda").manual_seed(args.seed)).images[0]
generate_seconds = time.time() - started
image.save(args.out)
print(f"qwen-image-edit-2509: load {load_seconds:.1f}s, generate {generate_seconds:.1f}s "
      f"({steps} steps, {args.size}px, {len(refs)} refs, cfg {cfg}), "
      f"peak {torch.cuda.max_memory_allocated() / 1e9:.1f} GB -> {args.out}")
