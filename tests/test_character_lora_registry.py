import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import character_lora_registry as registry
import local_backend as backend
import worker_contract


class CharacterLoraRegistryTests(unittest.TestCase):
    def install(self, root: Path, identity="mika.identity", kind="identity"):
        weight = root / f"{identity}.safetensors"
        weight.write_bytes(b"safe-test-weight")
        digest = hashlib.sha256(weight.read_bytes()).hexdigest()
        metadata = {
            "id": identity,
            "label": "Mika Identity",
            "kind": kind,
            "model_family": "ltx-2.5",
            "weight_filename": weight.name,
            "weight_sha256": digest,
            "trigger_token": "mikaPerson",
            "default_strength": 0.8,
            "validated_strength_range": {"min": 0.5, "max": 1.1},
            "compatible_models": ["ltx25-fast"],
            "compatible_modes": ["t2v", "i2v"],
            "approval_status": "approved",
            "version": "1.0.0",
        }
        (root / f"{identity}.json").write_text(json.dumps(metadata), encoding="utf-8")
        return metadata

    def test_catalog_never_exposes_paths_or_trigger_tokens(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LTX_CHARACTER_LORA_DIR": temp}):
            self.install(Path(temp))
            item = registry.public_catalog()["loras"][0]
        self.assertEqual(item["id"], "mika.identity")
        self.assertNotIn("weight_filename", item)
        self.assertNotIn("trigger_token", item)
        self.assertNotIn("_path", item)

    def test_request_resolves_id_injects_trigger_and_environment_path(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LTX_CHARACTER_LORA_DIR": temp}):
            metadata = self.install(Path(temp))
            payload, _, _ = worker_contract.parse_request(
                {"model": "ltx25-fast", "prompt": "walks through a studio", "identity_lora": {"id": metadata["id"]}},
                backend.parse_payload,
            )
            env = backend.job_environment(payload)
        self.assertTrue(payload["prompt"].startswith("mikaPerson "))
        self.assertEqual(payload["identity_lora"]["id"], metadata["id"])
        self.assertTrue(env["LTX_IDENTITY_LORA_PATH"].endswith("mika.identity.safetensors"))
        self.assertEqual(env["LTX_IDENTITY_LORA_STRENGTH"], "0.8")

    def test_unregistered_id_and_strength_outside_validated_range_fail(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LTX_CHARACTER_LORA_DIR": temp}):
            metadata = self.install(Path(temp))
            with self.assertRaisesRegex(ValueError, "not installed"):
                backend.parse_payload({"model": "ltx25-fast", "prompt": "test", "identity_lora": {"id": "unknown.person"}})
            with self.assertRaisesRegex(ValueError, "validated range"):
                backend.parse_payload({"model": "ltx25-fast", "prompt": "test", "identity_lora": {"id": metadata["id"], "strength": 1.5}})


if __name__ == "__main__":
    unittest.main()
