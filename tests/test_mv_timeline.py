import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import av
import numpy as np
from PIL import Image

import local_backend as backend
import media_store
import mv_timeline as mv
import worker_contract as contract
from video_settings import image_geometry
from scripts.sequence_media import assemble, audio_clip, audio_samples, prepare_image
from scripts.check_output import check_output
from scripts.audio_conditioning import FrozenAudioStage
from production_store import ProductionStore
from test_quality import create_video
from test_backend import BackendTests


def wav_bytes(seconds=4, rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        times = np.arange(round(seconds * rate)) / rate
        output.writeframes((np.sin(times * 2 * np.pi * 220) * 10000).astype("<i2").tobytes())
    return buffer.getvalue()


class TimelineTests(unittest.TestCase):
    def test_lrc_offset_repeat_unsorted_and_metadata(self):
        parsed = mv.parse_lrc("\ufeff[ti:test]\n[offset:+100]\n[00:02.05][00:01.5]世界\n[00:01.50]hello")
        self.assertEqual(parsed, [{"time": 1.6, "text": "世界 / hello"}, {"time": 2.15, "text": "世界"}])
        for bad in ("lyrics without time", "[00:61]bad", "[00:01]<00:01.3>word", "[offset:-500]\n[00:00]bad", "x" * 16001):
            with self.assertRaises(ValueError):
                mv.parse_lrc(bad)

    def test_music_timebase_tracks_audio_start(self):
        raw = {"prompt": "Singer", "render_mode": "sequence", "duration_seconds": 4, "fps": 24,
               "timeline": {"audio_id": "music", "audio_start_seconds": 3, "lrc_timebase": "music",
                            "lrc": "[00:02.00]Skipped\n[00:05.00]Visible"}}
        asset = lambda identity: {"kind": "audio", "duration_seconds": 20}
        payload = mv.normalize_sequence(raw, {"prompt": "Singer", "fps": 24, "audio": True, "directing": {}}, 481, asset)
        self.assertEqual(payload["timeline"]["lrc_timebase"], "music")
        self.assertTrue(any(segment["start_seconds"] == 2 and segment["lyrics"] == "Visible" for segment in payload["segments"]))
        self.assertIn("before the selected music start", " ".join(payload["timeline_warnings"]))
        with self.assertRaises(ValueError):
            mv.normalize_sequence({**raw, "timeline": {"lrc_timebase": "music", "lrc": "[00:01]No music"}},
                                  {"prompt": "Singer", "fps": 24, "audio": True, "directing": {}}, 481, asset)

    def test_exact_three_minute_plan_all_fps(self):
        for fps in (8, 16, 24, 25, 30, 50, 60):
            payload, _, requested = contract.parse_request({"prompt": "Character by the sea", "render_mode": "sequence", "duration_seconds": 180, "fps": fps}, backend.parse_payload)
            self.assertEqual(requested, 180)
            self.assertEqual(payload["frames"], 180 * fps)
            self.assertEqual(sum(s["keep_frames"] for s in payload["segments"]), 180 * fps)
            for part in payload["segments"]:
                self.assertGreaterEqual(part["frames"], part["keep_frames"])
                self.assertLessEqual(part["frames"], contract.MAX_FRAMES)
                self.assertEqual((part["frames"] - 1) % 8, 0)
            self.assertEqual(payload["segments"][-1]["start_frame"] + payload["segments"][-1]["keep_frames"], 180 * fps)

    def test_cue_changes_real_prompt_on_boundaries(self):
        raw = {"prompt": "Same character", "render_mode": "sequence", "duration_seconds": 8, "fps": 24,
               "directing": {"shot_size": "mcu", "camera": "locked"},
               "timeline": {"lrc": "[00:00.00]Hello\n[00:04.05]Goodbye", "cues": [{"time": 4, "action": "Raises one hand", "directing": {"emotion": "hope", "performance": "singing"}}]}}
        payload, _, _ = contract.parse_request(raw, backend.parse_payload)
        segments = payload["segments"]
        self.assertEqual([s["start_frame"] for s in segments], [0, 96, 98])
        self.assertIn("Medium close-up", segments[0]["prompt"])
        self.assertIn("Raises one hand", segments[1]["prompt"])
        self.assertIn("Goodbye", segments[2]["prompt"])
        self.assertIn("sings", segments[2]["prompt"])

    def test_invalid_sequence_and_input_fields(self):
        base = {"prompt": "Test", "render_mode": "sequence", "duration_seconds": 180}
        for extra in ({"duration_seconds": 181}, {"duration_seconds": float("nan")}, {"duration_seconds": True},
                      {"frames": 49}, {"segment_seconds": 1}, {"timeline": {"audio_path": "/etc/passwd"}},
                      {"timeline": {"cues": [{"time": 180}]}}, {"timeline": {"cues": [{"time": 0}, {"time": 0}]}},
                      {"timeline": {"audio_mode": "condition"}}, {"directing": {"camera": "shell"}}):
            with self.assertRaises(ValueError, msg=str(extra)):
                contract.parse_request({**base, **extra}, backend.parse_payload)
        with self.assertRaises(ValueError):
            contract.parse_request({"prompt": "single", "timeline": {}}, backend.parse_payload)

    def test_geometry_and_letterbox_exif(self):
        for width, height, ratio in ((1080, 1920, "9:16"), (1920, 1080, "16:9"), (999, 999, "1:1"), (400, 300, "4:3")):
            result = image_geometry(width, height)
            self.assertEqual(result["suggested_aspect_ratio"], ratio)
            self.assertEqual(result["ratio_error_percent"], 0)
        geometry = image_geometry(1234, 1000)
        self.assertEqual(geometry["suggested_aspect_ratio"], "source")
        for dimension in geometry["suggested_dimensions"].values():
            self.assertEqual(dimension % 64, 0)
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.jpg", Path(folder) / "fitted.png"
            original = Image.new("RGB", (80, 40), "red")
            exif = original.getexif(); exif[274] = 6
            original.save(source, exif=exif)
            prepare_image(source, target, 256, 256)
            with Image.open(target) as picture:
                self.assertEqual(picture.size, (256, 256))
                self.assertEqual(picture.getpixel((0, 128)), (0, 0, 0))
                self.assertGreater(picture.getpixel((128, 128))[0], 200)
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "cutout.png", Path(folder) / "neutral.png"
            cutout = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            cutout.paste((255, 0, 0, 255), (8, 8, 24, 24))
            cutout.save(source)
            prepare_image(source, target, 64, 64, "alpha_neutral")
            with Image.open(target) as picture:
                self.assertEqual(picture.getpixel((0, 0)), (127, 127, 127))
                self.assertGreater(picture.getpixel((32, 32))[0], 200)
            Image.new("RGB", (32, 32), "red").save(source)
            with self.assertRaises(ValueError):
                prepare_image(source, target, 64, 64, "alpha_neutral")

    def test_audio_stage_really_freezes_source_in_both_calls(self):
        from ltx_pipelines.utils.types import ModalitySpec
        seen = []
        sentinel = object()
        stage = FrozenAudioStage(lambda **kw: seen.append(kw), sentinel)
        for _ in range(2):
            stage(audio=ModalitySpec(context="context"), video="video")
        for call in seen:
            self.assertTrue(call["audio"].frozen)
            self.assertEqual(call["audio"].noise_scale, 0)
            self.assertIs(call["audio"].initial_latent, sentinel)

    def test_180_second_composition_and_continuous_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, music, output, manifest = (root / name for name in ("shot.mp4", "music.wav", "final.mp4", "plan.json"))
            create_video(source, frames=81, fps=8, width=64, height=64)
            music.write_bytes(wav_bytes(181))
            manifest.write_text(json.dumps({"fps": 8, "width": 64, "height": 64, "audio_path": str(music), "audio_start_seconds": 1,
                                            "segments": [{"path": str(source), "keep_frames": 80} for _ in range(18)]}))
            assemble(manifest, output)
            checked = check_output(output, {"width": 64, "height": 64, "frames": 1440, "fps": 8, "audio": True})
            self.assertTrue(checked["quality_control"]["passed"], checked)
            self.assertEqual(checked["measured_media"]["video_seconds"], 180)
            self.assertAlmostEqual(checked["measured_media"]["audio_seconds"], 180, delta=0.05)
            fragment = root / "clip.wav"
            audio_clip(music, fragment, 179, 2.125)
            self.assertEqual(audio_samples(fragment, 0, 2.125).shape, (2, 102000))


class TimelineAPITests(BackendTests):
    def api(self, path, raw):
        return self.request("POST", path, json.dumps(raw), {"Content-Type": "application/json", "Authorization": "Bearer " + "a" * 48, "Idempotency-Key": "timeline-request-123"})

    def test_audio_upload_validate_ownership_and_deletion_guard(self):
        with patch.object(contract, "api_key", return_value="a" * 48):
            status, _, body = self.request("POST", "/api/v1/assets?name=song.wav", wav_bytes(4), {"Content-Type": "audio/wav", "Authorization": "Bearer " + "a" * 48})
            self.assertEqual(status, 201, body)
            music = json.loads(body)
            self.assertEqual(music["kind"], "audio")
            raw = {"prompt": "Test", "render_mode": "sequence", "duration_seconds": 4, "timeline": {"audio_id": music["id"]}}
            valid = self.api("/api/v1/validate", raw)
            self.assertEqual(valid[0], 200, valid)
            self.assertEqual(self.api("/api/v1/validate", {**raw, "duration_seconds": 5})[0], 400)
            backend.JOBS["test"] = {"status": "running", "timeline": {"audio_id": music["id"]}}
            response = self.request("DELETE", f"/api/v1/assets/{music['id']}", headers={"Authorization": "Bearer " + "a" * 48})
            self.assertEqual(response[0], 409)
            backend.JOBS.clear()
            store = ProductionStore()
            payload, _, _ = contract.parse_request(raw, backend.parse_payload)
            with patch.object(backend, "STORE", store):
                with self.assertRaisesRegex(ValueError, "account"):
                    backend.submit_job(payload, owner_id="another-user")

    def test_real_sequence_worker_assembly_and_cancel_between_shots(self):
        # TEST FIXTURE ONLY. Real process, validation and composition; no AI claim.
        source = Path(self.temp.name) / "fixture.mp4"
        create_video(source, frames=49, fps=24)
        store = ProductionStore()
        raw = {"prompt": "valid", "render_mode": "sequence", "duration_seconds": 4, "segment_seconds": 2,
               "width": 256, "height": 256, "fps": 24, "audio": False}
        payload, _, _ = contract.parse_request(raw, backend.parse_payload)
        with patch.object(backend, "STORE", store), patch.object(backend, "LAUNCHER", Path(__file__).parent / "fixtures/generator.sh"), patch.dict(os.environ, {"LTX_TEST_FIXTURE": str(source)}):
            backend.JOBS["abcdef123456"] = {**payload, "id": "abcdef123456", "filename": "sequence.mp4", "status": "queued", "created_at": 0}
            backend.run_job("abcdef123456", payload)
            saved = store.get("abcdef123456")
            self.assertEqual(saved["status"], "succeeded", saved)
            self.assertEqual(saved["measured_media"]["frames"], 96)
            self.assertEqual(saved["measured_media"]["video_seconds"], 4)
            backend.JOBS["abcdef654321"] = {**payload, "id": "abcdef654321", "filename": "cancelled.mp4", "status": "queued", "created_at": 0, "cancel_requested": True}
            backend.run_job("abcdef654321", payload)
            self.assertEqual(store.get("abcdef654321")["status"], "cancelled")
            self.assertFalse((self.output / "cancelled.mp4").exists())

    def test_sequence_resume_reuses_valid_completed_shots(self):
        source = Path(self.temp.name) / "fixture.mp4"
        create_video(source, frames=49, fps=24)
        store = ProductionStore()
        raw = {"prompt": "valid", "render_mode": "sequence", "duration_seconds": 4, "segment_seconds": 2,
               "width": 256, "height": 256, "fps": 24, "audio": False}
        payload, _, _ = contract.parse_request(raw, backend.parse_payload)
        job_id = "abcdef789012"
        work = backend.WORK_DIR / job_id
        work.mkdir(parents=True)
        first = work / "shot-001.mp4"
        first.write_bytes(source.read_bytes())
        original = first.stat().st_mtime_ns
        job = {**payload, "id": job_id, "filename": "resumed.mp4", "status": "failed", "created_at": 0,
               "finished_at": 1, "runtime_seconds": 1, "error": {"code": "generation_timeout", "retryable": True}}
        store.record(job)
        with patch.object(backend, "STORE", store), patch.object(backend, "LAUNCHER", Path(__file__).parent / "fixtures/generator.sh"), patch.dict(os.environ, {"LTX_TEST_FIXTURE": str(source)}):
            backend.JOBS[job_id] = job
            backend.run_job(job_id, payload, resume=True)
        saved = store.get(job_id)
        self.assertEqual(saved["status"], "succeeded", saved)
        self.assertEqual(first.stat().st_mtime_ns, original)
        self.assertNotIn("error", saved)
        self.assertTrue((self.output / "resumed.mp4").is_file())
