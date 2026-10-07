import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import model_registry


class Ltx25DevTests(unittest.TestCase):
    def test_catalog_requires_dev_transformer_but_not_spatial_upsampler(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LTX_REPO_ROOT": temp}, clear=False):
            root = Path(temp) / "models/LTX-2.5"
            for relative in (
                "diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors",
                "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
                "vae/ltx-2.5-video-vae-conv-bf16.safetensors",
                "vae/ltx-2.5-audio-vae-bf16.safetensors",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            item = model_registry.get("ltx25-dev").describe({"cuda_available": True})
        self.assertTrue(item["available"])
        self.assertTrue(item["installed"])
        self.assertEqual(item["modes"], ["t2v", "i2v"])

    def test_launcher_maps_one_stage_dev_and_character_lora_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_root = root / "models/LTX-2.5"
            for relative in (
                "diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors",
                "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
                "vae/ltx-2.5-video-vae-conv-bf16.safetensors",
                "vae/ltx-2.5-audio-vae-bf16.safetensors",
            ):
                path = model_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            lora = root / "identity.safetensors"
            lora.touch()
            capture = root / "capture.sh"
            output = root / "args.txt"
            capture.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$CAPTURE_OUTPUT\"\n", encoding="utf-8")
            capture.chmod(0o755)
            env = {
                **os.environ,
                "LTX_REPO_ROOT": str(root),
                "LTX_PYTHON": str(capture),
                "CAPTURE_OUTPUT": str(output),
                "LTX_IDENTITY_LORA_PATH": str(lora),
                "LTX_IDENTITY_LORA_STRENGTH": "1.0",
            }
            subprocess.run(
                ["bash", str(Path(__file__).parents[1] / "scripts/run-ltx-2.5-dev.sh"),
                 "test prompt", str(root / "out.mp4")],
                env=env,
                check=True,
            )
            args = output.read_text(encoding="utf-8").splitlines()
        self.assertTrue(args[0].endswith("scripts/run_local_dev.py"))
        self.assertIn("--transformer-path", args)
        self.assertIn("--num-inference-steps", args)
        self.assertIn("--negative-prompt", args)
        self.assertNotIn("--spatial-upsampler-path", args)
        lora_index = args.index("--lora")
        self.assertEqual(args[lora_index + 1:lora_index + 3], [str(lora), "1.0"])


if __name__ == "__main__":
    unittest.main()
