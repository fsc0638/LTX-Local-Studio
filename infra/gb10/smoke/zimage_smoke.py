"""Z-Image-Turbo text-to-image smoke test: one portrait, prints load/generate seconds and peak memory."""
import argparse
import time

import torch

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--prompt", default="Studio portrait of an adult woman with shoulder-length dark brown hair, "
                    "wearing a dark green wool coat, soft window light, neutral grey background, photorealistic, 85mm lens")
parser.add_argument("--size", type=int, default=1024)
parser.add_argument("--steps", type=int, default=8)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--model", default="Tongyi-MAI/Z-Image-Turbo")
args = parser.parse_args()

try:
    from diffusers import ZImagePipeline
except ImportError:
    raise SystemExit("diffusers has no ZImagePipeline: pip install -U 'diffusers>=0.36' (or from git main)")

started = time.time()
pipe = ZImagePipeline.from_pretrained(args.model, torch_dtype=torch.bfloat16).to("cuda")
load_seconds = time.time() - started
torch.cuda.reset_peak_memory_stats()
started = time.time()
image = pipe(prompt=args.prompt, height=args.size, width=args.size, num_inference_steps=args.steps,
             guidance_scale=0.0, generator=torch.Generator("cuda").manual_seed(args.seed)).images[0]
generate_seconds = time.time() - started
image.save(args.out)
print(f"z-image-turbo: load {load_seconds:.1f}s, generate {generate_seconds:.1f}s "
      f"({args.steps} steps, {args.size}px), peak {torch.cuda.max_memory_allocated() / 1e9:.1f} GB -> {args.out}")
