import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import test_backend
import local_backend as backend
from production_store import ProductionStore
import user_auth as auth


class AccountTests(test_backend.BackendTests):
    def setUp(self):
        super().setUp()
        self.auth = auth.AuthStore(Path(self.temp.name) / "accounts.sqlite3")
        self.store = ProductionStore(Path(self.temp.name) / "jobs.sqlite3")
        self.mail = []
        settings = auth.AuthSettings("http://localhost:3000", smtp_host="smtp.example.test", smtp_from="sender@example.test", registration_enabled=True)
        self.account_patches = [patch.object(backend, "USER_AUTH_ENABLED", True), patch.object(backend, "AUTH", self.auth),
                                patch.object(backend, "AUTH_SETTINGS", settings), patch.object(backend, "STORE", self.store),
                                patch.object(auth, "PASSWORD_N", 1024), patch.object(auth.AuthSettings, "send", side_effect=lambda email, token, kind: self.mail.append((email, token, kind))),
                                patch.object(backend, "generation_provenance", return_value={}), patch.object(backend, "run_job")]
        for item in self.account_patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.account_patches):
            item.stop()
        super().tearDown()

    def call(self, method, path, payload=None, cookie="", csrf="", **headers):
        return self.request(method, path, json.dumps(payload) if payload is not None else None,
                            {"Content-Type": "application/json", "Origin": "http://localhost:3000", "Cookie": cookie,
                             "X-CSRF-Token": csrf, **headers})

    def register(self, username="alice"):
        raw = dict(name="Test Person", username=username, email=f"{username}@example.test", password="a long test passphrase 2026")
        result = self.call("POST", "/api/auth/register", raw)
        self.assertEqual(result[0], 202, result)
        return raw

    def account(self, username="alice"):
        raw = self.register(username)
        token = self.mail[-1][1]
        self.assertEqual(self.call("POST", "/api/auth/verify", {"token": token})[0], 200)
        result = self.call("POST", "/api/auth/login", {"username": username, "password": raw["password"]})
        self.assertEqual(result[0], 200, result)
        return result[1]["Set-Cookie"].split(";", 1)[0], json.loads(result[2])["csrf_token"]

    # Inherited legacy tests are intentionally run with the explicit service key
    # only in the base/worker suites; account tests use the stricter boundary.
    def test_cuda_failure_and_payload_validation(self):
        self.assertEqual(self.call("POST", "/api/jobs", {"prompt": "test"})[0], 401)

    def test_generated_range_head_and_traversal(self):
        self.assertEqual(self.call("GET", "/generated/test.mp4")[0], 401)
        self.assertEqual(self.call("HEAD", "/generated/test.mp4")[0], 401)

    def test_progress_is_stage_based_and_partial_output_hidden(self):
        self.assertEqual(self.call("GET", "/api/outputs")[0], 401)

    def test_reject_uploads_and_untrusted_origin(self):
        self.assertEqual(self.call("POST", "/api/auth/login", {}, Origin="https://evil.invalid")[0], 403)

    def test_upload_list_preview_download_and_i2v(self):
        self.assertEqual(self.call("GET", "/api/assets")[0], 401)

    def test_verification_is_single_use_and_never_creates_a_session(self):
        raw = self.register()
        response = self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})
        self.assertEqual(response[0], 403)
        self.assertNotIn("Set-Cookie", response[1])
        token = self.mail[0][1]
        result = self.call("POST", "/api/auth/verify", {"token": token})
        self.assertEqual(result[0], 200)
        self.assertTrue(json.loads(result[2])["requires_login"])
        self.assertIn("Max-Age=0", result[1]["Set-Cookie"])
        self.assertFalse(json.loads(self.call("GET", "/api/auth/session")[2])["authenticated"])
        self.assertEqual(self.call("POST", "/api/auth/verify", {"token": token})[0], 400)
        with self.auth.connect() as db:
            row = db.execute("SELECT password_hash,verified_at FROM users").fetchone()
        self.assertNotEqual(row[0], raw["password"])
        self.assertNotIn(raw["password"], row[0])
        self.assertIsNotNone(row[1])

    def test_cookie_csrf_logout_and_session_expiry(self):
        cookie, csrf = self.account()
        session = json.loads(self.call("GET", "/api/auth/session", cookie=cookie)[2])
        self.assertEqual(session["user"]["username"], "alice")
        self.assertNotIn(cookie.split("=", 1)[1], json.dumps(session))
        self.assertEqual(self.call("POST", "/api/jobs", {"prompt": "test"}, cookie=cookie)[0], 403)
        self.assertEqual(self.call("POST", "/api/auth/logout", cookie=cookie, csrf="wrong")[0], 403)
        with patch.object(auth.time, "time", return_value=time.time() + auth.SESSION_SECONDS + 1):
            self.assertFalse(json.loads(self.call("GET", "/api/auth/session", cookie=cookie)[2])["authenticated"])
        self.assertEqual(self.call("POST", "/api/auth/logout", cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.call("GET", "/api/v1/capabilities", cookie=cookie)[0], 401)

    def test_user_isolation_and_idempotency_scope(self):
        alice, acsrf = self.account("alice")
        bob, bcsrf = self.account("bob")
        raw = {"prompt": "generic client", "audio": False}
        a = json.loads(self.call("POST", "/api/v1/jobs", raw, cookie=alice, csrf=acsrf, **{"Idempotency-Key": "same-key-001"})[2])
        self.assertIn("id", a, a)
        self.assertEqual(self.call("GET", a["status_url"], cookie=bob)[0], 404)
        self.assertEqual(self.call("GET", a["status_url"] + "/video", cookie=bob)[0], 404)
        self.assertEqual(self.call("POST", a["status_url"] + "/cancel", cookie=bob, csrf=bcsrf)[0], 404)
        self.assertEqual(self.call("GET", f"/api/jobs/{a['id']}", cookie=bob)[0], 404)
        health = json.loads(self.call("GET", "/api/health", cookie=bob)[2])
        self.assertTrue(health["busy"])
        self.assertIsNone(health["active_job"])
        saved = backend.JOBS[a["id"]]
        saved.update(status="succeeded", size_bytes=10)
        (self.output / saved["filename"]).write_bytes(b"0123456789")
        self.store.record(saved)
        self.assertEqual(self.call("GET", saved["output_url"], cookie=bob)[0], 404)
        self.assertEqual(self.call("GET", saved["output_url"], cookie=alice, Range="bytes=0-2")[2], b"012")
        b = json.loads(self.call("POST", "/api/v1/jobs", raw, cookie=bob, csrf=bcsrf, **{"Idempotency-Key": "same-key-001"})[2])
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(json.loads(self.call("GET", "/api/v1/jobs", cookie=bob)[2])["total"], 1)
        self.assertEqual(json.loads(self.call("GET", "/api/outputs", cookie=bob)[2])["outputs"], [])

    def test_reference_ownership_enforced_for_download_and_generation(self):
        import base64
        alice, acsrf = self.account("alice")
        bob, bcsrf = self.account("bob")
        data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        result = self.request("POST", "/api/assets?name=test.png", data,
                              {"Content-Type": "image/png", "Origin": "http://localhost:3000", "Cookie": alice, "X-CSRF-Token": acsrf})
        self.assertEqual(result[0], 201, result)
        asset = json.loads(result[2])
        self.assertEqual(self.call("GET", asset["url"], cookie=bob)[0], 404)
        self.assertEqual(self.call("GET", f"/api/v1/assets/{asset['id']}/file", cookie=bob)[0], 404)
        self.assertEqual(json.loads(self.call("GET", "/api/assets", cookie=bob)[2])["assets"], [])
        request = {"prompt": "test", "mode": "i2v", "image_id": asset["id"]}
        self.assertEqual(self.call("POST", "/api/v1/validate", request, cookie=bob, csrf=bcsrf)[0], 400)
        self.assertEqual(self.call("POST", "/api/v1/validate", request, cookie=alice, csrf=acsrf)[0], 200)

    def test_reset_revokes_sessions_but_does_not_sign_in(self):
        cookie, csrf = self.account()
        self.assertEqual(self.call("POST", "/api/auth/forgot", {"email": "alice@example.test"})[0], 202)
        token = self.mail[-1][1]
        result = self.call("POST", "/api/auth/reset", {"token": token, "password": "a different long passphrase"})
        self.assertEqual(result[0], 200)
        self.assertTrue(json.loads(result[2])["requires_login"])
        self.assertEqual(self.call("GET", "/api/health", cookie=cookie)[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": "alice", "password": "a long test passphrase 2026"})[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": "alice", "password": "a different long passphrase"})[0], 200)

    def test_expired_verification_and_duplicate_registration(self):
        raw = self.register()
        token = self.mail[-1][1]
        self.assertEqual(self.call("POST", "/api/auth/register", {**raw, "password": "an attacker changed password"})[0], 202)
        self.assertEqual(len(self.mail), 1)
        with patch.object(auth.time, "time", return_value=time.time() + auth.TOKEN_SECONDS + 1):
            self.assertEqual(self.call("POST", "/api/auth/verify", {"token": token})[0], 400)

    def test_disabled_email_fail_closed_and_https_cookie(self):
        settings = auth.AuthSettings("https://new-host.example.test", registration_enabled=True)
        with patch.object(backend, "AUTH_SETTINGS", settings):
            self.assertFalse(json.loads(self.call("GET", "/api/auth/config")[2])["registration_open"])
            self.assertEqual(self.call("POST", "/api/auth/register", dict(name="Test", username="alice", email="alice@example.test", password="a long test passphrase"))[0], 503)
        raw = self.register()
        self.call("POST", "/api/auth/verify", {"token": self.mail[-1][1]})
        with patch.object(backend, "AUTH_SETTINGS", settings):
            result = self.call("POST", "/api/auth/login", {"username": "alice", "password": raw["password"]}, Origin=settings.origin)
            self.assertEqual(result[0], 200)
            header = result[1]["Set-Cookie"]
            self.assertTrue(header.startswith("__Host-ltx_session="))
            for flag in ("HttpOnly", "SameSite=Lax", "Secure", "Path=/"):
                self.assertIn(flag, header)
            self.assertNotIn("Domain=", header)
            cookie = header.split(";", 1)[0]
            self.assertTrue(json.loads(self.call("GET", "/api/auth/session", cookie=cookie)[2])["authenticated"])
            self.assertFalse(json.loads(self.call("GET", "/api/auth/session", cookie=cookie.replace("__Host-", ""))[2])["authenticated"])

    def test_rate_limit_and_account_generation_quota(self):
        for _ in range(10):
            self.assertEqual(self.call("POST", "/api/auth/login", {"username": "missing", "password": "wrong"})[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": "missing", "password": "wrong"})[0], 429)
        cookie, csrf = self.account()
        with patch.dict(os.environ, {"LTX_USER_DAILY_JOB_LIMIT": "1"}):
            job = json.loads(self.call("POST", "/api/jobs", {"prompt": "test"}, cookie=cookie, csrf=csrf)[2])
            backend.JOBS[job["id"]]["status"] = "failed"
            self.store.record(backend.JOBS[job["id"]])
            self.assertEqual(self.call("POST", "/api/jobs", {"prompt": "test"}, cookie=cookie, csrf=csrf)[0], 429)

    def internal_settings(self, **overrides):
        return auth.AuthSettings("http://localhost:3000", registration_enabled=True, auth_mode="internal", **overrides)

    def test_eight_character_password_registration_in_both_modes(self):
        for mode in ("internal", "verified_email"):
            with self.subTest(mode=mode), patch.object(backend, "AUTH_SETTINGS", auth.AuthSettings(
                    "http://localhost:3000", smtp_host="smtp.example.test", smtp_from="sender@example.test",
                    registration_enabled=True, auth_mode=mode)):
                config = json.loads(self.call("GET", "/api/auth/config")[2])
                self.assertEqual(config["password_min_length"], 8)
                username = "eight-" + mode.replace("_", "-")
                raw = dict(name="Password Test", username=username, email=f"{username}@example.test", password="Abcd123")
                rejected = self.call("POST", "/api/auth/register", raw)
                self.assertEqual(rejected[0], 400, rejected)
                self.assertEqual(json.loads(rejected[2])["code"], "invalid_password")
                raw["password"] = "Abcd1234"
                accepted = self.call("POST", "/api/auth/register", raw)
                self.assertEqual(accepted[0], 201 if mode == "internal" else 202, accepted)
                credentials = {"username": username, "password": raw["password"]}
                if mode == "verified_email":
                    self.assertEqual(self.call("POST", "/api/auth/login", credentials)[0], 403)
                    self.assertEqual(self.call("POST", "/api/auth/verify", {"token": self.mail[-1][1]})[0], 200)
                self.assertEqual(self.call("POST", "/api/auth/login", credentials)[0], 200)

    def test_password_reset_accepts_eight_characters_but_rejects_seven(self):
        cookie, _ = self.account()
        self.assertEqual(self.call("POST", "/api/auth/forgot", {"email": "alice@example.test"})[0], 202)
        token = self.mail[-1][1]
        rejected = self.call("POST", "/api/auth/reset", {"token": token, "password": "Abcd123"})
        self.assertEqual(rejected[0], 400, rejected)
        self.assertEqual(json.loads(rejected[2])["code"], "invalid_password")
        self.assertEqual(self.call("POST", "/api/auth/reset", {"token": token, "password": "Abcd1234"})[0], 200)
        self.assertEqual(self.call("GET", "/api/health", cookie=cookie)[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": "alice", "password": "Abcd1234"})[0], 200)

    def internal_account(self, username="internal-alice"):
        raw = dict(name="Internal Tester", username=username, email=f"{username}@example.test", password="a long internal test passphrase")
        response = self.call("POST", "/api/auth/register", raw)
        self.assertEqual(response[0], 201, response)
        result = self.call("POST", "/api/auth/login", {"username": username, "password": raw["password"]})
        self.assertEqual(result[0], 200, result)
        self.assertFalse(json.loads(result[2])["user"]["email_verified"])
        return raw, result[1]["Set-Cookie"].split(";", 1)[0], json.loads(result[2])["csrf_token"]

    def test_internal_registration_no_mail_no_fake_verification_no_auto_login(self):
        with patch.object(backend, "AUTH_SETTINGS", self.internal_settings()):
            config = json.loads(self.call("GET", "/api/auth/config")[2])
            self.assertTrue(config["registration_open"])
            self.assertEqual(config["auth_mode"], "internal")
            self.assertFalse(config["verification_required"])
            self.assertFalse(config["email_ready"])
            self.assertFalse(config["password_reset_available"])
            raw = dict(name="Tester", username="internal-one", email="test@example.test", password="a long internal test passphrase", email_verified=True)
            result = self.call("POST", "/api/auth/register", raw)
            self.assertEqual(result[0], 201)
            self.assertNotIn("Set-Cookie", result[1])
            self.assertTrue(json.loads(result[2])["requires_login"])
            self.assertFalse(json.loads(result[2])["verification_required"])
            self.assertEqual(self.mail, [])
            with self.auth.connect() as db:
                self.assertIsNone(db.execute("SELECT verified_at FROM users").fetchone()[0])
                self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM email_tokens").fetchone()[0], 0)
            self.assertEqual(self.call("GET", "/api/v1/models")[0], 401)
            self.assertEqual(self.call("POST", "/api/auth/register", {**raw, "username": "other", "email": "invalid"})[0], 400)

    def test_internal_existing_pending_account_and_restore_verified_policy(self):
        raw = self.register()
        with patch.object(backend, "AUTH_SETTINGS", self.internal_settings()):
            login = self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})
            self.assertEqual(login[0], 200)
            cookie = login[1]["Set-Cookie"].split(";", 1)[0]
            self.assertFalse(json.loads(login[2])["user"]["email_verified"])
            self.assertEqual(self.call("GET", "/api/v1/models", cookie=cookie)[0], 200)
        self.assertFalse(json.loads(self.call("GET", "/api/auth/session", cookie=cookie)[2])["authenticated"])
        self.assertEqual(self.call("GET", "/api/v1/models", cookie=cookie)[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})[0], 403)
        self.assertEqual(self.call("POST", "/api/auth/verify", {"token": self.mail[0][1]})[0], 200)
        self.assertEqual(self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})[0], 200)

    def test_internal_email_routes_disabled_even_if_smtp_configured(self):
        with patch.object(backend, "AUTH_SETTINGS", self.internal_settings(smtp_host="smtp.example.test", smtp_from="test@example.test")):
            self.assertFalse(json.loads(self.call("GET", "/api/auth/config")[2])["password_reset_available"])
            for action in ("verify", "resend", "forgot", "reset"):
                response = self.call("POST", "/api/auth/" + action, {"email": "alice@example.test", "token": "x" * 43, "password": "a long test passphrase"})
                self.assertEqual(response[0], 503, action)
                self.assertEqual(json.loads(response[2])["code"], "email_disabled_in_internal_mode")
            self.assertEqual(self.mail, [])

    def test_internal_rejects_wrong_disabled_duplicate_and_unregistered_accounts(self):
        with patch.object(backend, "AUTH_SETTINGS", self.internal_settings()):
            raw, cookie, _ = self.internal_account()
            self.assertEqual(self.call("POST", "/api/auth/register", {**raw, "password": "an overwritten password attempt"})[0], 409)
            self.assertEqual(self.call("POST", "/api/auth/login", {"username": raw["username"], "password": "wrong"})[0], 401)
            self.assertEqual(self.call("POST", "/api/auth/login", {"username": "unknown", "password": raw["password"]})[0], 401)
            self.assertEqual(self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})[0], 200)
            with self.auth.connect() as db:
                db.execute("UPDATE users SET disabled=1 WHERE username=?", (raw["username"],))
            self.assertEqual(self.call("GET", "/api/v1/models", cookie=cookie)[0], 401)
            self.assertEqual(self.call("POST", "/api/auth/login", {"username": raw["username"], "password": raw["password"]})[0], 401)

    def test_internal_csrf_ownership_expiry_and_logout_still_enforced(self):
        with patch.object(backend, "AUTH_SETTINGS", self.internal_settings()):
            _, alice, acsrf = self.internal_account()
            _, bob, bcsrf = self.internal_account("internal-bob")
            self.assertEqual(self.call("POST", "/api/v1/jobs", {"prompt": "test"}, cookie=alice)[0], 403)
            self.assertEqual(self.call("POST", "/api/auth/login", {}, Origin="http://evil.invalid")[0], 403)
            result = self.call("POST", "/api/v1/jobs", {"prompt": "test", "audio": False}, cookie=alice, csrf=acsrf, **{"Idempotency-Key": "internal-test-001"})
            self.assertEqual(result[0], 202, result)
            job = json.loads(result[2])
            self.assertEqual(self.call("GET", job["status_url"], cookie=bob)[0], 404)
            self.assertEqual(self.call("POST", job["status_url"] + "/cancel", cookie=bob, csrf=bcsrf)[0], 404)
            saved = backend.JOBS[job["id"]]
            saved.update(status="succeeded", size_bytes=10)
            (self.output / saved["filename"]).write_bytes(b"0123456789")
            self.store.record(saved)
            self.assertEqual(self.call("GET", saved["output_url"], cookie=bob)[0], 404)
            self.assertEqual(self.call("GET", saved["output_url"], cookie=alice, Range="bytes=0-2")[2], b"012")
            self.assertEqual(self.call("POST", "/api/auth/logout", cookie=alice, csrf="wrong")[0], 403)
            with patch.object(auth.time, "time", return_value=time.time() + auth.SESSION_SECONDS + 1):
                self.assertFalse(json.loads(self.call("GET", "/api/auth/session", cookie=alice)[2])["authenticated"])
            self.assertEqual(self.call("POST", "/api/auth/logout", cookie=alice, csrf=acsrf)[0], 200)
            self.assertEqual(self.call("GET", "/api/v1/models", cookie=alice)[0], 401)

    def test_internal_registration_can_still_be_closed(self):
        with patch.object(backend, "AUTH_SETTINGS", auth.AuthSettings("http://localhost:3000", auth_mode="internal")):
            self.assertFalse(json.loads(self.call("GET", "/api/auth/config")[2])["registration_open"])
            self.assertEqual(self.call("POST", "/api/auth/register", {})[0], 503)


class CryptoAndMailTests(unittest.TestCase):
    def test_password_length_boundaries_and_existing_character_support(self):
        for password in ("Abcd1234", "x" * 128, "a long passphrase with symbols !@#"):
            with self.subTest(length=len(password)):
                self.assertEqual(auth.check_password(password), password)
        for password in (None, 12345678, "", "Abcd123", "x" * 129, "Abcd1234\x00"):
            with self.subTest(value_type=type(password).__name__):
                with self.assertRaises(auth.AuthError) as caught:
                    auth.check_password(password)
                self.assertEqual(caught.exception.code, "invalid_password")

    def test_auth_mode_defaults_secure_and_rejects_typo(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(auth.AuthSettings.from_env().verification_required)
        with patch.dict(os.environ, {"LTX_AUTH_MODE": "internal", "LTX_PUBLIC_ORIGIN": "http://localhost:3000", "LTX_REGISTRATION_ENABLED": "1", "LTX_SMTP_PASSWORD_FILE": "/nonexistent/unused-secret"}, clear=True):
            settings = auth.AuthSettings.from_env()
            self.assertTrue(settings.registration_open)
            self.assertFalse(settings.verification_required)
            with self.assertRaises(auth.AuthError):
                settings.send("test@example.test", "x" * 43, "verify")
        with patch.dict(os.environ, {"LTX_AUTH_MODE": "internla"}, clear=True):
            with self.assertRaises(ValueError):
                auth.AuthSettings.from_env()

    def test_production_scrypt_parameters_and_salted_hash(self):
        self.assertEqual(auth.PASSWORD_N, 2**17)
        encoded = auth.password_hash("a long production test passphrase")
        self.assertTrue(auth.password_matches("a long production test passphrase", encoded))
        self.assertFalse(auth.password_matches("wrong", encoded))

    def test_smtp_requires_tls_and_keeps_token_in_fragment(self):
        settings = auth.AuthSettings("https://new.example.test", smtp_host="smtp.example.test", smtp_from="sender@example.test", smtp_user="user", smtp_password="test-secret")
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.send_message.return_value = {}
        with patch.object(auth.smtplib, "SMTP", return_value=smtp):
            settings.send("recipient@example.test", "x" * 43, "verify")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user", "test-secret")
        message = smtp.send_message.call_args.args[0]
        self.assertIn("https://new.example.test/auth/verify#token=", message.get_content())
        self.assertNotIn("?token=", message.get_content())

    def test_migration_is_dry_run_by_default_and_does_not_overwrite(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("secure_media", Path(__file__).resolve().parents[1] / "scripts/secure-media.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "public/generated"
            source.mkdir(parents=True)
            path = source / "one.mp4"
            path.write_bytes(b"original")
            module.migrate(root)
            self.assertTrue(path.exists())
            result = module.migrate(root, True)
            self.assertEqual(result["deleted"], 0)
            self.assertEqual((root / "data/worker/legacy-outputs/one.mp4").read_bytes(), b"original")
            path.write_bytes(b"new file")
            with self.assertRaises(ValueError):
                module.migrate(root, True)
            self.assertEqual(path.read_bytes(), b"new file")
