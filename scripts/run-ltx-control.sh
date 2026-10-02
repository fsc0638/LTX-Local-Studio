#!/usr/bin/env bash
set -euo pipefail
repo="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT}"
python_bin="${LTX_PYTHON:-$repo/.venv/bin/python}"
root="$repo/models/LTX-2.5"
kind="${LTX_PARAM_CONTROL_KIND:-performance}"
case "$kind" in
  performance|pose|camera) ;;
  *) echo "Unsupported control kind: $kind" >&2; exit 2 ;;
esac
upper_kind="${kind^^}"
lora_var="LTX_CONTROL_${upper_kind}_LORA_PATH"
control_lora="${!lora_var:-$repo/models/control/ltx-2.5-${kind}-ic-lora.safetensors}"
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
  --transformer-path "${LTX25_TRANSFORMER_PATH:-$root/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors}"
  --text-encoder-path "${LTX25_TEXT_ENCODER_PATH:-$root/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors}"
  --video-vae-path "${LTX25_VIDEO_VAE_PATH:-$root/vae/ltx-2.5-video-vae-conv-bf16.safetensors}"
  --audio-vae-path "${LTX25_AUDIO_VAE_PATH:-$root/vae/ltx-2.5-audio-vae-bf16.safetensors}"
  --spatial-upsampler-path "${LTX25_UPSAMPLER_PATH:-$root/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors}"
  --lora "$control_lora" 1.0 --video-conditioning "$control_video" "${LTX_PARAM_CONTROL_STRENGTH:-1.0}"
  --prompt "${1:?Missing prompt}" --output-path "${2:?Missing output}"
  --height "$height" --width "$width" --num-frames "$frames"
  --frame-rate "$fps" --seed "${LTX_PARAM_SEED:-42}" )
[[ -n "${LTX_IMAGE:-}" ]] && args+=(--image "$LTX_IMAGE" 0 "${LTX_IMAGE_STRENGTH:-0.8}")
exec "$python_bin" "${args[@]}"
