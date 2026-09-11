"""Whole-song AI director analysis. OpenAI is mocked; no project material leaves the test."""
import io
import json
from unittest.mock import patch

import local_backend as backend
import test_factory_api


SHOT_FIELDS = (
    "scene", "mood", "atmosphere", "action", "progression", "emotion", "camera",
    "breathing", "prompt",
)


def suggestion(shot_id):
    return {"shot_id": shot_id, **{field: f"{field} for {shot_id}" for field in SHOT_FIELDS}}


def openai_response(ids=("shot-0", "shot-1"), tokens=2400):
    analysis = {
        "song": {
            "genre": "Dream pop",
            "lyrical_meaning": "Learning to let go",
            "visual_concept": "A city slowly becoming weightless",
            "emotional_arc": "Isolation to release",
            "producer_strategy": "Reserve wide frames for the chorus",
        },
        "shots": [suggestion(identity) for identity in ids],
    }
    payload = {"output": [{"type": "message", "content": [
        {"text": json.dumps(analysis)}]}], "usage": {"total_tokens": tokens}}
    return io.BytesIO(json.dumps(payload).encode())


class DirectorDraftTests(test_factory_api.FactoryAPITests):
    def setUp(self):
        super().setUp()
        key = patch.object(backend, "openai_key", return_value="sk-test")
        key.start()
        self.patches.append(key)

    def project(self):
        return self.new_project(bible={
            "output": {},
            "lyric_offset_seconds": -0.9,
            "character": {"name": "Mina", "description": "Short black hair, red coat",
                          "references": []},
            "music": {"audio_id": "audio-1", "audio_start_seconds": 0,
                      "audio_mode": "soundtrack", "lrc": "[00:01.00]飛向夜空",
                      "lrc_timebase": "output"},
        })

    def director_payload(self):
        return {"locale": "zh-TW", "audio_analysis": {
            "duration_seconds": 12, "beat_seconds": 0.5, "section_seconds": [8],
            "energy_db": [-18, -12, -8], "energy_hop_seconds": 0.1,
        }, "shots": [
            {"shot_id": "shot-0", "start_seconds": 0, "end_seconds": 8,
             "kind": "lyric", "lyrics": ["飛向夜空"]},
            {"shot_id": "shot-1", "start_seconds": 8, "end_seconds": 12,
             "kind": "breathing", "lyrics": []},
        ]}

    def draft(self, project_id, payload=None):
        return self.call("POST", f"/api/v1/factory/projects/{project_id}/director-draft",
                         payload or self.director_payload())

    def test_whole_song_and_every_shot_are_returned_without_auto_applying(self):
        plan = self.project()
        with patch("urllib.request.urlopen", return_value=openai_response()) as sent:
            status, _, body = self.draft(plan["id"])
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(result["analysis"]["song"]["genre"], "Dream pop")
        self.assertEqual([row["shot_id"] for row in result["analysis"]["shots"]],
                         ["shot-0", "shot-1"])
        self.assertEqual(result["usage"], {"total_tokens": 2400, "calls": 1})
        outbound = json.loads(sent.call_args[0][0].data.decode())
        self.assertEqual(outbound["text"]["format"]["schema"], backend.DIRECTOR_SCHEMA)
        self.assertIn("[00:01.00]飛向夜空", outbound["input"])
        self.assertIn("breathing", outbound["input"])
        self.assertIn("energy_db", outbound["input"])
        self.assertNotIn(b"sk-test", body)

    def test_bad_shot_input_is_refused_before_openai(self):
        plan = self.project()
        invalid = self.director_payload()
        invalid["shots"][1]["shot_id"] = "shot-0"
        with patch("urllib.request.urlopen") as sent:
            status, _, body = self.draft(plan["id"], invalid)
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "director_invalid")
        self.assertFalse(sent.called)

    def test_missing_or_reordered_model_shots_are_not_charged(self):
        plan = self.project()
        with patch("urllib.request.urlopen", return_value=openai_response(("shot-1", "shot-0"))):
            status, _, body = self.draft(plan["id"])
        self.assertEqual(status, 502, body)
        self.assertEqual(json.loads(body)["code"], "director_unreadable")
        stored = self.factory.director_context(plan["id"], "@service")
        self.assertEqual(stored["usage"], {})

    def test_project_ownership_and_configuration_are_enforced(self):
        missing = "11111111-1111-4111-8111-111111111111"
        with patch("urllib.request.urlopen") as sent:
            self.assertEqual(self.draft(missing)[0], 404)
            with patch.object(backend, "openai_key", return_value=None):
                plan = self.project()
                status, _, body = self.draft(plan["id"])
        self.assertEqual(status, 503, body)
        self.assertEqual(json.loads(body)["code"], "draft_unavailable")
        self.assertFalse(sent.called)


if __name__ == "__main__":
    import unittest
    unittest.main()
