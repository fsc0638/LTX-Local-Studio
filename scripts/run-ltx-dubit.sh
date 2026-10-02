#!/usr/bin/env bash
set -euo pipefail
repo="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT}"
python_bin="${LTX_PYTHON:-$repo/.venv/bin/python}"
root="$repo/models/LTX-2.3"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
frames="${LTX_PARAM_FRAMES:-121}"
fps="${LTX_PARAM_FPS:-24}"
width="${LTX_PARAM_WIDTH:-768}"
height="${LTX_PARAM_HEIGHT:-512}"
duration="$($python_bin -c 'import sys; print(int(sys.argv[1])/int(sys.argv[2]))' "$frames" "$fps")"
reference="$tmp/reference.mp4"
ffmpeg -hide_banner -loglevel error -i "${LTX_ASSET_REFERENCE_VIDEO_ID:?Missing reference performance}" \
  -vf "scale=${width}:${height}:force_original_aspect_ratio=decrease,pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2,fps=${fps},tpad=stop_mode=clone:stop_duration=${duration}" \
  -af apad -frames:v "$frames" -t "$duration" -c:v libx264 -pix_fmt yuv420p -c:a aac -y "$reference"
args=( -m ltx_pipelines.dubit
  --distilled-checkpoint-path "${LTX_CHECKPOINT_PATH:-$root/ltx-2.3-22b-distilled-1.1.safetensors}"
  --gemma-root "${LTX_GEMMA_ROOT:-$repo/models/gemma-3-12b}"
  --spatial-upsampler-path "${LTX_UPSAMPLER_PATH:-$root/ltx-2.3-spatial-upscaler-x2-1.1.safetensors}"
  --lora "${LTX_DUBIT_LORA_PATH:-$root/ltx-2.3-22b-ic-lora-dubit.safetensors}" 1.0
  --reference-video "$reference"
  --reference-strength "${LTX_PARAM_REFERENCE_STRENGTH:-1.0}"
  --prompt "${1:?Missing prompt}" --output-path "${2:?Missing output}"
  --height "$height" --width "$width" --seed "${LTX_PARAM_SEED:-42}" )
exec "$python_bin" "${args[@]}"
