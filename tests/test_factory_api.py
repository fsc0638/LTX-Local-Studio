import json
import unittest
from unittest.mock import patch

import conftest
import local_backend as backend
import test_backend
import worker_contract as contract
from factory_store import FactoryStore


def shot(prompt="A quiet station at dawn.", **over):
    return {"title": over.pop("title", "OPENING"), "request": {"prompt": prompt}, **over}


class FactoryAPITests(test_backend.BackendTests):
    def setUp(self):
        super().setUp()
        self.factory = FactoryStore()
        # /api/v1/* is worker-credentialed, exactly like the job endpoints.
        extra = [patch.object(backend, "FACTORY", self.factory),
                 patch.object(backend, "STORE_ERROR", ""),
                 patch.object(contract, "api_key", return_value="a" * 48)]
        for item in extra:
            item.start()
        self.patches = [*self.patches, *extra]

    def call(self, method, path, payload=None, **headers):
        body = json.dumps(payload) if payload is not None else None
        sent = {"Authorization": "Bearer " + "a" * 48, **headers}
        if body is not None:
            sent["Content-Type"] = "application/json"
        return self.request(method, path, body, sent)

    def new_project(self, **raw):
        status, _, body = self.call("POST", "/api/v1/factory/projects", {"title": "MV 01", **raw})
        self.assertEqual(status, 201, body)
        return json.loads(body)

    def test_a_project_is_created_listed_and_fetched_as_a_v2_plan(self):
        plan = self.new_project(bible={"output": {"fps": 24}})
        self.assertEqual(plan["format"], "ltx-production-factory")
        self.assertEqual(plan["version"], 2)
        listed = json.loads(self.call("GET", "/api/v1/factory/projects")[2])["projects"]
        self.assertEqual([p["id"] for p in listed], [plan["id"]])
        fetched = json.loads(self.call("GET", f"/api/v1/factory/projects/{plan['id']}")[2])
        self.assertEqual(fetched["bible"], {"output": {"fps": 24}})

    def test_importing_a_plan_with_shots_keeps_them(self):
        plan = self.new_project(shots=[shot("first"), shot("second")])
        self.assertEqual([s["request"]["prompt"] for s in plan["shots"]], ["first", "second"])
        self.assertEqual(len({s["idempotencyKey"] for s in plan["shots"]}), 2)

    def test_a_shot_without_a_prompt_is_rejected_before_any_gpu_work(self):
        plan = self.new_project()
        status, _, body = self.call("POST", f"/api/v1/factory/projects/{plan['id']}/shots",
                                    {"shots": [{"title": "T", "request": {}}]})
        self.assertEqual(status, 400)
        self.assertIn(json.loads(body)["code"], ("invalid_request", "invalid_prompt"))

    def test_run_queues_and_pause_stops_without_killing_a_running_shot(self):
        plan = self.new_project(shots=[shot("a"), shot("b")])
        running = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        self.assertEqual(running["status"], "running")
        self.assertEqual([s["status"] for s in running["shots"]], ["queued", "queued"])
        self.factory.set_shot_status(running["shots"][0]["id"], "running")
        paused = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/pause")[2])
        self.assertEqual(paused["status"], "paused")
        self.assertEqual([s["status"] for s in paused["shots"]], ["running", "draft"])

    def test_an_unknown_project_is_not_found_rather_than_an_error(self):
        missing = "11111111-1111-4111-8111-111111111111"
        self.assertEqual(self.call("GET", f"/api/v1/factory/projects/{missing}")[0], 404)
        self.assertEqual(self.call("POST", f"/api/v1/factory/projects/{missing}/run")[0], 404)
        self.assertEqual(self.call("DELETE", f"/api/v1/factory/projects/{missing}")[0], 404)

    def test_deleting_a_project_removes_it(self):
        plan = self.new_project(shots=[shot()])
        self.assertEqual(self.call("DELETE", f"/api/v1/factory/projects/{plan['id']}")[0], 200)
        self.assertEqual(self.call("GET", f"/api/v1/factory/projects/{plan['id']}")[0], 404)

    def test_takes_are_listed_for_a_shot(self):
        plan = self.new_project(shots=[shot()])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        shot_id = started["shots"][0]["id"]
        self.factory.record_take(shot_id, status="succeeded", output_url="/generated/a.mp4")
        takes = json.loads(self.call("GET", f"/api/v1/factory/shots/{shot_id}/takes")[2])["takes"]
        self.assertEqual(len(takes), 1)
        self.assertEqual(takes[0]["outputUrl"], "/generated/a.mp4")
        self.assertEqual(takes[0]["verdict"], "pending")

    def test_a_busy_worker_keeps_the_shot_queued_instead_of_failing_it(self):
        plan = self.new_project(shots=[shot()])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        busy = (409, {"error": "GPU busy", "code": "worker_busy"})
        with patch.object(backend, "submit_job", return_value=busy):
            self.assertFalse(backend.factory_send(
                {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}},
                self.factory.next_queued_shot(plan["id"])))
        after = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(after["shots"][0]["status"], "queued")
        self.assertEqual(after["status"], "running")

    def test_a_refused_request_fails_the_shot_and_stops_the_line(self):
        plan = self.new_project(shots=[shot()])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        with patch.object(backend.worker, "validate_request", side_effect=ValueError("bad model")):
            self.assertFalse(backend.factory_send(
                {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}},
                self.factory.next_queued_shot(plan["id"])))
        after = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(after["shots"][0]["status"], "failed")
        self.assertEqual(after["status"], "paused")
        self.assertIn("bad model", after["shots"][0]["error"])

    def test_a_submitted_shot_is_linked_to_its_job_and_settles_with_it(self):
        plan = self.new_project(shots=[shot()])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        shot_row = self.factory.next_queued_shot(plan["id"])
        with self.factory.connect() as db:
            db.execute("INSERT INTO jobs(id,snapshot,updated_at) VALUES('abcdef123456','{}'::jsonb,1)")
        with patch.object(backend, "submit_job", return_value=(202, {"id": "abcdef123456"})):
            self.assertTrue(backend.factory_send(
                {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}}, shot_row))
        linked = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(linked["shots"][0]["status"], "running")
        self.assertEqual(linked["shots"][0]["jobId"], "abcdef123456")
        with patch.dict(backend.JOBS, {"abcdef123456": {
                "id": "abcdef123456", "status": "succeeded",
                "output_url": "/generated/a.mp4", "poster_url": "/generated/a.jpg"}}, clear=False):
            backend.factory_collect({"id": shot_row["id"]}, "abcdef123456")
        done = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(done["shots"][0]["status"], "succeeded")
        self.assertEqual(done["shots"][0]["outputUrl"], "/generated/a.mp4")
        self.assertTrue(self.factory.finish_if_done(plan["id"]))
        self.assertEqual(self.factory.get_project(plan["id"], "@service")["status"], "completed")

    def test_a_restart_opens_a_new_take_instead_of_replaying_the_dead_job(self):
        """The bug B1 acceptance found: after a restart the shot kept its idempotency key, so the
        worker replayed the interrupted job forever and the queue could never move on."""
        plan = self.new_project(shots=[shot()])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        shot_row = self.factory.next_queued_shot(plan["id"])
        original_key = shot_row["idempotency_key"]
        project = {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}}
        with self.factory.connect() as db:
            db.execute("INSERT INTO jobs(id,snapshot,updated_at) VALUES('abcdef123456','{}'::jsonb,1)")
        with patch.object(backend, "submit_job", return_value=(202, {"id": "abcdef123456"})):
            self.assertTrue(backend.factory_send(project, shot_row))
        # The API restarts: the job is marked interrupted and the shot returns to the queue.
        self.factory.recover()
        interrupted = {"id": "abcdef123456", "status": "interrupted",
                       "error": {"code": "worker_restarted", "retryable": True}}
        with patch.object(backend, "replay_job", return_value=(200, {**interrupted, "idempotent_replay": True})):
            requeued = self.factory.next_queued_shot(plan["id"])
            backend.factory_send(project, requeued)
        after = self.factory.get_project(plan["id"], "@service")
        # It must not fail the shot and stop the line; a restart is not the shot's fault.
        self.assertEqual(after["status"], "running")
        self.assertEqual(after["shots"][0]["status"], "queued")
        self.assertNotEqual(after["shots"][0]["idempotencyKey"], original_key)

    def test_a_replayed_success_is_recorded_without_running_the_gpu_again(self):
        plan = self.new_project(shots=[shot()])
        json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        shot_row = self.factory.next_queued_shot(plan["id"])
        project = {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}}
        with self.factory.connect() as db:
            db.execute("INSERT INTO jobs(id,snapshot,updated_at) VALUES('abcdef123456','{}'::jsonb,1)")
        done = {"id": "abcdef123456", "status": "succeeded", "output_url": "/generated/a.mp4",
                "poster_url": "/generated/a.jpg", "idempotent_replay": True}
        with patch.object(backend, "replay_job", return_value=(200, done)):
            with patch.object(backend, "submit_job", side_effect=AssertionError("must not submit")):
                self.assertTrue(backend.factory_send(project, shot_row))
        after = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(after["shots"][0]["status"], "succeeded")
        self.assertEqual(after["shots"][0]["outputUrl"], "/generated/a.mp4")

    def test_a_replayed_failure_still_stops_the_line_for_a_person(self):
        plan = self.new_project(shots=[shot()])
        json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        shot_row = self.factory.next_queued_shot(plan["id"])
        project = {"id": plan["id"], "owner_id": "@service", "title": "MV 01", "bible": {}}
        with self.factory.connect() as db:
            db.execute("INSERT INTO jobs(id,snapshot,updated_at) VALUES('abcdef123456','{}'::jsonb,1)")
        failed = {"id": "abcdef123456", "status": "failed",
                  "error": {"code": "generation_failed"}, "idempotent_replay": True}
        with patch.object(backend, "replay_job", return_value=(200, failed)):
            self.assertFalse(backend.factory_send(project, shot_row))
        after = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(after["status"], "paused")
        self.assertEqual(after["shots"][0]["status"], "failed")
        self.assertIn("generation_failed", after["shots"][0]["error"])

    def test_a_restart_resumes_from_the_database(self):
        plan = self.new_project(shots=[shot("a"), shot("b")])
        started = json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])
        self.factory.set_shot_status(started["shots"][0]["id"], "submitting")
        # A new process sees only what the database holds.
        fresh = FactoryStore()
        self.assertEqual(fresh.recover(), 1)
        resumed = fresh.get_project(plan["id"], "@service")
        self.assertEqual([s["status"] for s in resumed["shots"]], ["queued", "queued"])
        self.assertEqual([s["idempotencyKey"] for s in resumed["shots"]],
                         [s["idempotencyKey"] for s in started["shots"]])


if __name__ == "__main__":
    unittest.main()
