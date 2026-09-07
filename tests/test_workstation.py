"""D4: the scheduler groups by workstation; the page can see the GPU and the budget."""
import json
import time
import unittest
import uuid
from unittest.mock import patch

import gpu_lease
import local_backend as backend
import model_registry as registry
import test_factory_api
from production_store import ProductionStore


def shots(model, n, prefix):
    request = {"prompt": prefix} if model == "ltx23-distilled" else {"prompt": prefix, "model": model, "mode": "edit", "image_id": "a" * 32}
    return [{"title": f"{prefix}{i:02d}", "request": dict(request)} for i in range(n)]


class WorkstationTests(test_factory_api.FactoryAPITests):
    def setUp(self):
        super().setUp()
        import local_adapters.imagegen as adapters
        registry_patch = patch.dict(registry.ADAPTERS)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        registry.register(adapters.QWEN)
        registry.register(adapters.ZIMAGE)
        self.lease = gpu_lease.GpuLease("http://127.0.0.1:9", backend.ltx_job_active, evict_timeout=1, poll=0.05)
        # The rolling average reads the job store; the factory fixture does not install one (the
        # worker tests do), and the production process always has it.
        for item in (patch.object(backend, "GPU_LEASE", self.lease),
                     patch.object(backend, "STORE", ProductionStore())):
            item.start()
            self.addCleanup(item.stop)

    def started(self, title, shot_list):
        plan = self.new_project(title=title, shots=shot_list)
        return json.loads(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[2])

    def drain(self, holder=None):
        """Run the pick rule to exhaustion, finishing each picked shot; return the station sequence."""
        self.lease.holder = holder
        sequence = []
        for _ in range(100):
            picked = backend.scheduler_pick()
            if picked is None:
                break
            project, shot = picked
            model = (shot.get("request") or {}).get("model") or "ltx23-distilled"
            station = backend.station_scheduler.station_of(model, registry.ADAPTERS)
            sequence.append(station)
            # The GPU now belongs to that station until something else is picked.
            self.lease.holder = station if station in ("ltx", "imagegen") else self.lease.holder
            self.factory.set_shot_status(shot["id"], "succeeded")
        return sequence

    def test_twelve_keyframes_and_twelve_shots_in_one_plan_switch_exactly_once(self):
        self.started("mixed", [s for pair in zip(shots("qwen-image-edit-2509", 12, "k"), shots("ltx23-distilled", 12, "v")) for s in pair])
        sequence = self.drain()
        self.assertEqual(len(sequence), 24)
        self.assertEqual(backend.station_scheduler.switch_count(sequence), 1, sequence)

    def test_across_projects_the_station_on_the_gpu_is_drained_first(self):
        self.started("video", shots("ltx23-distilled", 3, "v"))
        self.started("images", shots("z-image-turbo", 5, "k"))
        sequence = self.drain(holder="imagegen")
        self.assertEqual(sequence[:5], ["imagegen"] * 5, sequence)
        self.assertEqual(backend.station_scheduler.switch_count(sequence, "imagegen"), 1)

    def test_with_nothing_on_the_gpu_the_larger_queue_goes_first(self):
        self.started("video", shots("ltx23-distilled", 2, "v"))
        self.started("images", shots("z-image-turbo", 6, "k"))
        sequence = self.drain()
        self.assertEqual(sequence[0], "imagegen", sequence)
        self.assertEqual(backend.station_scheduler.switch_count(sequence), 1)

    def test_the_workstation_view_counts_this_owners_queue_by_station(self):
        self.started("video", shots("ltx23-distilled", 2, "v"))
        self.started("images", shots("z-image-turbo", 3, "k"))
        status, _, body = self.call("GET", "/api/v1/factory/workstation")
        self.assertEqual(status, 200, body)
        view = json.loads(body)
        self.assertEqual(view["queue"], {"ltx": 2, "imagegen": 3, "none": 0})
        self.assertIsNone(view["current"])
        self.assertIsNone(view["gpu"]["station"])
        self.assertEqual(view["switch"]["imagegen_load_seconds"], 336.0)

    def test_the_budget_estimates_one_switch_and_says_what_it_assumed(self):
        plan = self.started("mixed", shots("qwen-image-edit-2509", 12, "k") + shots("ltx23-distilled", 12, "v"))
        status, _, body = self.call("GET", f"/api/v1/factory/projects/{plan['id']}/budget")
        self.assertEqual(status, 200, body)
        view = json.loads(body)
        self.assertEqual(view["estimate"]["switches"], 1)
        self.assertEqual(view["estimate"]["assumed_models"], ["ltx23-distilled", "qwen-image-edit-2509"])
        self.assertEqual(view["remaining_shots"], 24)
        self.assertEqual(view["warnings"], [])

    def test_a_measured_average_replaces_the_default_and_a_ceiling_only_warns(self):
        plan = self.new_project(title="v", bible={"budget": {"gpu_seconds": 100}}, shots=shots("ltx23-distilled", 4, "v"))
        store = ProductionStore()
        for _ in range(3):
            store.record({"id": uuid.uuid4().hex[:12], "model": "ltx23-distilled", "status": "succeeded",
                          "runtime_seconds": 90.0, "created_at": time.time()})
        view = json.loads(self.call("GET", f"/api/v1/factory/projects/{plan['id']}/budget")[2])
        self.assertEqual(view["estimate"]["measured_models"], ["ltx23-distilled"])
        self.assertEqual(view["estimate"]["generate_seconds"], 360.0)
        self.assertEqual(view["warnings"][0]["kind"], "gpu_seconds")
        self.assertEqual(view["warnings"][0]["limit"], 100)
        # Warned, not stopped: the project can still be started.
        self.assertEqual(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/run")[0], 200)

    def test_the_budget_is_owner_scoped(self):
        plan = self.new_project(title="v", shots=shots("ltx23-distilled", 1, "v"))
        self.assertIsNone(backend.budget_view(plan["id"], "someone-else"))


if __name__ == "__main__":
    unittest.main()
