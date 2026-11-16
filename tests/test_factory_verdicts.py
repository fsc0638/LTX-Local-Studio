"""C2: takes carry verdicts, shots point at the accepted one, rejections teach the next take.

Three things the roadmap names as acceptance, each as a test: two rejections accumulate rather
than overwrite; deleting an output touches only its own take; only one take per shot is accepted,
and that is a property of the table.
"""
import json
import time
import unittest
import uuid

import psycopg

import test_factory_api
from production_store import ProductionStore


def finished_job():
    job = {"id": uuid.uuid4().hex, "status": "succeeded", "created_at": time.time(),
           "output_url": None}
    job["output_url"] = f"/generated/{job['id']}.mp4"
    ProductionStore().record(job)
    return job


class VerdictTests(test_factory_api.FactoryAPITests):
    def shot_with_take(self, prompt="A quiet station at dawn.", shots=1):
        plan = self.new_project(shots=[test_factory_api.shot(prompt) for _ in range(shots)])
        shot = plan["shots"][0]
        job = finished_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        take = self.factory.takes(shot["id"], "@service")[0]
        return plan, shot, take

    def reject(self, take_id, reason):
        return self.call("POST", f"/api/v1/factory/takes/{take_id}/reject", {"reason": reason})

    def accept(self, take_id):
        return self.call("POST", f"/api/v1/factory/takes/{take_id}/accept", {})

    # ---- rejection ----

    def test_a_rejection_needs_a_reason(self):
        _, _, take = self.shot_with_take()
        status, _, body = self.reject(take["id"], "   ")
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "reason_required")
        self.assertEqual(self.factory.takes(take["shot_id"] if "shot_id" in take else
                                            self.shot_id_of(take), "@service")[0]["verdict"],
                         "pending")

    def shot_id_of(self, take):
        with self.factory.connect() as db:
            return str(db.execute("SELECT shot_id FROM takes WHERE id=%s",
                                  (take["id"],)).fetchone()["shot_id"])

    def test_a_rejection_opens_a_new_take_with_the_reason_in_its_prompt(self):
        plan, shot, take = self.shot_with_take("A quiet station at dawn.")
        status, _, body = self.reject(take["id"], "臉不像參照圖")
        self.assertEqual(status, 200, body)
        after = json.loads(body)["shots"][0]
        self.assertEqual(after["request"]["prompt"], "A quiet station at dawn.\n避免：臉不像參照圖")
        self.assertIn("prompt", after["pinned"], "the amended prompt must survive a reprojection")
        self.assertEqual(after["status"], "draft")
        self.assertNotEqual(after["idempotencyKey"], shot["idempotencyKey"],
                            "a new attempt needs a new key or the worker replays the old job")
        history = self.factory.takes(shot["id"], "@service")
        self.assertEqual(history[0]["verdict"], "rejected")
        self.assertEqual(history[0]["reason"], "臉不像參照圖")

    def test_two_rejections_accumulate_and_neither_is_lost(self):
        plan, shot, first = self.shot_with_take("Opening.")
        self.reject(first["id"], "第一個原因")
        second_job = finished_job()
        self.factory.record_take(shot["id"], job_id=second_job["id"], status="succeeded",
                                 output_url=second_job["output_url"])
        second = self.factory.takes(shot["id"], "@service")[0]
        self.assertNotEqual(second["id"], first["id"])
        status, _, body = self.reject(second["id"], "第二個原因")
        self.assertEqual(status, 200, body)
        prompt = json.loads(body)["shots"][0]["request"]["prompt"]
        self.assertEqual(prompt, "Opening.\n避免：第一個原因\n避免：第二個原因")
        verdicts = [t["verdict"] for t in self.factory.takes(shot["id"], "@service")]
        self.assertEqual(sorted(verdicts), ["rejected", "rejected"])

    def test_the_user_can_still_rewrite_the_prompt_after_a_rejection(self):
        plan, shot, take = self.shot_with_take("Opening.")
        after = json.loads(self.reject(take["id"], "太暗")[2])["shots"][0]
        after["request"]["prompt"] = "Opening, brighter.\n避免：太暗（已處理：加了頂光）"
        status, _, body = self.call("POST", f"/api/v1/factory/projects/{plan['id']}/shots",
                                    {"shots": [after]})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["shots"][0]["request"]["prompt"],
                         "Opening, brighter.\n避免：太暗（已處理：加了頂光）")

    # ---- acceptance ----

    def test_accepting_a_take_points_the_shot_at_it(self):
        plan, shot, take = self.shot_with_take()
        status, _, body = self.accept(take["id"])
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["shots"][0]["acceptedTakeId"], take["id"])
        self.assertEqual(self.factory.takes(shot["id"], "@service")[0]["verdict"], "accepted")

    def test_accepting_a_second_take_returns_the_first_to_pending_and_only_one_is_accepted(self):
        plan, shot, first = self.shot_with_take()
        self.accept(first["id"])
        job = finished_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        second = self.factory.takes(shot["id"], "@service")[0]
        after = json.loads(self.accept(second["id"])[2])["shots"][0]
        self.assertEqual(after["acceptedTakeId"], second["id"])
        by_id = {t["id"]: t["verdict"] for t in self.factory.takes(shot["id"], "@service")}
        # 'overridden' is reserved for a person overruling a red light (C3); a superseded take is
        # simply no longer chosen, so it goes back to pending.
        self.assertEqual(by_id[first["id"]], "pending")
        self.assertEqual(by_id[second["id"]], "accepted")
        self.assertEqual(list(by_id.values()).count("accepted"), 1)

    def test_one_take_cannot_be_accepted_by_two_shots_even_by_direct_sql(self):
        plan, shot, take = self.shot_with_take(shots=2)
        other = plan["shots"][1]
        self.accept(take["id"])
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.factory.connect() as db:
                db.execute("UPDATE shots SET accepted_take_id=%s WHERE id=%s",
                           (take["id"], other["id"]))

    def test_rejecting_the_accepted_take_clears_the_pointer(self):
        plan, shot, take = self.shot_with_take()
        self.accept(take["id"])
        after = json.loads(self.reject(take["id"], "重看之後不行")[2])["shots"][0]
        self.assertIsNone(after["acceptedTakeId"])

    def test_a_deleted_take_cannot_be_accepted(self):
        plan, shot, take = self.shot_with_take()
        self.factory.mark_take_deleted(take["jobId"])
        status, _, body = self.accept(take["id"])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "take_deleted")

    def test_another_account_cannot_judge_this_take(self):
        plan, shot, take = self.shot_with_take()
        self.assertIsNone(self.factory.accept_take(take["id"], "someone-else"))
        self.assertIsNone(self.factory.reject_take(take["id"], "someone-else", "no"))
        self.assertEqual(self.factory.takes(shot["id"], "@service")[0]["verdict"], "pending")

    # ---- deletion isolation ----

    def test_deleting_an_output_marks_only_its_own_take(self):
        plan, shot, first = self.shot_with_take(shots=2)
        job = finished_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        sibling = plan["shots"][1]
        sibling_job = finished_job()
        self.factory.record_take(sibling["id"], job_id=sibling_job["id"], status="succeeded",
                                 output_url=sibling_job["output_url"])
        self.accept(first["id"])

        self.assertEqual(self.factory.mark_take_deleted(first["jobId"]), 1)

        takes = {t["id"]: t for t in self.factory.takes(shot["id"], "@service")}
        self.assertIsNotNone(takes[first["id"]]["deletedAt"])
        others = [t for t in takes.values() if t["id"] != first["id"]]
        self.assertEqual(len(others), 1)
        self.assertIsNone(others[0]["deletedAt"])
        self.assertIsNone(self.factory.takes(sibling["id"], "@service")[0]["deletedAt"])
        after = self.factory.get_project(plan["id"], "@service")
        self.assertEqual(after["shots"][0]["status"], "succeeded", "the shot is untouched")
        self.assertIsNone(after["shots"][0]["acceptedTakeId"],
                          "a shot cannot keep an accepted take whose output is gone")
        # The plan shows the surviving take's output, not the deleted one's.
        self.assertEqual(after["shots"][0]["outputUrl"], job["output_url"])

    def test_deleting_twice_is_idempotent(self):
        plan, shot, take = self.shot_with_take()
        self.assertEqual(self.factory.mark_take_deleted(take["jobId"]), 1)
        self.assertEqual(self.factory.mark_take_deleted(take["jobId"]), 0)

    # ---- takes must outlive plan edits ----

    def test_editing_the_plan_keeps_every_take(self):
        plan, shot, take = self.shot_with_take(shots=2)
        self.accept(take["id"])
        reordered = [plan["shots"][1], {**plan["shots"][0], "title": "RENAMED"}]
        status, _, body = self.call("POST", f"/api/v1/factory/projects/{plan['id']}/shots",
                                    {"shots": reordered})
        self.assertEqual(status, 200, body)
        after = json.loads(body)
        self.assertEqual([s["title"] for s in after["shots"]], ["OPENING", "RENAMED"])
        self.assertEqual(after["shots"][1]["acceptedTakeId"], take["id"])
        self.assertEqual(len(self.factory.takes(shot["id"], "@service")), 1)

    def test_dropping_a_shot_from_the_plan_drops_its_takes_and_nothing_else(self):
        plan, shot, take = self.shot_with_take(shots=2)
        kept = plan["shots"][1]
        self.call("POST", f"/api/v1/factory/projects/{plan['id']}/shots", {"shots": [kept]})
        self.assertIsNone(self.factory.takes(shot["id"], "@service"))
        self.assertEqual(self.factory.takes(kept["id"], "@service"), [])

    def test_a_shot_id_from_another_project_is_refused(self):
        plan, shot, take = self.shot_with_take()
        other = self.new_project()
        status, _, body = self.call("POST", f"/api/v1/factory/projects/{other['id']}/shots",
                                    {"shots": [shot]})
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "invalid_shots")
        self.assertEqual(len(self.factory.takes(shot["id"], "@service")), 1,
                         "the take stayed with its own project")


if __name__ == "__main__":
    unittest.main()


# Through the real recycle-bin route, with session auth, so the hook in the DELETE handler is
# what gets exercised rather than the store method it calls.
import test_media_deletion  # noqa: E402
from unittest.mock import patch  # noqa: E402

import local_backend as backend  # noqa: E402
from factory_store import FactoryStore  # noqa: E402


class RecycleBinTests(test_media_deletion.DeletionTests):
    def setUp(self):
        super().setUp()
        self.factory = FactoryStore()
        factory_patch = patch.object(backend, "FACTORY", self.factory)
        factory_patch.start()
        self.addCleanup(factory_patch.stop)

    def test_the_recycle_bin_marks_the_take_and_leaves_the_shot_alone(self):
        job = self.job()
        owner = job["owner_id"]
        plan = self.factory.create_project(owner, {"title": "MV"})
        plan = self.factory.replace_shots(plan["id"], owner, [
            {"title": "ONE", "request": {"prompt": "one"}},
            {"title": "TWO", "request": {"prompt": "two"}}])
        one, two = plan["shots"]
        self.factory.record_take(one["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        self.factory.accept_take(self.factory.takes(one["id"], owner)[0]["id"], owner)
        other_job = finished_job()
        self.factory.record_take(two["id"], job_id=other_job["id"], status="succeeded",
                                 output_url=other_job["output_url"])

        status, _, body = self.remove("jobs", job["id"])
        self.assertEqual(status, 200, body)

        deleted = self.factory.takes(one["id"], owner)[0]
        self.assertIsNotNone(deleted["deletedAt"])
        self.assertEqual(deleted["verdict"], "accepted", "history is kept; only the output went")
        after = self.factory.get_project(plan["id"], owner)
        self.assertEqual(after["shots"][0]["status"], "succeeded")
        self.assertIsNone(after["shots"][0]["acceptedTakeId"])
        self.assertIsNone(self.factory.takes(two["id"], owner)[0]["deletedAt"])
        self.assertEqual(after["shots"][1]["outputUrl"], other_job["output_url"])
