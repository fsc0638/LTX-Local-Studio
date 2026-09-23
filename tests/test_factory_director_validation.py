"""Director request bounds that do not require the factory test database."""
import unittest

import local_backend as backend


def request(duration):
    return {
        "locale": "zh-TW",
        "audio_analysis": {
            "duration_seconds": duration,
            "beat_seconds": 0.544,
            "section_seconds": [80.0, 160.0],
            "energy_db": [-20.0] * 1989,
            "energy_hop_seconds": 0.1,
        },
        "shots": [
            {"shot_id": "shot-0", "start_seconds": 0, "end_seconds": 100,
             "kind": "lyric", "lyrics": ["first line"]},
            {"shot_id": "shot-1", "start_seconds": 100, "end_seconds": duration,
             "kind": "breathing", "lyrics": []},
        ],
    }


class DirectorRequestValidationTests(unittest.TestCase):
    def test_full_song_longer_than_generation_sequence_cap_is_valid(self):
        shots, audio, locale = backend.normalize_director_request(request(198.88))
        self.assertEqual(shots[-1]["end_seconds"], 198.88)
        self.assertEqual(audio["duration_seconds"], 198.88)
        self.assertEqual(locale, "zh-TW")

    def test_shot_cannot_extend_past_the_measured_song(self):
        payload = request(198.88)
        payload["shots"][-1]["end_seconds"] = 199
        with self.assertRaises(ValueError):
            backend.normalize_director_request(payload)

    def test_director_analysis_keeps_a_bounded_input(self):
        payload = request(backend.DIRECTOR_MAX_SECONDS + 0.001)
        payload["shots"][-1]["end_seconds"] = payload["audio_analysis"]["duration_seconds"]
        with self.assertRaises(ValueError):
            backend.normalize_director_request(payload)


if __name__ == "__main__":
    unittest.main()
