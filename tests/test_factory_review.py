"""C3: lights, overrides and the VLM's sentence. Nothing here reaches OpenAI.

The judge never vetoes. It lights a take red, and a person who accepts it anyway is recorded as
having overridden the light - who and when - so the cut can say why the take is in it. A take
the judge could not score is not red: no evidence against it is not evidence against it.
"""
import io
import json
import tempfile
import time
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import patch

import local_backend as backend
import review_rules
import test_factory_api
from production_store import ProductionStore

RED = {"media": {"kind": "video", "frozen_ratio": 0.1, "black_ratio": 0.0},
       "consistency": {"median": 0.62, "per_frame": [0.60, 0.64], "method_per_frame": ["face_facenet"] * 2},
       "style": {"median": 0.90}, "motion": {"median": 1.2}}
GREEN = {"media": {"kind": "video", "frozen_ratio": 0.1, "black_ratio": 0.0},
         "consistency": {"median": 0.91, "per_frame": [0.90, 0.92], "method_per_frame": ["face_facenet"] * 2},
         "style": {"median": 0.90}, "motion": {"median": 1.2}}
UNSCORED = {"status": "unscored", "reason": "judge_unavailable"}


def finished_job():
    job = {"id": uuid.uuid4().hex, "status": "succeeded", "created_at": time.time()}
    job["output_url"] = f"/generated/{job['id']}.mp4"
    job["poster_url"] = f"/generated/{job['id']}.jpg"
    ProductionStore().record(job)
    return job


class RuleTests(unittest.TestCase):
    def test_defaults_are_marked_uncalibrated(self):
        t = review_rules.resolve_thresholds({})
        self.assertEqual((t["cj"], t["sj"], t["mq"]), (0.80, 0.85, 0.50))
        self.assertFalse(t["calibrated"])

    def test_the_bible_then_the_shot_override_the_defaults(self):
        bible = {"thresholds": {"cj": 0.70, "calibrated": True}}
        self.assertEqual(review_rules.resolve_thresholds(bible)["cj"], 0.70)
        self.assertTrue(review_rules.resolve_thresholds(bible)["calibrated"])
        self.assertEqual(review_rules.resolve_thresholds(bible, {"thresholds": {"cj": 0.95}})["cj"], 0.95)
        # Nonsense is ignored, not applied.
        self.assertEqual(review_rules.resolve_thresholds({}, {"thresholds": {"cj": 7}})["cj"], 0.80)

    def test_strict_mode_uses_the_stricter_set(self):
        self.assertEqual(review_rules.resolve_thresholds({}, strict=True)["cj"], 0.85)
        bible = {"thresholds": {"cj": 0.70, "strict": {"cj": 0.78}}}
        self.assertEqual(review_rules.resolve_thresholds(bible, strict=True)["cj"], 0.78)

    def test_lights(self):
        t = review_rules.resolve_thresholds({})
        self.assertEqual(review_rules.lights(RED, t), {"cj": "red", "sj": "green", "mq": "green"})
        self.assertEqual(review_rules.lights(GREEN, t), {"cj": "green", "sj": "green", "mq": "green"})
        self.assertEqual(review_rules.lights(UNSCORED, t), {"cj": "unscored", "sj": "unscored", "mq": "unscored"})
        self.assertEqual(review_rules.lights(None, t)["cj"], "unscored")
        self.assertFalse(review_rules.is_red(UNSCORED, t), "no score is not a red light")

    def test_a_still_has_no_motion_score(self):
        still = {**GREEN, "media": {"kind": "image"}, "motion": None}
        self.assertIsNone(review_rules.take_scores(still)["mq"])
        self.assertEqual(review_rules.lights(still, review_rules.resolve_thresholds({}))["mq"], "unscored")


class ReviewAPITests(test_factory_api.FactoryAPITests):
    def setUp(self):
        super().setUp()
        self.key = patch.object(backend, "openai_key", return_value="sk-test")
        self.key.start()
        self.patches = [*self.patches, self.key]

    def take_with(self, scores, bible=None, request=None, shots=1):
        plan = self.new_project(bible=bible or {}, shots=[
            {"title": f"S{i}", "request": {"prompt": "a shot", **(request or {})}} for i in range(shots)])
        shot = plan["shots"][0]
        job = finished_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"], poster_url=job["poster_url"])
        if scores is not None:
            self.factory.record_scores(shot["id"], job["id"], scores)
        take = self.factory.takes(shot["id"], "@service")[0]
        return plan, shot, take

    def accept(self, take_id, **body):
        return self.call("POST", f"/api/v1/factory/takes/{take_id}/accept", body or None)

    # ---- overriding a red light ----

    def test_accepting_a_red_take_is_recorded_as_an_override_with_who_and_when(self):
        plan, shot, take = self.take_with(RED)
        before = time.time()
        status, _, body = self.accept(take["id"])
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["shots"][0]["acceptedTakeId"], take["id"],
                         "a red light does not stop a person from accepting")
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["verdict"], "overridden")
        self.assertEqual(stored["overriddenBy"], "@service")
        self.assertGreaterEqual(stored["overriddenAt"], before)

    def test_accepting_a_green_take_is_a_plain_acceptance(self):
        plan, shot, take = self.take_with(GREEN)
        self.accept(take["id"])
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["verdict"], "accepted")
        self.assertIsNone(stored["overriddenBy"])

    def test_a_take_the_judge_could_not_score_is_not_an_override(self):
        plan, shot, take = self.take_with(UNSCORED)
        self.accept(take["id"])
        self.assertEqual(self.factory.takes(shot["id"], "@service")[0]["verdict"], "accepted")

    def test_a_red_take_is_never_accepted_automatically(self):
        plan, shot, take = self.take_with(RED)
        self.assertIsNone(self.factory.get_project(plan["id"], "@service")["shots"][0]["acceptedTakeId"])
        self.assertEqual(take["verdict"], "pending")

    def test_the_shots_own_threshold_decides_its_light(self):
        plan, shot, take = self.take_with(RED, request={"thresholds": {"cj": 0.60}})
        self.accept(take["id"])
        self.assertEqual(self.factory.takes(shot["id"], "@service")[0]["verdict"], "accepted")

    def test_strict_mode_can_turn_a_green_take_red(self):
        borderline = {**GREEN, "consistency": {**GREEN["consistency"], "median": 0.82}}
        plan, shot, take = self.take_with(borderline)
        self.accept(take["id"], strict=True)
        self.assertEqual(self.factory.takes(shot["id"], "@service")[0]["verdict"], "overridden")

    def test_the_light_is_computed_here_not_trusted_from_the_client(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(review_rules, "is_red", wraps=review_rules.is_red) as computed:
            self.accept(take["id"])
        self.assertTrue(computed.called)

    def test_choosing_another_take_clears_the_earlier_override(self):
        plan, shot, first = self.take_with(RED)
        self.accept(first["id"])
        job = finished_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        self.factory.record_scores(shot["id"], job["id"], GREEN)
        second = self.factory.takes(shot["id"], "@service")[0]
        self.accept(second["id"])
        by_id = {t["id"]: t for t in self.factory.takes(shot["id"], "@service")}
        self.assertEqual(by_id[first["id"]]["verdict"], "pending")
        self.assertIsNone(by_id[first["id"]]["overriddenBy"])
        self.assertEqual(by_id[second["id"]]["verdict"], "accepted")

    # ---- the project-level listing the page reads ----

    def test_project_takes_are_grouped_with_lights_and_thresholds(self):
        plan, shot, take = self.take_with(RED, shots=2)
        status, _, body = self.call("GET", f"/api/v1/factory/projects/{plan['id']}/takes")
        self.assertEqual(status, 200, body)
        grouped = json.loads(body)["takes"]
        self.assertEqual(list(grouped), [shot["id"]])
        entry = grouped[shot["id"]][0]
        self.assertEqual(entry["lights"], {"cj": "red", "sj": "green", "mq": "green"})
        self.assertFalse(entry["thresholds"]["calibrated"])
        self.assertEqual(entry["thresholds"]["cj"], 0.80)

    def test_project_takes_are_owner_scoped(self):
        plan, shot, take = self.take_with(GREEN)
        self.assertIsNone(self.factory.project_takes(plan["id"], "someone-else"))

    # ---- the VLM sentence ----

    def opinion_response(self, sentence="臉像、光線偏平，可留但建議補側光。", tokens=800):
        payload = {"output": [{"type": "message", "content": [
            {"text": json.dumps({"sentence": sentence})}]}], "usage": {"total_tokens": tokens}}
        return io.BytesIO(json.dumps(payload).encode())

    def poster(self):
        directory = tempfile.mkdtemp()
        path = Path(directory) / "poster.jpg"
        path.write_bytes(b"\\xff\\xd8\\xff\\xe0 not really a jpeg")
        return path

    def test_an_opinion_is_stored_on_the_take_and_charged_to_the_project(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(backend, "output_location", return_value=self.poster()):
            with patch("urllib.request.urlopen", return_value=self.opinion_response()) as sent:
                status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/opinion", {})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["opinion"]["text"], "臉像、光線偏平，可留但建議補側光。")
        request = json.loads(sent.call_args[0][0].data.decode())
        self.assertEqual(request["input"][0]["content"][1]["type"], "input_image")
        self.assertIn("Lights", request["input"][0]["content"][0]["text"])
        self.assertEqual(request["text"]["format"]["schema"]["properties"].keys(), {"sentence"})
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["opinion"]["text"], "臉像、光線偏平，可留但建議補側光。")
        usage = self.factory.draft_context(shot["id"], "@service")["usage"]
        self.assertEqual(usage["total_tokens"], 800)

    def test_a_take_without_a_poster_gets_no_opinion_and_costs_nothing(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(backend, "output_location", return_value=Path("/nonexistent.jpg")):
            with patch("urllib.request.urlopen") as sent:
                status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/opinion", {})
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "poster_missing")
        self.assertFalse(sent.called)

    def test_the_opinion_shares_the_draft_budget(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(backend, "DRAFT_TOKEN_LIMIT", 100):
            self.factory.add_draft_usage(plan["id"], 100)
            with patch.object(backend, "output_location", return_value=self.poster()):
                with patch("urllib.request.urlopen") as sent:
                    status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/opinion", {})
        self.assertEqual(status, 429, body)
        self.assertFalse(sent.called)

    def test_disagreeing_keeps_the_sentence_and_records_who(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(backend, "output_location", return_value=self.poster()):
            with patch("urllib.request.urlopen", return_value=self.opinion_response()):
                self.call("POST", f"/api/v1/factory/takes/{take['id']}/opinion", {})
        status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/disagree", {})
        self.assertEqual(status, 200, body)
        stored = self.factory.takes(shot["id"], "@service")[0]["opinion"]
        self.assertEqual(stored["text"], "臉像、光線偏平，可留但建議補側光。")
        self.assertEqual(stored["disagreed_by"], "@service")
        self.assertIsNotNone(stored["disagreed_at"])

    def test_disagreeing_with_nothing_is_an_error(self):
        plan, shot, take = self.take_with(RED)
        status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/disagree", {})
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "no_opinion")

    def test_openai_down_is_reported_and_nothing_is_stored(self):
        plan, shot, take = self.take_with(RED)
        with patch.object(backend, "output_location", return_value=self.poster()):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
                status, _, body = self.call("POST", f"/api/v1/factory/takes/{take['id']}/opinion", {})
        self.assertEqual(status, 503, body)
        self.assertIsNone(self.factory.takes(shot["id"], "@service")[0]["opinion"])


if __name__ == "__main__":
    unittest.main()
