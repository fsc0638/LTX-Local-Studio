#!/usr/bin/env bash
set -euo pipefail
repo="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT}"
python_bin="${LTX_PYTHON:-$repo/.venv/bin/python}"
root="$repo/models/LTX-2.3"
kind="${LTX_PARAM_CONTROL_KIND:-performance}"
case "$kind" in
  performance|pose) ;;
  *) echo "Unsupported control kind: $kind" >&2; exit 2 ;;
esac
upper_kind="${kind^^}"
lora_var="LTX_CONTROL_${upper_kind}_LORA_PATH"
case "$kind" in
  performance) default_lora="$repo/models/control/ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors" ;;
  pose) default_lora="$repo/models/control/ltx-2-19b-ic-lora-pose-control.safetensors" ;;
esac
control_lora="${!lora_var:-$default_lora}"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/ltx-control.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
control_video="$tmp/control.mp4"
width="${LTX_PARAM_WIDTH:-768}"
height="${LTX_PARAM_HEIGHT:-512}"
frames="${LTX_PARAM_FRAMES:-121}"
fps="${LTX_PARAM_FPS:-24}"
# Freeze the control contract before inference: exact canvas, cadence, and requested duration.
ffmpeg -hide_banner -loglevel error -y -i "${LTX_ASSET_CONTROL_VIDEO_ID:?Missing control video}" \
  -vf "scale=${width}:${height}:force_original_aspect_ratio=decrease,pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2,fps=${fps}" \
  -frames:v "$frames" -an "$control_video"
args=( -m ltx_pipelines.ic_lora
  --distilled-checkpoint-path "${LTX_CHECKPOINT_PATH:-$root/ltx-2.3-22b-distilled-1.1.safetensors}"
  --gemma-root "${LTX_GEMMA_ROOT:-$repo/models/gemma-3-12b}"
  --spatial-upsampler-path "${LTX_UPSAMPLER_PATH:-$root/ltx-2.3-spatial-upscaler-x2-1.1.safetensors}"
  --lora "$control_lora" 1.0 --video-conditioning "$control_video" "${LTX_PARAM_CONTROL_STRENGTH:-1.0}"
  --prompt "${1:?Missing prompt}" --output-path "${2:?Missing output}"
  --height "$height" --width "$width" --num-frames "$frames"
  --frame-rate "$fps" --seed "${LTX_PARAM_SEED:-42}" )
[[ -n "${LTX_IMAGE:-}" ]] && args+=(--image "$LTX_IMAGE" 0 "${LTX_IMAGE_STRENGTH:-0.8}")
exec "$python_bin" "${args[@]}"
