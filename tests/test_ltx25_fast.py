import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_backend as backend
import model_registry
import worker_contract


class Ltx25FastCompatibilityTests(unittest.TestCase):
    def test_ltx25_uses_full_ltx_contract(self):
        raw = {"model": "ltx25-fast", "prompt": "A dancer turns toward camera", "mode": "t2v",
               "profile": "preview-v1", "directing": {"camera": "locked"}}
        payload, external, requested = worker_contract.parse_request(raw, backend.parse_payload)
        self.assertEqual(payload["model"], "ltx25-fast")
        self.assertEqual(payload["width"], 512)
        self.assertEqual(payload["directing"]["camera"], "locked")
        self.assertEqual(external, {})
        self.assertIsNone(requested)

    def test_catalog_blocks_generation_until_every_component_exists(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LTX_REPO_ROOT": temp}, clear=False):
            item = model_registry.get("ltx25-fast").describe({"cuda_available": True})
        self.assertFalse(item["available"])
        self.assertFalse(item["installed"])
        self.assertIn("transformer", item["unavailable_reason"])

    def test_launcher_maps_split_checkpoint_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_root = root / "models/LTX-2.5"
            files = [
                model_root / "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
                model_root / "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
                model_root / "vae/ltx-2.5-video-vae-conv-bf16.safetensors",
                model_root / "vae/ltx-2.5-audio-vae-bf16.safetensors",
                model_root / "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
            ]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            capture = root / "capture.sh"
            output = root / "args.txt"
            capture.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$CAPTURE_OUTPUT\"\n", encoding="utf-8")
            capture.chmod(0o755)
            env = {**os.environ, "LTX_REPO_ROOT": str(root), "LTX_PYTHON": str(capture),
                   "CAPTURE_OUTPUT": str(output), "LTX_AUDIO": "0"}
            subprocess.run(["bash", str(Path(__file__).parents[1] / "scripts/run-ltx-2.5-fast.sh"),
                            "test prompt", str(root / "out.mp4")], env=env, check=True)
            args = output.read_text(encoding="utf-8").splitlines()
            for flag in ("--transformer-path", "--text-encoder-path", "--video-vae-path",
                         "--audio-vae-path", "--spatial-upsampler-path"):
                self.assertIn(flag, args)
            self.assertNotIn("--gemma-root", args)
            self.assertNotIn("--distilled-checkpoint-path", args)


if __name__ == "__main__":
    unittest.main()
