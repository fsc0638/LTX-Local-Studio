"""Audio service tests.

The unit tests generate a click track with numpy and never load a model, so they run anywhere.
The one test that needs whisper is skipped unless LTX_AUDIO_INTEGRATION=1, because loading
large-v3 costs several seconds and about 6 GB.
"""
import json
import math
import os
import struct
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

# The API tests need psycopg and the backend; the server tests need neither. Importing them
# lazily lets the audio venv (librosa, no psycopg) run the analysis tests while the LTX venv
# (psycopg, no librosa) runs the endpoint tests. Between them every test runs somewhere.
try:
    import local_backend as backend
    import test_backend
    import worker_contract as contract

    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False

    class test_backend:  # noqa: N801 - stands in so the class below still defines
        BackendTests = unittest.TestCase

SERVER = Path(__file__).resolve().parents[1] / "services/audio/server.py"

# librosa lives in /opt/studio/venvs/audio, not in the interpreter that runs this suite. Path
# containment and argument checks are pure Python and always run; anything that actually analyses
# audio is skipped unless the suite happens to be run by the audio venv.
try:
    import librosa  # noqa: F401

    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False


def click_track(path, seconds=4.0, bpm=120, rate=8000):
    """A click every beat: something with an unambiguous tempo that costs nothing to make."""
    period = 60.0 / bpm
    frames = bytearray()
    for index in range(int(seconds * rate)):
        t = index / rate
        into_beat = t % period
        # 12 ms of tone at each beat, silence between.
        value = math.sin(2 * math.pi * 880 * t) * 0.8 if into_beat < 0.012 else 0.0
        frames += struct.pack("<h", int(value * 32767))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
    return path


class AudioServerUnitTests(unittest.TestCase):
    """Exercises the server module directly; no socket, no model."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location("audio_server", SERVER)
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)

    def setUp(self):
        import tempfile

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "uploads").mkdir()
        (self.root / "data").mkdir()
        patcher = patch.object(self.server, "SITE_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        roots = patch.object(self.server, "ALLOWED_ROOTS",
                             (self.root / "uploads", self.root / "data"))
        roots.start()
        self.addCleanup(roots.stop)

    def test_a_path_outside_the_allowed_roots_is_refused(self):
        outside = self.root / "secret.wav"
        click_track(outside, seconds=0.2)
        for candidate in (str(outside), "/etc/passwd", "../../etc/passwd", ""):
            with self.assertRaises(ValueError):
                self.server.resolved_path(candidate)

    def test_a_symlink_escaping_the_roots_is_refused(self):
        target = self.root / "outside.wav"
        click_track(target, seconds=0.2)
        link = self.root / "uploads" / "link.wav"
        link.symlink_to(target)
        # It resolves to a file outside uploads/, so containment must fail even though the name
        # given is inside.
        with self.assertRaises(ValueError):
            self.server.resolved_path(str(link))

    def test_a_path_inside_uploads_resolves(self):
        good = click_track(self.root / "uploads" / "song.wav", seconds=0.2)
        self.assertEqual(self.server.resolved_path(str(good)), good.resolve())
        self.assertEqual(self.server.resolved_path("uploads/song.wav"), good.resolve())

    @unittest.skipUnless(HAS_LIBROSA, "librosa lives in /opt/studio/venvs/audio")
    def test_beats_finds_the_tempo_of_a_click_track(self):
        path = click_track(self.root / "uploads" / "click.wav", seconds=6.0, bpm=120)
        result = self.server.beats(path)
        self.assertAlmostEqual(result["duration_seconds"], 6.0, places=1)
        # A 6-second 8 kHz click is a thin signal, so the estimate lands near the truth rather
        # than on it, and librosa may lock on to half or double time. The claim under test is
        # that the tempo is defensible, not exact: the real accuracy check is the three songs in
        # uploads/, whose 104.2 BPM matches docs/GB10_SETUP.md.
        estimate = result["tempo_bpm"]
        self.assertTrue(any(abs(estimate - reference) / reference < 0.08 for reference in (60, 120, 240)),
                        f"{estimate} BPM is not within 8% of 60, 120 or 240")
        self.assertGreater(len(result["beats"]), 3)
        self.assertEqual(result["beats"], sorted(result["beats"]))
        self.assertTrue(all(0 <= t <= 6.1 for t in result["beats"]))
        self.assertGreater(len(result["energy_db"]), 10)

    def test_align_refuses_empty_or_oversized_lyrics(self):
        path = click_track(self.root / "uploads" / "click.wav", seconds=0.5)
        for bad in (None, "", "   ", "x" * (self.server.MAX_LYRICS + 1)):
            with self.assertRaises(ValueError):
                self.server.align(path, bad, "ja")


@unittest.skipUnless(HAS_BACKEND, "needs psycopg and the backend; run under the LTX venv")
class AudioEndpointTests(test_backend.BackendTests):
    """The ltx-api side: ownership, caching and what happens when the service is down."""

    def setUp(self):
        super().setUp()
        extra = [patch.object(contract, "api_key", return_value="a" * 48),
                 patch.object(backend, "AUDIO_CACHE_DIR", Path(self.temp.name) / "audio-cache")]
        for item in extra:
            item.start()
        self.patches = [*self.patches, *extra]

    def call(self, payload):
        return self.request("POST", "/api/v1/audio/analyze", json.dumps(payload),
                            {"Authorization": "Bearer " + "a" * 48,
                             "Content-Type": "application/json"})

    def upload_audio(self, owner=None):
        """An audio asset owned by `owner` (None means the service principal)."""
        from media_store import UPLOAD_DIR

        asset_id = "b" * 32
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        click_track(UPLOAD_DIR / f"{asset_id}.wav", seconds=1.0)
        (UPLOAD_DIR / f"{asset_id}.json").write_text(json.dumps({
            "id": asset_id, "filename": f"{asset_id}.wav", "name": "song.wav", "kind": "audio",
            "content_type": "audio/wav", "size_bytes": 16000, "owner_id": owner,
            "url": f"/api/v1/assets/{asset_id}/file"}), encoding="utf-8")
        return asset_id

    def test_an_asset_owned_by_someone_else_is_refused(self):
        asset_id = self.upload_audio(owner="another-account")
        with patch.object(backend.Handler, "can_access", return_value=False):
            status, _, body = self.call({"audio_id": asset_id})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["code"], "asset_forbidden")

    def test_a_missing_or_non_audio_asset_is_a_client_error(self):
        self.assertEqual(self.call({"audio_id": "c" * 32})[0], 400)
        self.assertEqual(self.call({})[0], 400)

    def test_the_service_being_down_never_blocks_generation(self):
        asset_id = self.upload_audio()
        with patch.object(backend, "audio_service", side_effect=OSError("connection refused")):
            status, _, body = self.call({"audio_id": asset_id})
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["code"], "audio_service_unavailable")
        # The job path is untouched: a plain validate still works with the service down.
        validate = self.request("POST", "/api/v1/validate", json.dumps({"prompt": "A calm sea."}),
                                {"Authorization": "Bearer " + "a" * 48,
                                 "Content-Type": "application/json"})
        self.assertEqual(validate[0], 200, validate[2])

    def test_a_result_carries_the_offset_and_is_cached(self):
        asset_id = self.upload_audio()
        fake = {"tempo_bpm": 120.0, "beats": [0.0, 0.5], "sections": [], "energy_db": [-1.0],
                "duration_seconds": 1.0, "sample_rate": 8000, "energy_hop_seconds": 0.1}
        with patch.object(backend, "audio_service", return_value=fake) as service:
            first = json.loads(self.call({"audio_id": asset_id})[2])
            second = json.loads(self.call({"audio_id": asset_id})[2])
        self.assertEqual(service.call_count, 1, "the second call must come from the cache")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["lyric_offset_seconds"], -0.9)
        self.assertIn("constant offset", first["lyric_offset_note"])
        self.assertEqual(first["beats"]["tempo_bpm"], 120.0)

    def test_different_lyrics_are_analysed_separately(self):
        asset_id = self.upload_audio()
        with patch.object(backend, "audio_service", return_value={"tempo_bpm": 120.0}) as service:
            self.call({"audio_id": asset_id, "lyrics": "one", "language": "ja"})
            self.call({"audio_id": asset_id, "lyrics": "two", "language": "ja"})
        # Two beat calls and two align calls: a different sheet is a different question.
        self.assertEqual(service.call_count, 4)


@unittest.skipUnless(os.environ.get("LTX_AUDIO_INTEGRATION") == "1",
                     "needs whisper large-v3; set LTX_AUDIO_INTEGRATION=1")
class AudioIntegrationTests(unittest.TestCase):
    def test_align_returns_word_times_for_real_audio(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("audio_server", SERVER)
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        songs = sorted((Path(server.SITE_ROOT) / "uploads").glob("*.wav"))
        self.assertTrue(songs, "no uploaded audio to align against")
        result = server.align(songs[0], "テスト", "ja")
        self.assertTrue(result["segments"])
        self.assertTrue(result["segments"][0]["words"])


if __name__ == "__main__":
    unittest.main()
