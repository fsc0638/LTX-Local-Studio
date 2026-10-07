#!/usr/bin/env bash
set -euo pipefail
studio_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ltx_repo_root="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT to the LTX-2 checkout path}"
python_bin="${LTX_PYTHON:-$ltx_repo_root/.venv/bin/python}"
model_root="${LTX25_MODEL_ROOT:-$ltx_repo_root/models/LTX-2.5}"
transformer="${LTX25_DEV_TRANSFORMER_PATH:-$model_root/diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors}"
text_encoder="${LTX25_TEXT_ENCODER_PATH:-$model_root/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors}"
video_vae="${LTX25_VIDEO_VAE_PATH:-$model_root/vae/ltx-2.5-video-vae-conv-bf16.safetensors}"
audio_vae="${LTX25_AUDIO_VAE_PATH:-$model_root/vae/ltx-2.5-audio-vae-bf16.safetensors}"

prompt="${1:-A cinematic character performance with stable identity and natural motion.}"
output_path="${2:-$ltx_repo_root/output-2.5-dev.mp4}"
height="${LTX_HEIGHT:-512}"
width="${LTX_WIDTH:-768}"
num_frames="${LTX_FRAMES:-49}"
frame_rate="${LTX_FPS:-24}"
negative_prompt="${LTX_NEGATIVE_PROMPT:-different person, inconsistent face, identity drift, duplicated person, deformed face, asymmetrical eyes, extra limbs, text, watermark}"

for required_path in "$python_bin" "$transformer" "$text_encoder" "$video_vae" "$audio_vae"; do
    if [[ ! -e "$required_path" ]]; then
        echo "Missing required LTX 2.5 Dev file: $required_path" >&2
        exit 1
    fi
done

mkdir -p "$(dirname "$output_path")"
cd "$ltx_repo_root"

args=(
    "$studio_root/scripts/run_local_dev.py"
    --transformer-path "$transformer"
    --text-encoder-path "$text_encoder"
    --video-vae-path "$video_vae"
    --audio-vae-path "$audio_vae"
    --prompt "$prompt"
    --negative-prompt "$negative_prompt"
    --output-path "$output_path"
    --height "$height"
    --width "$width"
    --num-frames "$num_frames"
    --frame-rate "$frame_rate"
    --seed "${LTX_SEED:-42}"
    --num-inference-steps "${LTX25_DEV_STEPS:-30}"
    --video-cfg-guidance-scale "${LTX25_DEV_VIDEO_CFG:-3.0}"
    --video-stg-guidance-scale "${LTX25_DEV_VIDEO_STG:-1.0}"
    --video-rescale-scale "${LTX25_DEV_VIDEO_RESCALE:-0.7}"
    --video-stg-blocks "${LTX25_DEV_VIDEO_STG_BLOCKS:-28}"
    --a2v-guidance-scale "${LTX25_DEV_A2V_GUIDANCE:-1.0}"
    --audio-cfg-guidance-scale "${LTX25_DEV_AUDIO_CFG:-1.0}"
    --audio-stg-guidance-scale "${LTX25_DEV_AUDIO_STG:-0.0}"
    --v2a-guidance-scale "${LTX25_DEV_V2A_GUIDANCE:-1.0}"
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
if [[ -n "${LTX_IDENTITY_LORA_PATH:-}" ]]; then
    args+=(--lora "$LTX_IDENTITY_LORA_PATH" "${LTX_IDENTITY_LORA_STRENGTH:-1.0}")
fi
if [[ -n "${LTX_WARDROBE_LORA_PATH:-}" ]]; then
    args+=(--lora "$LTX_WARDROBE_LORA_PATH" "${LTX_WARDROBE_LORA_STRENGTH:-1.0}")
fi

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export CUDA_MODULE_LOADING="${CUDA_MODULE_LOADING:-LAZY}"
exec "$python_bin" "${args[@]}"
