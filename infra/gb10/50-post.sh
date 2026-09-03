#!/usr/bin/env bash
# Post tools into the vision venv: LaMa inpaint, Real-ESRGAN upscale, RIFE interpolation. Used by VX.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
gb10_hf_env
venv="${STUDIO_VENVS}/vision"
[[ -x "${venv}/bin/python" ]] || gb10_die "run 20-vision.sh first"

"${venv}/bin/pip" install --upgrade simple-lama-inpainting realesrgan basicsr
# basicsr still imports a torchvision module that was removed upstream.
"${venv}/bin/python" - <<'PY'
import pathlib, basicsr
target = pathlib.Path(basicsr.__file__).parent / "data" / "degradations.py"
source = target.read_text()
patched = source.replace("torchvision.transforms.functional_tensor", "torchvision.transforms.functional")
print("patched" if patched != source else "no patch needed", target)
if patched != source:
    target.write_text(patched)
PY

weights="${STUDIO_MODELS}/realesrgan/RealESRGAN_x4plus.pth"
mkdir -p "$(dirname "${weights}")"
[[ -f "${weights}" ]] || curl -fL -o "${weights}" \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
[[ -d "${STUDIO_TOOLS}/rife" ]] || git clone --depth 1 https://github.com/hzwer/Practical-RIFE "${STUDIO_TOOLS}/rife"
gb10_log "RIFE weights are linked from ${STUDIO_TOOLS}/rife/README.md; unpack them into ${STUDIO_TOOLS}/rife/train_log"

STUDIO_REALESRGAN_WEIGHTS="${weights}" "${venv}/bin/python" - <<'PY'
import os, numpy as np, torch
from PIL import Image
from simple_lama_inpainting import SimpleLama
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

image = Image.new("RGB", (256, 256), (120, 90, 60))
mask = Image.new("L", (256, 256), 0); mask.paste(255, (96, 96, 160, 160))
print("lama:", SimpleLama()(image, mask).size)
net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
upscaler = RealESRGANer(scale=4, model_path=os.environ["STUDIO_REALESRGAN_WEIGHTS"], model=net, half=True, device="cuda")
print("realesrgan:", upscaler.enhance(np.array(image))[0].shape)
print(f"peak allocated {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
PY
gb10_log "post tools ready in ${venv}"
