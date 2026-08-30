import contextlib
import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch

spec = importlib.util.spec_from_file_location("run_local", Path(__file__).resolve().parents[1] / "scripts/run_local.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AudioAdapterTests(unittest.TestCase):
    def test_fp32_vocoder_and_bf16_vae(self):
        builds = []
        class Builder:
            def build(self, device, dtype):
                builds.append(dtype)
                return torch.nn.Conv1d(1, 1, 1).to(dtype=dtype)

        class Decoder:
            _device = torch.device("cpu")
            _dtype = torch.bfloat16
            _decoder_builder = Builder()
            _vocoder_builder = Builder()
            _alloc_trim_strategy = None

        @contextlib.contextmanager
        def gpu_model(model, **_kwargs):
            yield model

        # Reproduce the failing boundary: FP32 input must match conv bias dtype.
        blocks = SimpleNamespace(AudioDecoder=Decoder, gpu_model=gpu_model,
                                 vae_decode_audio=lambda latent, decoder, vocoder: vocoder(latent.float()))
        distilled = SimpleNamespace()
        runner.install_audio_adapter(distilled, blocks)
        with patch.dict(os.environ, {"LTX_AUDIO": "1"}):
            result = distilled.AudioDecoder()(torch.zeros(1, 1, 8, dtype=torch.bfloat16))
        self.assertEqual(builds, [torch.bfloat16, torch.float32])
        self.assertEqual(result.dtype, torch.float32)
        builds.clear()
        with patch.dict(os.environ, {"LTX_AUDIO": "0"}):
            self.assertIsNone(distilled.AudioDecoder()(None))
        self.assertEqual(builds, [])

    def test_cpu_fallback_is_blocked(self):
        with patch.object(torch.cuda, "is_available", return_value=False), patch("sys.argv", ["run_local.py"]):
            with self.assertRaisesRegex(SystemExit, "CPU"):
                runner.main()

    def test_parent_death_signal_and_startup_race_guard(self):
        libc = MagicMock()
        libc.prctl.return_value = 0
        with patch.dict(os.environ, {"LTX_WORKER_PARENT_PID": "12345"}), patch.object(runner.ctypes, "CDLL", return_value=libc), patch.object(runner.os, "getppid", return_value=12345):
            runner.guard_worker_parent()
            libc.prctl.assert_called_once_with(1, runner.signal.SIGKILL, 0, 0, 0)
            with patch.object(runner.os, "getppid", return_value=1):
                with self.assertRaises(SystemExit):
                    runner.guard_worker_parent()
            libc.prctl.return_value = -1
            with self.assertRaises(OSError):
                runner.guard_worker_parent()


if __name__ == "__main__":
    unittest.main()
