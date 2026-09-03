#!/usr/bin/env bash
# imagegen venv: Qwen-Image-Edit-2509 (multi-reference character keyframes) + Z-Image-Turbo (anchors, empty shots)
# + the Edit-2509 Lightning 8-step LoRA. Downloads ~75 GB into $HF_HOME (resumable), then runs two smoke tests
# that print seconds and peak memory. Do not run while an LTX job is generating: the two cannot share 128 GB.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
gb10_ensure_root
gb10_detect_torch
gb10_hf_env
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

venv="$(gb10_make_venv imagegen)"
gb10_pip_torch "${venv}" torchvision
"${venv}/bin/pip" install --upgrade "diffusers>=0.36" transformers accelerate safetensors sentencepiece peft huggingface_hub pillow numpy

"${venv}/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
for repo, kwargs in (
    ("Tongyi-MAI/Z-Image-Turbo", {}),
    ("Qwen/Qwen-Image-Edit-2509", {}),
    ("lightx2v/Qwen-Image-Lightning", {"allow_patterns": ["*Edit-2509*8steps*bf16*.safetensors"]}),
):
    print("ready:", repo, "->", snapshot_download(repo, **kwargs))
PY

smoke_dir="${STUDIO_ROOT}/smoke"
mkdir -p "${smoke_dir}"
"${venv}/bin/python" "${here}/smoke/zimage_smoke.py" --out "${smoke_dir}/zimage_ref.png"
"${venv}/bin/python" "${here}/smoke/qwen_edit_smoke.py" --ref "${smoke_dir}/zimage_ref.png" \
  --out "${smoke_dir}/qwen_edit_three_quarter.png" --lightning
gb10_log "imagegen venv ready: ${venv}. Record the seconds and peak GB above; they feed the LP budget formula."
