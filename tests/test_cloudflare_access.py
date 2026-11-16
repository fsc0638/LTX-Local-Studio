import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import cloudflare_access as access
import local_backend as backend
import user_auth as auth
import conftest
import test_backend
from production_store import ProductionStore


def settings():
    return access.AccessSettings(True, 'a' * 32, '11111111-2222-3333-4444-555555555555',
                                 'https://video.example.test', 'https://studio-test.cloudflareaccess.com', 'b' * 64,
                                 '/unused/test-token')


class EnrollmentTests(conftest.DatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.start_database()
        self.temp = tempfile.TemporaryDirectory()
        self.store = auth.AuthStore()
        self.client = Mock(settings=settings())
        self.hash_patch = patch.object(auth, 'PASSWORD_N', 1024)
        self.hash_patch.start()

    def tearDown(self):
        self.hash_patch.stop()
        self.temp.cleanup()

    def register(self, username='alice'):
        return self.store.register(dict(name='Test', username=username, email=f'{username}@example.test', password='Abcd1234'),
                                   access_target=self.client.settings.target)

    def test_first_enrollment_only_and_no_fake_email_verification(self):
        uid, email = self.register()
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'synced')
        self.client.append.assert_called_once_with(email)
        # Once synced, neither login nor a later sync restores dashboard removals.
        self.store.login('alice', 'Abcd1234', require_verified=False)
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'synced')
        self.client.append.assert_called_once()
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT verified_at FROM users').fetchone()['verified_at'])

    def test_read_failure_retries_but_uncertain_write_does_not(self):
        uid, _ = self.register()
        self.client.check_list.side_effect = access.AccessAPIError('cloudflare_http_403')
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'pending')
        self.client.append.assert_not_called()
        self.client.check_list.side_effect = None
        self.client.append.side_effect = access.AccessAPIError('cloudflare_unavailable')
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'review')
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'review')
        self.client.append.assert_called_once()

    def test_restart_during_write_target_change_and_disabled_user_never_append(self):
        uid, _ = self.register()
        with self.store.connect() as db:
            db.execute("UPDATE cloudflare_enrollments SET state='adding'")
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'adding')
        self.client.append.assert_not_called()
        self.client.settings = access.AccessSettings(True, 'c' * 32, settings().list_id)
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'not_enrolled')
        self.client.settings = settings()
        other, _ = self.register('bob')
        with self.store.connect() as db:
            db.execute('UPDATE users SET disabled=1 WHERE id=%s', (other,))
        self.assertEqual(access.sync_enrollment(self.store, self.client, other), 'not_enrolled')
        self.client.append.assert_not_called()

    def test_enrollment_tombstone_survives_user_deletion(self):
        uid, _ = self.register()
        with self.store.connect() as db:
            db.execute('DELETE FROM users WHERE id=%s', (uid,))
        self.assertIsNone(self.register())
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) AS total FROM users').fetchone()['total'], 0)

    def test_duplicate_and_concurrent_claim_only_append_once(self):
        uid, email = self.register()
        self.assertIsNone(self.register())
        original = self.client.append
        original.side_effect = lambda _: self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'adding')
        self.assertEqual(access.sync_enrollment(self.store, self.client, uid), 'synced')
        original.assert_called_once_with(email)

    def test_client_only_appends_one_email_to_fixed_list(self):
        client = access.AccessClient(settings())
        with patch.object(client, 'request') as request:
            client.append('Alice@Example.test')
        request.assert_called_once_with('PATCH', client.path, {'append': [{'value': 'alice@example.test'}]})
        with patch.object(client, 'request', return_value={'type': 'IP', 'id': settings().list_id}):
            with self.assertRaises(access.AccessAPIError):
                client.check_list()

    def test_private_token_config_and_disabled_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(access.AccessSettings.from_env().enabled)
        with patch.dict(os.environ, {'LTX_CF_ACCESS_ENABLED': 'true'}, clear=True):
            with self.assertRaises(ValueError):
                access.AccessSettings.from_env()
        token = Path(self.temp.name) / 'token'
        token.write_text('x' * 40)
        config = access.AccessSettings(token_file=str(token))
        token.chmod(0o600)
        self.assertEqual(config.read_token(), 'x' * 40)
        token.chmod(0o644)
        with self.assertRaises(ValueError):
            config.read_token()
        symlink = Path(self.temp.name) / 'link'
        symlink.symlink_to(token)
        with self.assertRaises(OSError):
            access.AccessSettings(token_file=str(symlink)).read_token()


class JWTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def verifier(self):
        verifier = access.AccessVerifier(settings())
        verifier.keys = {'test-key': self.key.public_key()}
        verifier.refreshed_at = time.monotonic()
        return verifier

    def token(self, **changes):
        claims = dict(type='app', email='alice@example.test', sub='user-1', iss=settings().team_domain,
                      aud=[settings().audience], iat=int(time.time()), exp=int(time.time()) + 300)
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test-key'})

    def test_signature_issuer_audience_expiry_and_user_identity(self):
        self.assertEqual(self.verifier().verify(self.token()), 'alice@example.test')
        for changes in ({'iss': 'https://evil.invalid'}, {'aud': ['wrong']}, {'exp': 1}, {'type': 'org'},
                        {'sub': ''}, {'sub': 42}, {'email': ''}, {'service_token_id': 'service-id'}):
            with self.subTest(changes=changes), self.assertRaises(auth.AuthError):
                self.verifier().verify(self.token(**changes))
        with self.assertRaises(auth.AuthError):
            self.verifier().verify(self.token() + 'broken')
        with self.assertRaises(auth.AuthError):
            self.verifier().verify(jwt.encode({'email': 'alice@example.test'}, 'secret', algorithm='HS256', headers={'kid': 'test-key'}))

    def test_jwks_fixed_origin_no_header_url_and_cache(self):
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        key['kid'] = 'test-key'
        response = Mock()
        response.__enter__ = Mock(return_value=io.BytesIO(json.dumps({'keys': [key]}).encode()))
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(access, 'build_opener', return_value=opener):
            verifier = access.AccessVerifier(settings())
            self.assertEqual(verifier.verify(self.token()), 'alice@example.test')
            self.assertEqual(verifier.verify(self.token()), 'alice@example.test')
        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.args[0].full_url, settings().team_domain + '/cdn-cgi/access/certs')

    def test_local_exception_rejects_forwarded_requests(self):
        def handler(**headers):
            return SimpleNamespace(client_address=('127.0.0.1', 8000), headers={'Host': 'localhost:3000', **headers})
        self.assertTrue(access.local_request(handler()))
        for headers in ({'Host': 'video.example.test'}, {'Origin': 'https://video.example.test'},
                        {'CF-Connecting-IP': '203.0.113.1'}, {'Cf-Ray': 'ray'}, {'Cf-Access-Jwt-Assertion': 'fake'},
                        {'X-Forwarded-Host': 'video.example.test'}):
            self.assertFalse(access.local_request(handler(**headers)), headers)
        self.assertFalse(access.local_request(SimpleNamespace(client_address=('203.0.113.1', 8), headers={'Host': 'localhost'})))


class AccessHTTPTests(test_backend.BackendTests):
    def setUp(self):
        super().setUp()
        self.auth = auth.AuthStore()
        self.client = Mock(settings=settings())
        self.verifier = Mock()
        self.verifier.verify.side_effect = lambda value: 'alice@example.test' if value == 'valid' else (_ for _ in ()).throw(auth.AuthError('cloudflare_identity_invalid', 401))
        self.access_patches = [patch.object(backend, 'USER_AUTH_ENABLED', True), patch.object(backend, 'AUTH', self.auth),
                               patch.object(backend, 'AUTH_SETTINGS', auth.AuthSettings('http://localhost:3000', registration_enabled=True, auth_mode='internal')),
                               patch.object(backend, 'ACCESS_SETTINGS', settings()), patch.object(backend, 'ACCESS_CLIENT', self.client),
                               patch.object(backend, 'ACCESS_VERIFIER', self.verifier), patch.object(auth, 'PASSWORD_N', 1024),
                               patch.object(backend, 'STORE', ProductionStore())]
        for p in self.access_patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.access_patches):
            p.stop()
        super().tearDown()

    def call(self, method, path, payload=None, external=False, cookie='', token='valid'):
        headers = {'Origin': settings().origin if external else 'http://localhost:3000', 'Content-Type': 'application/json', 'Cookie': cookie}
        if external:
            headers.update({'Host': 'video.example.test', 'Cf-Access-Jwt-Assertion': token})
        return self.request(method, path, json.dumps(payload) if payload is not None else None, headers)

    def test_local_registration_sync_and_external_verified_login(self):
        raw = dict(name='Alice', username='alice', email='alice@example.test', password='Abcd1234')
        response = self.call('POST', '/api/auth/register', raw)
        self.assertEqual(response[0], 201, response)
        self.assertEqual(json.loads(response[2])['cloudflare_sync_status'], 'synced')
        self.assertNotIn('Set-Cookie', response[1])
        self.client.append.assert_called_once_with(raw['email'])
        login = self.call('POST', '/api/auth/login', raw, external=True)
        self.assertEqual(login[0], 200, login)
        self.assertTrue(json.loads(login[2])['user']['email_verified'])
        self.assertTrue(login[1]['Set-Cookie'].startswith('__Host-ltx_session='))
        self.assertIn('; Secure', login[1]['Set-Cookie'])
        cookie = login[1]['Set-Cookie'].split(';', 1)[0]
        self.assertEqual(self.call('GET', '/api/models', external=True, cookie=cookie)[0], 200)
        self.assertEqual(self.call('GET', '/api/models', external=True, cookie=cookie, token='fake')[0], 401)
        self.verifier.verify.side_effect = lambda _: 'bob@example.test'
        self.assertEqual(self.call('GET', '/api/models', external=True, cookie=cookie)[0], 403)
        self.assertEqual(self.call('GET', '/api/auth/session', external=True, cookie=cookie)[0], 403)
        self.assertEqual(self.call('POST', '/api/auth/login', raw, external=True)[0], 403)
        self.client.append.assert_called_once()

    def test_remote_registration_cannot_enroll_another_email(self):
        raw = dict(name='Bob', username='bob', email='bob@example.test', password='Abcd1234')
        self.assertEqual(self.call('POST', '/api/auth/register', raw, external=True)[0], 403)
        self.client.append.assert_not_called()

    def test_logout_after_switching_cloudflare_identity_is_safe(self):
        raw = dict(name='Alice', username='alice', email='alice@example.test', password='Abcd1234')
        self.assertEqual(self.call('POST', '/api/auth/register', raw)[0], 201)
        login = self.call('POST', '/api/auth/login', raw, external=True)
        cookie = login[1]['Set-Cookie'].split(';', 1)[0]
        csrf = json.loads(login[2])['csrf_token']
        session = json.loads(self.call('GET', '/api/auth/session', external=True, cookie=cookie)[2])
        self.assertEqual(session['cloudflare_logout_url'], '/cdn-cgi/access/logout')
        self.verifier.verify.side_effect = lambda _: 'bob@example.test'
        self.assertEqual(self.call('GET', '/api/models', external=True, cookie=cookie)[0], 403)
        headers = {'Origin': settings().origin, 'Host': 'video.example.test', 'Cf-Access-Jwt-Assertion': 'valid', 'Cookie': cookie}
        self.assertEqual(self.request('POST', '/api/auth/logout', headers=headers)[0], 403)
        result = self.request('POST', '/api/auth/logout', headers={**headers, 'X-CSRF-Token': csrf})
        self.assertEqual(result[0], 200, result)
        self.assertIn('Max-Age=0; Secure', result[1]['Set-Cookie'])
        self.assertEqual(json.loads(result[2])['cloudflare_logout_url'], '/cdn-cgi/access/logout')
        self.assertIsNone(self.auth.session(cookie.split('=', 1)[1], require_verified=False))

    # Base suite covers legacy behavior separately; these tests explicitly assert
    # that the same media/worker endpoints cannot bypass the new external gate.
    def test_cuda_failure_and_payload_validation(self):
        self.assertEqual(self.call('POST', '/api/jobs', {}, external=True, token='fake')[0], 401)

    def test_generated_range_head_and_traversal(self):
        self.assertEqual(self.call('GET', '/generated/test.mp4', external=True, token='fake')[0], 401)

    def test_progress_is_stage_based_and_partial_output_hidden(self):
        self.assertEqual(self.call('GET', '/api/outputs', external=True, token='fake')[0], 401)

    def test_reject_uploads_and_untrusted_origin(self):
        self.assertEqual(self.call('POST', '/api/assets', {}, external=True, token='fake')[0], 401)

    def test_upload_list_preview_download_and_i2v(self):
        self.assertEqual(self.call('GET', '/api/v1/models', external=True, token='fake')[0], 401)
