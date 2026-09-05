import unittest

import conftest
from factory_store import FactoryStore, FactoryError


def shot(prompt="A quiet station at dawn.", **over):
    return {"title": over.pop("title", "OPENING"), "request": {"prompt": prompt, **over.pop("request", {})}, **over}


class FactoryStoreTests(conftest.DatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.start_database()
        self.store = FactoryStore()

    def project(self, owner="owner-1", **raw):
        return self.store.create_project(owner, {"title": "MV 01", **raw})

    def test_a_new_project_round_trips_as_a_v2_plan(self):
        plan = self.project(bible={"output": {"fps": 24}})
        self.assertEqual(plan["format"], "ltx-production-factory")
        self.assertEqual(plan["version"], 2)
        self.assertEqual(plan["status"], "draft")
        self.assertEqual(plan["bible"], {"output": {"fps": 24}})
        self.assertEqual(plan["shots"], [])
        self.assertEqual(self.store.get_project(plan["id"], "owner-1")["title"], "MV 01")

    def test_projects_are_invisible_to_other_accounts(self):
        plan = self.project()
        self.assertIsNone(self.store.get_project(plan["id"], "owner-2"))
        self.assertEqual(self.store.list_projects("owner-2"), [])
        self.assertIsNone(self.store.update_project(plan["id"], "owner-2", {"title": "stolen"}))
        self.assertIsNone(self.store.replace_shots(plan["id"], "owner-2", [shot()]))
        self.assertIsNone(self.store.start(plan["id"], "owner-2"))
        self.assertFalse(self.store.delete_project(plan["id"], "owner-2"))
        self.assertIsNotNone(self.store.get_project(plan["id"], "owner-1"))

    def test_replacing_shots_renumbers_and_keeps_one_key_each(self):
        plan = self.project()
        saved = self.store.replace_shots(plan["id"], "owner-1", [shot("first"), shot("second")])
        self.assertEqual([s["request"]["prompt"] for s in saved["shots"]], ["first", "second"])
        self.assertEqual(len({s["idempotencyKey"] for s in saved["shots"]}), 2)
        reordered = self.store.replace_shots(plan["id"], "owner-1", [shot("second"), shot("first")])
        self.assertEqual([s["request"]["prompt"] for s in reordered["shots"]], ["second", "first"])
        self.assertEqual(len(reordered["shots"]), 2)

    def test_a_shot_without_a_usable_prompt_is_refused(self):
        plan = self.project()
        for bad in ({}, {"prompt": ""}, {"prompt": "x" * 4001}):
            with self.assertRaises(FactoryError) as caught:
                self.store.replace_shots(plan["id"], "owner-1", [{"title": "T", "request": bad}])
            self.assertIn(caught.exception.code, ("invalid_request", "invalid_prompt"))

    def test_starting_queues_work_and_pausing_returns_it_to_draft(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        running = self.store.start(plan["id"], "owner-1")
        self.assertEqual(running["status"], "running")
        self.assertEqual([s["status"] for s in running["shots"]], ["queued", "queued"])
        paused = self.store.pause(plan["id"], "owner-1")
        self.assertEqual(paused["status"], "paused")
        self.assertEqual([s["status"] for s in paused["shots"]], ["draft", "draft"])

    def test_pausing_leaves_a_shot_already_on_the_gpu_alone(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        started = self.store.start(plan["id"], "owner-1")
        self.store.set_shot_status(started["shots"][0]["id"], "running")
        paused = self.store.pause(plan["id"], "owner-1")
        self.assertEqual([s["status"] for s in paused["shots"]], ["running", "draft"])

    def test_the_scheduler_takes_shots_in_order_and_stops_when_paused(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        started = self.store.start(plan["id"], "owner-1")
        first = self.store.next_queued_shot(plan["id"])
        self.assertEqual(first["request"]["prompt"], "a")
        self.store.set_shot_status(first["id"], "running")
        self.assertEqual(self.store.next_queued_shot(plan["id"])["request"]["prompt"], "b")
        self.store.pause(plan["id"], "owner-1")
        self.assertIsNone(self.store.next_queued_shot(plan["id"]))

    def test_a_failure_records_the_take_and_stops_the_line_together(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        started = self.store.start(plan["id"], "owner-1")
        self.store.record_take(started["shots"][0]["id"], status="failed",
                               reason="generation_failed", pause_project=True)
        after = self.store.get_project(plan["id"], "owner-1")
        self.assertEqual(after["status"], "paused")
        self.assertEqual(after["shots"][0]["status"], "failed")
        self.assertEqual(after["shots"][0]["error"], "generation_failed")
        # The line is stopped, so nothing else may be sent.
        self.assertIsNone(self.store.next_queued_shot(plan["id"]))

    def test_a_succeeded_shot_carries_its_output_and_completes_the_project(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a")])
        started = self.store.start(plan["id"], "owner-1")
        shot_id = started["shots"][0]["id"]
        with self.store.connect() as db:
            db.execute("INSERT INTO jobs(id,snapshot,updated_at) VALUES(%s,'{}'::jsonb,1)", ("abcdef123456",))
        self.store.record_take(shot_id, job_id="abcdef123456", status="succeeded",
                               output_url="/generated/a.mp4", poster_url="/generated/a.jpg")
        done = self.store.get_project(plan["id"], "owner-1")
        self.assertEqual(done["shots"][0]["outputUrl"], "/generated/a.mp4")
        self.assertEqual(done["shots"][0]["jobId"], "abcdef123456")
        self.assertTrue(self.store.finish_if_done(plan["id"]))
        self.assertEqual(self.store.get_project(plan["id"], "owner-1")["status"], "completed")
        self.assertEqual(len(self.store.takes(shot_id, "owner-1")), 1)
        self.assertIsNone(self.store.takes(shot_id, "owner-2"))

    def test_a_restart_requeues_shots_that_were_mid_flight(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        started = self.store.start(plan["id"], "owner-1")
        keys = {s["id"]: s["idempotencyKey"] for s in started["shots"]}
        self.store.set_shot_status(started["shots"][0]["id"], "running")
        self.assertEqual(self.store.recover(), 1)
        after = self.store.get_project(plan["id"], "owner-1")
        self.assertEqual([s["status"] for s in after["shots"]], ["queued", "queued"])
        # Same key, so a job that did reach the worker replays instead of running twice.
        self.assertEqual({s["id"]: s["idempotencyKey"] for s in after["shots"]}, keys)

    def test_the_queue_limit_counts_only_work_still_in_flight(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a"), shot("b")])
        self.assertEqual(self.store.queued_count("owner-1"), 0)
        self.store.start(plan["id"], "owner-1")
        self.assertEqual(self.store.queued_count("owner-1"), 2)
        self.assertEqual(self.store.queued_count("owner-2"), 0)

    def test_deleting_a_project_takes_its_shots_and_takes(self):
        plan = self.project()
        self.store.replace_shots(plan["id"], "owner-1", [shot("a")])
        started = self.store.start(plan["id"], "owner-1")
        self.store.record_take(started["shots"][0]["id"], status="succeeded", output_url="/generated/a.mp4")
        self.assertTrue(self.store.delete_project(plan["id"], "owner-1"))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM shots").fetchone()["n"], 0)
            self.assertEqual(db.execute("SELECT count(*) AS n FROM takes").fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
