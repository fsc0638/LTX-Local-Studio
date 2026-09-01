"""Project-owned adapter for the installed LTX distilled pipeline."""
import json
import logging
import os
import sys
import ctypes
import signal

import torch


def guard_worker_parent():
    """Linux: don't leave GPU inference orphaned if the API dies abruptly."""
    expected = os.environ.get("LTX_WORKER_PARENT_PID")
    if not expected:
        return  # Standalone CLI execution is not owned by the API.
    if sys.platform != "linux":
        raise RuntimeError("Worker parent-death protection requires Linux")
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_PDEATHSIG=1. Set it before checking ppid to close the startup race.
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Could not configure worker parent-death signal")
    if os.getppid() != int(expected):
        raise SystemExit("Worker parent exited before generation started")


def runtime_info():
    available = torch.cuda.is_available()
    return {
        "cuda_available": available,
        "device": torch.cuda.get_device_name(0) if available else "unavailable",
        "torch": torch.__version__,
        "error": "" if available else "CUDA GPU 不可用；請在主機終端啟動服務並檢查 NVIDIA 驅動。已停用 CPU 自動回退。",
    }


def install_audio_adapter(distilled, blocks):
    class StudioAudioDecoder(blocks.AudioDecoder):
        def __call__(self, latent):
            if os.environ.get("LTX_AUDIO", "1") == "0":
                logging.info("Studio: audio decode disabled")
                return None
            logging.info("Building audio decoder + vocoder (FP32 vocoder compatibility)")
            # The upstream vocoder casts mel input to FP32. FP32 autocast does
            # NOT convert BF16 convolution weights on this PyTorch runtime.
            # Keep only this small decoder component in FP32, not the 22B model.
            with (
                blocks.gpu_model(
                    self._decoder_builder.build(device=self._device, dtype=self._dtype).eval(),
                    alloc_trim_strategy=self._alloc_trim_strategy,
                ) as decoder,
                blocks.gpu_model(
                    self._vocoder_builder.build(device=self._device, dtype=torch.float32).eval(),
                    alloc_trim_strategy=self._alloc_trim_strategy,
                ) as vocoder,
                torch.autocast(device_type=self._device.type, enabled=False),
            ):
                return blocks.vae_decode_audio(latent, decoder, vocoder)

    distilled.AudioDecoder = StudioAudioDecoder


def main():
    guard_worker_parent()
    info = runtime_info()
    if "--check" in sys.argv:
        print(json.dumps(info, ensure_ascii=False))
        return
    if not info["cuda_available"]:
        raise SystemExit(info["error"])
    print(f"Studio device: {info['device']} / CUDA / {info['torch']}", flush=True)
    from ltx_pipelines import distilled
    from ltx_pipelines.utils import blocks

    install_audio_adapter(distilled, blocks)
    if os.environ.get("LTX_AUDIO_REFERENCE"):
        from audio_conditioning import install
        install(distilled)
    distilled.main()


if __name__ == "__main__":
    main()
