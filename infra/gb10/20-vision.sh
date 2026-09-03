#!/usr/bin/env bash
# vision venv: image embeddings (face / DINOv2 / CLIP), RAFT optical flow. Used by the CJ/SJ/MQ judges.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
gb10_ensure_root
gb10_detect_torch
gb10_hf_env

venv="$(gb10_make_venv vision)"
gb10_pip_torch "${venv}" torchvision
"${venv}/bin/pip" install --upgrade transformers open_clip_torch timm opencv-python-headless scikit-image scipy pillow numpy requests tqdm
# facenet-pytorch pins an old torch range; --no-deps keeps the aarch64 CUDA torch we just installed.
"${venv}/bin/pip" install --no-deps facenet-pytorch
# InsightFace is optional: its pretrained models are non-commercial. facenet-pytorch is the commercial path.
if ! ("${venv}/bin/pip" install cython && "${venv}/bin/pip" install --no-build-isolation insightface onnxruntime); then
  gb10_log "WARN: insightface/onnxruntime not installed (optional)"
fi

"${venv}/bin/python" - <<'PY'
import time, torch, torchvision, open_clip
from transformers import AutoModel
from facenet_pytorch import MTCNN, InceptionResnetV1

assert torch.cuda.is_available(), "CUDA not available inside the vision venv"
print("torch", torch.__version__, "cuda", torch.version.cuda, torch.cuda.get_device_name(0))
for label, build in [
    ("dinov2-large", lambda: AutoModel.from_pretrained("facebook/dinov2-large").cuda().eval()),
    ("clip ViT-L/14", lambda: open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai", device="cuda")),
    ("raft-large", lambda: torchvision.models.optical_flow.raft_large(weights="DEFAULT").cuda().eval()),
    ("facenet vggface2 + mtcnn", lambda: (InceptionResnetV1(pretrained="vggface2").eval().cuda(), MTCNN(device="cuda"))),
]:
    started = time.time(); build(); print(f"{label}: ok ({time.time() - started:.1f}s)")
try:
    import insightface
    app = insightface.app.FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"]); app.prepare(ctx_id=-1)
    print("insightface buffalo_l: ok (non-commercial models)")
except Exception as exc:  # optional
    print("insightface: skipped:", exc)
print(f"peak allocated {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
PY
gb10_log "vision venv ready: ${venv}"
