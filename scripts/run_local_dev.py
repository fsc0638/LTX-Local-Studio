"""Project-owned adapter for the installed LTX 2.5 one-stage Dev pipeline."""
import json
import os
import sys

from run_local import guard_worker_parent, install_audio_adapter, runtime_info


def main():
    guard_worker_parent()
    info = runtime_info()
    if "--check" in sys.argv:
        print(json.dumps(info, ensure_ascii=False))
        return
    if not info["cuda_available"]:
        raise SystemExit(info["error"])
    print(f"Studio device: {info['device']} / CUDA / {info['torch']}", flush=True)

    from ltx_pipelines import ti2vid_one_stage
    from ltx_pipelines.utils import blocks

    install_audio_adapter(ti2vid_one_stage, blocks)
    if os.environ.get("LTX_AUDIO_REFERENCE"):
        raise SystemExit("LTX 2.5 Dev character-LoRA lane does not support audio-reference conditioning; use A2V.")
    ti2vid_one_stage.main()


if __name__ == "__main__":
    main()
