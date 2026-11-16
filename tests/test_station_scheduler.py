"""D4: the station rules, pure. Twelve keyframes and twelve LTX shots switch exactly once."""
import unittest

import station_scheduler as ss


class StationTests(unittest.TestCase):
    def test_models_map_to_stations(self):
        self.assertEqual(ss.station_of("ltx23-distilled"), "ltx")
        self.assertEqual(ss.station_of("qwen-image-edit-2509"), "imagegen")
        self.assertEqual(ss.station_of("z-image-turbo"), "imagegen")
        self.assertEqual(ss.station_of("post-vx"), "none")

    def test_the_registry_wins_when_present(self):
        class Adapter:
            gpu_tenant = "none"
            media_type = "video"
        self.assertEqual(ss.station_of("whatever", {"whatever": Adapter()}), "none")

    def test_twelve_keyframes_and_twelve_shots_switch_exactly_once(self):
        models = ["qwen-image-edit-2509"] * 12 + ["ltx23-distilled"] * 12
        # Interleaved in the plan; grouped by the scheduler.
        interleaved = [m for pair in zip(models[:12], models[12:]) for m in pair]
        stations = [ss.station_of(m) for m in interleaved]
        self.assertEqual(ss.switch_count(stations), 23, "run in plan order this would switch 23 times")
        ordered = ss.group_by_station(stations)
        self.assertEqual(ss.switch_count(ordered), 1)
        self.assertEqual(ss.estimate(interleaved)["switches"], 1)

    def test_the_holder_goes_first_so_a_switch_is_paid_once(self):
        stations = ["imagegen"] * 3 + ["ltx"] * 9
        self.assertEqual(ss.group_by_station(stations, holder="imagegen")[:3], ["imagegen"] * 3)
        self.assertEqual(ss.switch_count(ss.group_by_station(stations, holder="imagegen"), "imagegen"), 1)
        # Without a holder the larger group goes first and the switch still happens once.
        self.assertEqual(ss.group_by_station(stations)[:9], ["ltx"] * 9)

    def test_choose_next_prefers_the_holder_then_the_larger_queue(self):
        candidates = [{"project_id": "a", "shot": 1, "station": "ltx"},
                      {"project_id": "b", "shot": 2, "station": "imagegen"}]
        self.assertEqual(ss.choose_next(candidates, "imagegen", {"ltx": 5, "imagegen": 1})["project_id"], "b")
        self.assertEqual(ss.choose_next(candidates, None, {"ltx": 5, "imagegen": 1})["project_id"], "a")
        self.assertEqual(ss.choose_next(candidates, None, {"ltx": 1, "imagegen": 5})["project_id"], "b")
        self.assertIsNone(ss.choose_next([], None, {}))

    def test_post_jobs_do_not_wait_for_a_switch_they_do_not_need(self):
        only_post = [{"project_id": "a", "shot": 1, "station": "none"}]
        self.assertEqual(ss.choose_next(only_post, "imagegen", {"none": 1})["station"], "none")
        mixed = [{"project_id": "a", "shot": 1, "station": "none"}, {"project_id": "b", "shot": 2, "station": "ltx"}]
        self.assertEqual(ss.choose_next(mixed, "ltx", {"ltx": 1, "none": 1})["station"], "ltx")

    def test_the_estimate_says_which_numbers_were_measured(self):
        result = ss.estimate(["ltx23-distilled", "z-image-turbo"], averages={"ltx23-distilled": 120.0})
        self.assertEqual(result["measured_models"], ["ltx23-distilled"])
        self.assertEqual(result["assumed_models"], ["z-image-turbo"])
        self.assertEqual(result["generate_seconds"], 120.0 + 12.9)
        self.assertEqual(result["switches"], 1)
        self.assertEqual(result["switch_seconds"], 336.0 if ss.group_by_station(["ltx", "imagegen"])[0] == "ltx" else 0.0)

    def test_switch_cost_is_the_destination_load_and_ltx_costs_nothing_extra(self):
        # Two image shots then twelve LTX: one switch, into LTX, which loads per job anyway.
        result = ss.estimate(["z-image-turbo"] * 2 + ["ltx23-distilled"] * 12, holder="imagegen")
        self.assertEqual(result["switches"], 1)
        self.assertEqual(result["switch_seconds"], 0.0)
        # Twelve LTX then two image: one switch into the image model, which costs its load.
        result = ss.estimate(["ltx23-distilled"] * 12 + ["z-image-turbo"] * 2, holder="ltx")
        self.assertEqual(result["switch_seconds"], 336.0)

    def test_over_budget_is_a_warning_with_numbers(self):
        result = ss.estimate(["ltx23-distilled"] * 4, averages={"ltx23-distilled": 100.0}, openai_tokens=5000)
        self.assertEqual(ss.budget_warnings(result, {"gpu_seconds": 300}), [{"kind": "gpu_seconds", "limit": 300, "estimate": 400.0}])
        self.assertEqual(ss.budget_warnings(result, {"openai_tokens": 4000})[0]["kind"], "openai_tokens")
        self.assertEqual(ss.budget_warnings(result, {}), [])
        self.assertEqual(ss.budget_warnings(result, {"gpu_seconds": 0}), [], "zero means no budget set")


if __name__ == "__main__":
    unittest.main()
