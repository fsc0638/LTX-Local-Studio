#!/usr/bin/env bash
set -euo pipefail
repo="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT}"
python_bin="${LTX_PYTHON:-$repo/.venv/bin/python}"
root="$repo/models/LTX-2.5"
args=( -m ltx_pipelines.a2vid_two_stage
  --transformer-path "${LTX25_A2V_TRANSFORMER_PATH:-$root/diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors}"
  --text-encoder-path "${LTX25_TEXT_ENCODER_PATH:-$root/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors}"
  --video-vae-path "${LTX25_VIDEO_VAE_PATH:-$root/vae/ltx-2.5-video-vae-conv-bf16.safetensors}"
  --audio-vae-path "${LTX25_AUDIO_VAE_PATH:-$root/vae/ltx-2.5-audio-vae-bf16.safetensors}"
  --distilled-lora "${LTX25_DISTILLED_LORA_PATH:-$root/loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors}" 1.0
  --spatial-upsampler-path "${LTX25_UPSAMPLER_PATH:-$root/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors}"
  --audio-path "${LTX_ASSET_AUDIO_ID:?Missing driving audio}" --a2v-guidance-scale "${LTX_PARAM_A2V_GUIDANCE:-3.0}"
  --prompt "${1:?Missing prompt}" --output-path "${2:?Missing output}"
  --height "${LTX_PARAM_HEIGHT:-512}" --width "${LTX_PARAM_WIDTH:-768}" --num-frames "${LTX_PARAM_FRAMES:-121}"
  --frame-rate "${LTX_PARAM_FPS:-24}" --seed "${LTX_PARAM_SEED:-42}" )
[[ -n "${LTX_IMAGE:-}" ]] && args+=(--image "$LTX_IMAGE" 0 "${LTX_IMAGE_STRENGTH:-0.8}")
exec "$python_bin" "${args[@]}"
