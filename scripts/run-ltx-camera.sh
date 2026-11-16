#!/usr/bin/env bash
set -euo pipefail
repo="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT}"
python_bin="${LTX_PYTHON:-$repo/.venv/bin/python}"
root="$repo/models/LTX-2.3"
move="${LTX_PARAM_CAMERA_MOVE:-static}"
case "$move" in
  dolly-in|dolly-left|dolly-out|dolly-right|jib-down|jib-up|static) ;;
  *) echo "Unsupported camera move: $move" >&2; exit 2 ;;
esac
upper_move="${move^^}"
upper_move="${upper_move//-/_}"
lora_var="LTX_CAMERA_${upper_move}_LORA_PATH"
camera_lora="${!lora_var:-$repo/models/control/ltx-2-19b-lora-camera-control-${move}.safetensors}"
args=( -m ltx_pipelines.distilled
  --distilled-checkpoint-path "${LTX_CHECKPOINT_PATH:-$root/ltx-2.3-22b-distilled-1.1.safetensors}"
  --gemma-root "${LTX_GEMMA_ROOT:-$repo/models/gemma-3-12b}"
  --spatial-upsampler-path "${LTX_UPSAMPLER_PATH:-$root/ltx-2.3-spatial-upscaler-x2-1.1.safetensors}"
  --lora "$camera_lora" "${LTX_PARAM_CAMERA_STRENGTH:-1.0}"
  --prompt "${1:?Missing prompt}" --output-path "${2:?Missing output}"
  --height "${LTX_PARAM_HEIGHT:-512}" --width "${LTX_PARAM_WIDTH:-768}" --num-frames "${LTX_PARAM_FRAMES:-121}"
  --frame-rate "${LTX_PARAM_FPS:-24}" --seed "${LTX_PARAM_SEED:-42}" )
[[ -n "${LTX_IMAGE:-}" ]] && args+=(--image "$LTX_IMAGE" 0 "${LTX_IMAGE_STRENGTH:-0.8}")
exec "$python_bin" "${args[@]}"
