"""HTTP account boundary shared by UI routes and the generic worker API."""
from http.cookies import SimpleCookie
import hmac
import json
import psycopg

from user_auth import AUTH_SLOTS, AuthError, PASSWORD_MIN_LENGTH, SESSION_SECONDS, csrf_token, normalize_email
from cloudflare_access import local_request, sync_enrollment


class AuthHandlerMixin:
    def access_identity(self):
        if not self.access_settings.enabled or local_request(self):
            return None
        return self.access_verifier.verify(self.headers.get("Cf-Access-Jwt-Assertion", ""))

    def access_boundary(self):
        try:
            return True, self.access_identity()
        except AuthError as exc:
            self.send_json(exc.status, {"error": exc.code, "code": exc.code})
            return False, None

    @property
    def secure_account_cookie(self):
        if self.access_settings.enabled:
            return not local_request(self)
        return self.auth_settings.secure_cookie

    @property
    def cookie_name(self):
        # HTTPS prefix prevents sibling subdomains from planting Domain cookies.
        return "__Host-ltx_session" if self.secure_account_cookie else "ltx_session"

    def session_cookie(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie[self.cookie_name].value if self.cookie_name in cookie else ""
        except Exception:
            return ""

    def cookie_header(self, token=""):
        secure = "; Secure" if self.secure_account_cookie else ""
        return {"Set-Cookie": f"{self.cookie_name}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECONDS if token else 0}{secure}"}

    @property
    def cloudflare_logout_url(self):
        # Same-origin URL survives subdomain changes. Never send loopback users
        # to a nonexistent local Cloudflare route.
        return "/cdn-cgi/access/logout" if self.access_settings.enabled and not local_request(self) else None

    def require_principal(self, *, worker_only=False):
        accepted, access_email = self.access_boundary()
        if not accepted:
            return False
        key = self.worker_key()
        authorization = self.headers.get("Authorization", "")
        if authorization:
            if not key:
                self.send_json(503, {"error": "Worker credential is not configured", "code": "worker_not_configured"})
                return False
            if not hmac.compare_digest(authorization.encode(), f"Bearer {key}".encode()):
                self.send_json(401, {"error": "Invalid worker credential", "code": "unauthorized"})
                return False
            self.principal = {"kind": "service", "id": None}
            return True
        if not self.user_auth_enabled:
            if worker_only:
                self.send_json(401 if key else 503, {"error": "Worker credential required", "code": "unauthorized" if key else "worker_not_configured"})
                return False
            self.principal = {"kind": "service", "id": None}
            return True
        try:
            token = self.session_cookie()
            user = self.auth_store.session(token, require_verified=self.auth_settings.verification_required) if self.auth_store else None
        except (OSError, psycopg.Error):
            self.send_json(503, {"error": "Account service unavailable", "code": "auth_unavailable"})
            return False
        if not user:
            self.send_json(401, {"error": "Account login required", "code": "login_required"})
            return False
        if access_email is not None and user["email"] != access_email:
            self.send_json(403, {"error": "Cloudflare identity must match the local account", "code": "cloudflare_email_mismatch"})
            return False
        if self.command not in {"GET", "HEAD", "OPTIONS"} and not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), csrf_token(token).encode()):
            self.send_json(403, {"error": "CSRF validation failed", "code": "csrf_failed"})
            return False
        self.principal = {"kind": "user", **user}
        return True

    def can_access(self, record):
        return not record.get("deleted_at") and (self.principal["kind"] == "service" or record.get("owner_id") == self.principal["id"])

    def auth_get(self, path):
        accepted, access_email = self.access_boundary()
        if not accepted:
            return
        if path == "/api/auth/config":
            settings = self.auth_settings
            self.send_json(200, {"registration_open": self.user_auth_enabled and settings.registration_open,
                                 "email_ready": settings.email_ready, "public_origin": settings.origin,
                                 "auth_mode": settings.auth_mode, "verification_required": settings.verification_required,
                                 "password_reset_available": settings.verification_required and settings.email_ready,
                                 "cloudflare_sync_enabled": self.access_settings.enabled,
                                 "cloudflare_verification_url": self.access_settings.login_url,
                                 "password_min_length": PASSWORD_MIN_LENGTH, "verification_requires_login": True})
        elif path == "/api/auth/session":
            try:
                token = self.session_cookie()
                user = self.auth_store.session(token, require_verified=self.auth_settings.verification_required) if self.auth_store else None
                if user and access_email is not None and user["email"] != access_email:
                    self.send_json(403, {"error": "Cloudflare identity must match the local account", "code": "cloudflare_email_mismatch"})
                    return
                self.send_json(200, {"required": self.user_auth_enabled, "authenticated": bool(user), "user": user,
                                     "auth_mode": self.auth_settings.auth_mode,
                                     "cloudflare_logout_url": self.cloudflare_logout_url,
                                     "csrf_token": csrf_token(token) if user else None})
            except (OSError, psycopg.Error):
                self.send_json(503, {"error": "Account service unavailable", "code": "auth_unavailable"})
        else:
            self.send_json(404, {"error": "Not found"})

    def auth_post(self, path):
        accepted, access_email = self.access_boundary()
        if not accepted:
            return
        routes = {"register", "login", "logout", "verify", "resend", "forgot", "reset"}
        action = path.removeprefix("/api/auth/")
        if action not in routes:
            self.send_json(404, {"error": "Not found"})
            return
        origin = self.headers.get("Origin", "").rstrip("/")
        if not origin or origin not in self.auth_origins:
            self.send_json(403, {"error": "Trusted same-origin browser request required", "code": "origin_not_allowed"})
            return
        if self.auth_store is None or not self.auth_settings.origin:
            self.send_json(503, {"error": "Account service is not configured", "code": "auth_unavailable"})
            return
        if not AUTH_SLOTS.acquire(blocking=False):
            self.send_json(429, {"error": "Try again later", "code": "rate_limited"})
            return
        try:
            self.auth_store.rate("auth:global", 60, 60)
            if action == "logout":
                token = self.session_cookie()
                # Expired/already-revoked sessions must still be able to clear
                # their cookie. Logging OUT must not require an email match to
                # a newly switched Cloudflare identity. The outer JWT, Origin,
                # and CSRF for every live local session remain enforced.
                user = self.auth_store.session(token, require_verified=False)
                if user and not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), csrf_token(token).encode()):
                    self.send_json(403, {"error": "CSRF validation failed", "code": "csrf_failed"})
                    return
                self.auth_store.logout(token)
                self.send_json(200, {"ok": True, "cloudflare_logout_url": self.cloudflare_logout_url}, extra_headers=self.cookie_header())
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise AuthError("json_required", 415)
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 6000:
                raise AuthError("invalid_request")
            self.connection.settimeout(10)
            raw = json.loads(self.rfile.read(length))
            if not isinstance(raw, dict):
                raise AuthError("invalid_request")
            if action in {"verify", "resend", "forgot", "reset"} and not self.auth_settings.verification_required:
                raise AuthError("email_disabled_in_internal_mode", 503)
            if action == "register":
                if not self.auth_settings.registration_enabled:
                    raise AuthError("registration_closed", 503)
                if self.auth_settings.verification_required and not self.auth_settings.email_ready:
                    raise AuthError("email_not_configured", 503)
                self.auth_store.rate("register:global", 20, 3600)
                self.auth_store.rate("mail:" + normalize_email(raw.get("email")), 3, 3600)
                if access_email is not None and normalize_email(raw.get("email")) != access_email:
                    raise AuthError("cloudflare_email_mismatch", 403)
                target = self.auth_store.register(raw, access_target=self.access_settings.target if self.access_settings.enabled else "")
                cf_result = {}
                if target and self.access_settings.enabled:
                    cf_result = {"cloudflare_sync_status": sync_enrollment(self.auth_store, self.access_client, target[0]),
                                 "cloudflare_verification_url": self.access_settings.login_url}
                if not self.auth_settings.verification_required:
                    if not target:
                        raise AuthError("account_unavailable", 409)
                    # No email/token/session and no fictitious verified_at value.
                    self.send_json(201, {"ok": True, "verification_required": False, "requires_login": True, **cf_result,
                                         "message": "Account created for internal testing. Sign in with your username and password."})
                    return
                if target:
                    token = self.auth_store.issue_email_token(target[0], "verify")
                    self.auth_settings.send(target[1], token, "verify")
                self.send_json(202, {"ok": True, "verification_required": True, "requires_login": True, **cf_result,
                                     "message": "If eligible, check your inbox. Verification requires a fresh login."})
            elif action == "login":
                username = raw.get("username")
                if not isinstance(username, str):
                    raise AuthError("invalid_credentials", 401)
                self.auth_store.rate("login:" + username.strip().lower()[:254], 10, 900)
                token, user = self.auth_store.login(username, raw.get("password"), require_verified=self.auth_settings.verification_required,
                                                   access_email=access_email)
                old_token = self.session_cookie()
                if old_token:
                    self.auth_store.logout(old_token)
                self.send_json(200, {"user": user, "csrf_token": csrf_token(token)}, extra_headers=self.cookie_header(token))
            elif action in {"resend", "forgot"}:
                if not self.auth_settings.email_ready:
                    raise AuthError("email_not_configured", 503)
                email = normalize_email(raw.get("email"))
                self.auth_store.rate("mail:" + email, 3, 3600)
                self.auth_store.rate("mail:global", 40, 3600)
                kind = "verify" if action == "resend" else "reset"
                target = self.auth_store.mail_target(email, kind)
                if target:
                    token = self.auth_store.issue_email_token(target[0], kind)
                    self.auth_settings.send(target[1], token, kind)
                self.send_json(202, {"ok": True, "message": "If eligible, check your inbox."})
            else:
                self.auth_store.consume_token(raw.get("token"), "verify" if action == "verify" else "reset", raw.get("password"))
                self.send_json(200, {"ok": True, "requires_login": True}, extra_headers=self.cookie_header())
        except AuthError as exc:
            self.send_json(exc.status, {"error": exc.code, "code": exc.code})
        except (ValueError, TypeError):
            self.send_json(400, {"error": "Invalid account request", "code": "invalid_request"})
        except (OSError, psycopg.Error):
            self.send_json(503, {"error": "Account service unavailable", "code": "auth_unavailable"})
        finally:
            AUTH_SLOTS.release()
