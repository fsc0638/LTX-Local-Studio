"""Opt-in Cloudflare Access enrollment. Never sends OTPs or replaces an allowlist.

Only the first enrollment may append one email. An uncertain write is terminal:
an operator must inspect it, rather than risk restoring a manually revoked user.
"""
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from user_auth import AuthError, normalize_email


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AccessAPIError(Exception):
    """Sanitized failure: never include tokens, upstream bodies or user emails."""


@dataclass(frozen=True)
class AccessSettings:
    enabled: bool = False
    account_id: str = ""
    list_id: str = ""
    origin: str = ""
    team_domain: str = ""
    audience: str = ""
    token_file: str = ""

    @classmethod
    def from_env(cls):
        flag = os.environ.get("LTX_CF_ACCESS_ENABLED", "0")
        if flag not in {"0", "1"}:
            raise ValueError("LTX_CF_ACCESS_ENABLED must be 0 or 1")
        if flag == "0":
            return cls()
        result = cls(True, *(os.environ.get("LTX_CF_" + name, "").rstrip("/") for name in
                            ("ACCOUNT_ID", "EMAIL_LIST_ID", "PUBLIC_ORIGIN", "TEAM_DOMAIN", "AUDIENCE", "API_TOKEN_FILE")))
        result.validate()
        return result

    def validate(self):
        if not self.enabled:
            return
        if not re.fullmatch(r"[a-f0-9]{32}", self.account_id) or not re.fullmatch(r"[a-f0-9-]{36}", self.list_id):
            raise ValueError("Configure the exact Cloudflare account and EMAIL list IDs")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or
                parsed.fragment or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError("LTX_CF_PUBLIC_ORIGIN must be an HTTPS origin")
        if not re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.cloudflareaccess\.com", self.team_domain):
            raise ValueError("LTX_CF_TEAM_DOMAIN must be the trusted Cloudflare Access team domain")
        if not re.fullmatch(r"[a-f0-9]{64}", self.audience):
            raise ValueError("Configure the Access application's AUD tag")
        try:
            import jwt
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError:
            raise ValueError("Cloudflare Access requires PyJWT and cryptography in the API Python environment") from None
        self.read_token()

    @property
    def target(self):
        return self.account_id + "/" + self.list_id

    @property
    def login_url(self):
        return self.origin + "/auth/login" if self.enabled else ""

    def read_token(self):
        path = Path(self.token_file)
        if not path.is_absolute():
            raise ValueError("Cloudflare API token file must have an absolute path")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "r") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise ValueError("Cloudflare API token file must be owned by this user and private (0600)")
            token = handle.read(512).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
            raise ValueError("Invalid Cloudflare API token file")
        return token


class AccessClient:
    def __init__(self, settings):
        self.settings = settings
        self.path = f"/accounts/{settings.account_id}/gateway/lists/{settings.list_id}"

    def request(self, method, path, payload=None):
        try:
            token = self.settings.read_token()
            request = Request("https://api.cloudflare.com/client/v4" + path,
                              data=json.dumps(payload).encode() if payload is not None else None,
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method=method)
            with build_opener(NoRedirect()).open(request, timeout=8) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise AccessAPIError("response_too_large")
                result = json.loads(raw)
            if not isinstance(result, dict) or result.get("success") is not True:
                raise AccessAPIError("cloudflare_rejected")
            return result.get("result")
        except HTTPError as exc:
            raise AccessAPIError("cloudflare_http_" + str(exc.code)) from None
        except (OSError, URLError, ValueError):
            raise AccessAPIError("cloudflare_unavailable") from None

    def check_list(self):
        value = self.request("GET", self.path)
        if not isinstance(value, dict) or value.get("type") != "EMAIL" or value.get("id") != self.settings.list_id:
            raise AccessAPIError("wrong_email_list")

    def append(self, email):
        # PATCH append is intentionally not a read/modify/PUT of all members.
        # No other user's removal or any Access policy is overwritten here.
        self.request("PATCH", self.path, {"append": [{"value": normalize_email(email)}]})


def sync_enrollment(store, client, user_id):
    """Return a durable state. Only pending rows can ever initiate a write."""
    settings = client.settings
    with store.connect() as db:
        row = db.execute("SELECT e.* FROM cloudflare_enrollments e JOIN users u ON u.id=e.user_id "
                         "WHERE e.user_id=%s AND u.disabled=0", (user_id,)).fetchone()
    if not row or row["target"] != settings.target:
        return "not_enrolled"
    if row["state"] != "pending":
        return row["state"]
    try:
        client.check_list()
    except AccessAPIError as exc:
        with store.connect() as db:
            db.execute("UPDATE cloudflare_enrollments SET last_error=%s,updated_at=%s WHERE user_id=%s AND state='pending'",
                       (str(exc), time.time(), user_id))
        return "pending"
    # Persist intent BEFORE the remote write. Crash/timeout cannot cause a second
    # append after an administrator has revoked the first one in Cloudflare.
    with store.connect() as db:
        claimed = db.execute("UPDATE cloudflare_enrollments SET state='adding',updated_at=%s "
                             "WHERE user_id=%s AND state='pending' AND user_id IN (SELECT id FROM users WHERE disabled=0)",
                             (time.time(), user_id)).rowcount
    if not claimed:
        return "adding"
    state, error = "synced", ""
    try:
        client.append(row["email"])
    except AccessAPIError as exc:
        state, error = "review", str(exc)
    with store.connect() as db:
        db.execute("UPDATE cloudflare_enrollments SET state=%s,last_error=%s,updated_at=%s WHERE user_id=%s AND state='adding'",
                   (state, error, time.time(), user_id))
    return state


class AccessVerifier:
    def __init__(self, settings):
        self.settings = settings
        self.keys = {}
        self.refreshed_at = 0.0
        self.lock = threading.Lock()

    def verify(self, token):
        import jwt
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise AuthError("cloudflare_login_required", 401)
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise AuthError("cloudflare_identity_invalid", 401)
            with self.lock:
                if time.monotonic() - self.refreshed_at > 60:
                    # Fixed issuer, not an untrusted jku/x5u from the JWT header.
                    request = Request(self.settings.team_domain + "/cdn-cgi/access/certs")
                    with build_opener(NoRedirect()).open(request, timeout=5) as response:
                        raw = response.read(128 * 1024 + 1)
                    if len(raw) > 128 * 1024:
                        raise ValueError()
                    keys = json.loads(raw)["keys"]
                    self.keys = {key["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                                 for key in keys if key.get("kty") == "RSA"}
                    self.refreshed_at = time.monotonic()
                key = self.keys.get(header["kid"])
            if key is None:
                raise AuthError("cloudflare_identity_invalid", 401)
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.settings.audience,
                                issuer=self.settings.team_domain,
                                options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]})
            if claims.get("type") != "app" or not isinstance(claims["sub"], str) or not claims["sub"] or claims.get("service_token_id"):
                raise AuthError("cloudflare_identity_invalid", 401)
            return normalize_email(claims["email"])
        except AuthError:
            raise
        except (jwt.PyJWTError, OSError, ValueError, KeyError, TypeError):
            raise AuthError("cloudflare_identity_invalid", 401) from None


def local_request(handler):
    """Explicit loopback administration only; forwarded requests cannot opt out."""
    try:
        if not ipaddress.ip_address(handler.client_address[0]).is_loopback:
            return False
        if any(handler.headers.get(name) for name in
               ("Cf-Ray", "CF-Connecting-IP", "Cf-Access-Jwt-Assertion", "Forwarded")):
            return False
        for authority in (handler.headers.get("Host", ""), handler.headers.get("X-Forwarded-Host", "")):
            if authority and urlsplit("http://" + authority).hostname not in {"localhost", "127.0.0.1", "::1"}:
                return False
        if not handler.headers.get("Host"):
            return False
        origin = handler.headers.get("Origin", "")
        if origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False
        return True
    except ValueError:
        return False
