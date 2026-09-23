import unittest
from unittest.mock import patch

import character_consistency as identity
import local_backend as backend


ASSETS = {
    "a" * 32: {"kind": "image", "width": 768, "height": 512},
    "b" * 32: {"kind": "image", "width": 768, "height": 512},
    "c" * 32: {"kind": "audio", "width": 0, "height": 0},
}


class CharacterConsistencyTests(unittest.TestCase):
    def test_normalize_prompt_and_angle_selection(self):
        raw = {"name": "Mina", "description": "Oval face, short black bob, amber eyes, navy coat.",
               "references": [{"image_id": "a" * 32, "view": "front"},
                              {"image_id": "b" * 32, "view": "left_profile"}]}
        character = identity.normalize_character(raw, "a" * 32, ASSETS.__getitem__)
        self.assertEqual(identity.select_reference(character, {"angle": "profile"}, "a" * 32), "b" * 32)
        self.assertEqual(identity.select_reference(character, {"angle": "left_profile"}, "a" * 32), "b" * 32)
        self.assertEqual(identity.select_reference(character, {"angle": "front"}, "a" * 32), "a" * 32)
        locked = identity.apply_identity_prompt("Walks forward.", character)
        self.assertIn("exact same person", locked)
        self.assertIn("same visual medium and art style", locked)
        self.assertEqual(identity.segment_seed(42, 3, character), 42)
        self.assertEqual(identity.segment_seed(42, 3, None), 45)

    def test_legacy_camera_prose_recovers_a_structured_reference_angle(self):
        self.assertEqual(identity.infer_angle("Camera holds a left three-quarter view."),
                         "left_three_quarter")
        self.assertEqual(identity.infer_angle("Low-angle portrait from the floor."), "low")
        self.assertIsNone(identity.infer_angle("Slow push-in on her hands."))

    def test_rejects_ambiguous_or_non_image_sets(self):
        base = {"name": "Mina", "description": "Stable identity", "references": []}
        invalid = [
            base,
            {**base, "references": [{"image_id": "c" * 32, "view": "front"}]},
            {**base, "references": [{"image_id": "a" * 32, "view": "front"}, {"image_id": "b" * 32, "view": "front"}]},
        ]
        for raw in invalid:
            with self.assertRaises(ValueError):
                identity.normalize_character(raw, "a" * 32, ASSETS.__getitem__)

    def test_backend_contract_resolves_character(self):
        raw = {"prompt": "A restrained portrait.", "mode": "i2v", "image_id": "a" * 32,
               "reference_background": "alpha_neutral", "image_strength": 0.7,
               "character": {"name": "Mina", "description": "Oval face and short black bob.",
                             "references": [{"image_id": "a" * 32, "view": "front"}]}}
        with patch.object(backend, "asset_by_id", side_effect=ASSETS.__getitem__):
            payload = backend.parse_payload(raw)
        self.assertEqual(payload["character"]["name"], "Mina")
        self.assertEqual(payload["reference_background"], "alpha_neutral")
        self.assertIn("Character identity lock", payload["prompt"])
        with patch.object(backend, "asset_by_id", side_effect=ASSETS.__getitem__), self.assertRaises(ValueError):
            backend.parse_payload({**raw, "reference_background": "automatic_magic"})

    def test_explicit_visual_style_is_validated_and_added_to_the_effective_prompt(self):
        raw = {"prompt": "A restrained portrait.", "mode": "i2v", "image_id": "a" * 32,
               "visual_style": "2D hand-drawn anime, clean ink lines and flat cel shading.",
               "character": {"name": "Mina", "description": "Oval face and short black bob.",
                             "references": [{"image_id": "a" * 32, "view": "front"}]}}
        with patch.object(backend, "asset_by_id", side_effect=ASSETS.__getitem__):
            payload = backend.parse_payload(raw)
        self.assertEqual(payload["visual_style"], raw["visual_style"])
        self.assertIn(raw["visual_style"], payload["prompt"])
        with patch.object(backend, "asset_by_id", side_effect=ASSETS.__getitem__), self.assertRaises(ValueError):
            backend.parse_payload({**raw, "visual_style": "x" * 1201})

        legacy = {**raw, "prompt": "A right profile view as Mina turns."}
        with patch.object(backend, "asset_by_id", side_effect=ASSETS.__getitem__):
            payload = backend.parse_payload(legacy)
        self.assertEqual(payload["directing"]["angle"], "right_profile")
        backend.worker.validate_request(legacy, "visual-style-contract")


if __name__ == "__main__":
    unittest.main()
