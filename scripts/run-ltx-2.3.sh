#!/usr/bin/env bash
set -euo pipefail

ltx_repo_root="${LTX_REPO_ROOT:?Set LTX_REPO_ROOT to the LTX-2 checkout path}"
python_bin="${LTX_PYTHON:-$ltx_repo_root/.venv/bin/python}"
checkpoint="${LTX_CHECKPOINT_PATH:-$ltx_repo_root/models/LTX-2.3/ltx-2.3-22b-distilled-1.1.safetensors}"
upsampler="${LTX_UPSAMPLER_PATH:-$ltx_repo_root/models/LTX-2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors}"
gemma_root="${LTX_GEMMA_ROOT:-$ltx_repo_root/models/gemma-3-12b}"

prompt="${1:-A cinematic ocean sunrise with gentle camera movement and synchronized ambient sound.}"
output_path="${2:-$ltx_repo_root/output.mp4}"
height="${LTX_HEIGHT:-512}"
width="${LTX_WIDTH:-768}"
num_frames="${LTX_FRAMES:-49}"
frame_rate="${LTX_FPS:-24}"

for required_path in "$python_bin" "$checkpoint" "$upsampler" "$gemma_root/config.json"; do
    if [[ ! -e "$required_path" ]]; then
        echo "Missing required LTX file: $required_path" >&2
        exit 1
    fi
done

mkdir -p "$(dirname "$output_path")"
cd "$ltx_repo_root"

args=(
    -m ltx_pipelines.distilled
    --distilled-checkpoint-path "$checkpoint"
    --spatial-upsampler-path "$upsampler"
    --gemma-root "$gemma_root"
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
