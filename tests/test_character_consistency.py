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
        self.assertIn("exact same person", identity.apply_identity_prompt("Walks forward.", character))
        self.assertEqual(identity.segment_seed(42, 3, character), 42)
        self.assertEqual(identity.segment_seed(42, 3, None), 45)

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


if __name__ == "__main__":
    unittest.main()
