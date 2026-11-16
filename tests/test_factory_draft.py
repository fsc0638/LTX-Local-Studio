"""B4: the screenwriting draft. Nothing here reaches OpenAI - the transport is mocked.

The point of the endpoint is that the key stays on the host, so the tests check the boundary as
much as the happy path: an unreadable or world-readable key means the feature is off, a spent
budget is refused before any call, and a malformed answer costs the user nothing.
"""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import local_backend as backend
import test_factory_api


def openai_response(prompt="A lantern-lit alley.", action="She turns to the camera.", tokens=1200,
                    extra=None):
    payload = {
        "output": [{"type": "message", "content": [
            {"text": json.dumps({"prompt": prompt, "primary_action": action, **(extra or {})})}]}],
        "usage": {"total_tokens": tokens},
    }
    return io.BytesIO(json.dumps(payload).encode())


class DraftTests(test_factory_api.FactoryAPITests):
    def setUp(self):
        super().setUp()
        # A key that exists and is private; individual tests override it to test the refusals.
        self.key = patch.object(backend, "openai_key", return_value="sk-test")
        self.key.start()
        self.patches = [*self.patches, self.key]

    def project_with_shots(self):
        plan = self.new_project(shots=[
            test_factory_api.shot("first", title="OPENING"),
            test_factory_api.shot("second", title="VERSE"),
            test_factory_api.shot("third", title="CHORUS"),
        ])
        return plan

    def draft(self, shot_id, **headers):
        return self.call("POST", f"/api/v1/factory/shots/{shot_id}/draft", {}, **headers)

    def test_a_draft_returns_only_the_two_fields_the_schema_allows(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen",
                   return_value=openai_response(extra={"camera": "dolly", "seed": 7})) as sent:
            status, _, body = self.draft(plan["shots"][1]["id"])
        self.assertEqual(status, 200, body)
        draft = json.loads(body)
        self.assertEqual(draft["prompt"], "A lantern-lit alley.")
        self.assertEqual(draft["primary_action"], "She turns to the camera.")
        # Anything else the model volunteered is dropped rather than passed to the client.
        self.assertNotIn("camera", draft)
        self.assertNotIn("seed", draft)
        self.assertTrue(sent.called)

    def test_the_request_carries_the_schema_and_the_neighbouring_shots(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen", return_value=openai_response()) as sent:
            self.draft(plan["shots"][1]["id"])
        body = json.loads(sent.call_args[0][0].data.decode())
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(
            sorted(body["text"]["format"]["schema"]["properties"]), ["primary_action", "prompt"])
        self.assertFalse(body["text"]["format"]["schema"]["additionalProperties"])
        # The neighbours are what stop the draft repeating the shot before it.
        self.assertIn("OPENING", body["input"])
        self.assertIn("CHORUS", body["input"])

    def test_the_key_never_leaves_the_host(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen", return_value=openai_response()) as sent:
            status, _, body = self.draft(plan["shots"][0]["id"])
        self.assertEqual(status, 200)
        self.assertNotIn(b"sk-test", body)
        # It is sent to OpenAI and nowhere else.
        self.assertEqual(sent.call_args[0][0].headers["Authorization"], "Bearer sk-test")

    def test_tokens_are_charged_to_the_project(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen", return_value=openai_response(tokens=1500)):
            first = json.loads(self.draft(plan["shots"][0]["id"])[2])
        self.assertEqual(first["usage"], {"total_tokens": 1500, "calls": 1})
        with patch("urllib.request.urlopen", return_value=openai_response(tokens=500)):
            second = json.loads(self.draft(plan["shots"][1]["id"])[2])
        self.assertEqual(second["usage"], {"total_tokens": 2000, "calls": 2})

    def test_a_spent_budget_is_refused_before_any_call_is_made(self):
        plan = self.project_with_shots()
        with patch.object(backend, "DRAFT_TOKEN_LIMIT", 1000):
            with patch("urllib.request.urlopen", return_value=openai_response(tokens=1200)):
                self.assertEqual(self.draft(plan["shots"][0]["id"])[0], 200)
            with patch("urllib.request.urlopen") as sent:
                status, _, body = self.draft(plan["shots"][1]["id"])
        self.assertEqual(status, 429, body)
        self.assertEqual(json.loads(body)["code"], "draft_budget_spent")
        self.assertFalse(sent.called, "the budget must be checked before spending more")

    def test_drafting_is_off_when_the_host_has_no_key(self):
        plan = self.project_with_shots()
        with patch.object(backend, "openai_key", return_value=None):
            with patch("urllib.request.urlopen") as sent:
                status, _, body = self.draft(plan["shots"][0]["id"])
        self.assertEqual(status, 503, body)
        self.assertEqual(json.loads(body)["code"], "draft_unavailable")
        self.assertFalse(sent.called)

    def test_openai_being_unreachable_is_reported_not_raised(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            status, _, body = self.draft(plan["shots"][0]["id"])
        self.assertEqual(status, 503, body)
        self.assertEqual(json.loads(body)["code"], "draft_unavailable")

    def test_an_unreadable_answer_costs_the_user_nothing(self):
        plan = self.project_with_shots()
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"{\"output\": [] }")):
            status, _, body = self.draft(plan["shots"][0]["id"])
        self.assertEqual(status, 502, body)
        self.assertEqual(json.loads(body)["code"], "draft_unreadable")
        plan = json.loads(self.call("GET", f"/api/v1/factory/projects/{plan['id']}")[2])
        self.assertNotIn("total_tokens", json.dumps(plan))

    def test_another_account_cannot_draft_into_this_project(self):
        plan = self.project_with_shots()
        with patch.object(backend.FACTORY, "draft_context", return_value=None):
            with patch("urllib.request.urlopen") as sent:
                status, _, body = self.draft(plan["shots"][0]["id"])
        self.assertEqual(status, 404, body)
        self.assertEqual(json.loads(body)["code"], "shot_not_found")
        self.assertFalse(sent.called)

    def test_capabilities_say_whether_drafting_works_without_naming_the_key(self):
        status, _, body = self.call("GET", "/api/v1/capabilities")
        self.assertEqual(status, 200, body)
        self.assertIs(json.loads(body)["draft_available"], True)
        self.assertNotIn(b"sk-test", body)
        with patch.object(backend, "openai_key", return_value=None):
            self.assertIs(json.loads(self.call("GET", "/api/v1/capabilities")[2])["draft_available"],
                          False)


class KeyFileTests(unittest.TestCase):
    def test_a_key_readable_by_others_is_treated_as_absent(self):
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "openai"
            path.write_text("sk-loose", encoding="utf-8")
            path.chmod(0o644)
            with patch.object(backend, "OPENAI_KEY_FILE", path):
                self.assertIsNone(backend.openai_key())
            path.chmod(0o600)
            with patch.object(backend, "OPENAI_KEY_FILE", path):
                self.assertEqual(backend.openai_key(), "sk-loose")

    def test_a_missing_key_file_is_not_an_error(self):
        import pathlib

        with patch.object(backend, "OPENAI_KEY_FILE", pathlib.Path("/nonexistent/openai")):
            self.assertIsNone(backend.openai_key())


if __name__ == "__main__":
    unittest.main()
