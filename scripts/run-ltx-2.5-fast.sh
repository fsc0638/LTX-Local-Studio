#!/usr/bin/env bash
set -euo pipefail
studio_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ltx_repo_root="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT to the LTX-2 checkout path}"
python_bin="${LTX_PYTHON:-$ltx_repo_root/.venv/bin/python}"
model_root="${LTX25_MODEL_ROOT:-$ltx_repo_root/models/LTX-2.5}"
transformer="${LTX25_TRANSFORMER_PATH:-$model_root/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors}"
text_encoder="${LTX25_TEXT_ENCODER_PATH:-$model_root/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors}"
video_vae="${LTX25_VIDEO_VAE_PATH:-$model_root/vae/ltx-2.5-video-vae-conv-bf16.safetensors}"
audio_vae="${LTX25_AUDIO_VAE_PATH:-$model_root/vae/ltx-2.5-audio-vae-bf16.safetensors}"
upsampler="${LTX25_UPSAMPLER_PATH:-$model_root/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors}"

prompt="${1:-A cinematic ocean sunrise with gentle camera movement and synchronized ambient sound.}"
output_path="${2:-$ltx_repo_root/output-2.5.mp4}"
height="${LTX_HEIGHT:-512}"
width="${LTX_WIDTH:-768}"
num_frames="${LTX_FRAMES:-49}"
frame_rate="${LTX_FPS:-24}"

for required_path in "$python_bin" "$transformer" "$text_encoder" "$video_vae" "$audio_vae" "$upsampler"; do
    if [[ ! -e "$required_path" ]]; then
        echo "Missing required LTX 2.5 file: $required_path" >&2
        exit 1
    fi
done

mkdir -p "$(dirname "$output_path")"
cd "$ltx_repo_root"

args=(
    "$studio_root/scripts/run_local.py"
    --transformer-path "$transformer"
    --text-encoder-path "$text_encoder"
    --video-vae-path "$video_vae"
    --audio-vae-path "$audio_vae"
    --spatial-upsampler-path "$upsampler"
    --prompt "$prompt"
    --output-path "$output_path"
    --height "$height"
    --width "$width"
    --num-frames "$num_frames"
    --frame-rate "$frame_rate"
    --seed "${LTX_SEED:-42}"
)

if [[ -n "${LTX_IMAGE:-}" ]]; then
    args+=(--image "$LTX_IMAGE" "${LTX_IMAGE_FRAME:-0}" "${LTX_IMAGE_STRENGTH:-0.8}")
fi
if [[ -n "${LTX_QUANTIZATION:-}" ]]; then
    args+=(--quantization "$LTX_QUANTIZATION")
fi
if [[ -n "${LTX_OFFLOAD:-}" ]]; then
    args+=(--offload "$LTX_OFFLOAD")
fi

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export CUDA_MODULE_LOADING="${CUDA_MODULE_LOADING:-LAZY}"
exec "$python_bin" "${args[@]}"
