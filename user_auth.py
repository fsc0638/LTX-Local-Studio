"""Local accounts with explicit verified-email and internal-testing policies.

No debug verification links, passwords, or session secrets are returned in JSON.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from urllib.parse import urlsplit

PASSWORD_N = 2**17
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
SESSION_SECONDS = 8 * 3600
TOKEN_SECONDS = 1800
AUTH_SLOTS = threading.BoundedSemaphore(2)


class AuthError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_email(value):
    if not isinstance(value, str):
        raise AuthError("invalid_email")
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise AuthError("invalid_email")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in value or any(not label or label.startswith("-") or label.endswith("-") for label in domain.split(".")):
        raise AuthError("invalid_email")
    return value


def check_password(value):
    if not isinstance(value, str) or not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH or "\x00" in value:
        raise AuthError("invalid_password")
    return value


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=PASSWORD_N, r=8, p=1, maxmem=256 * 1024**2).hex()
    return f"scrypt${PASSWORD_N}$8$1${salt}${key}"


def password_matches(password, encoded):
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if (scheme, int(n), int(r), int(p)) != ("scrypt", PASSWORD_N, 8, 1):
            return False
        actual = password_hash(password, salt).rsplit("$", 1)[1]
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def public_user(row):
    return {key: row[key] for key in ("id", "name", "username", "email")} | {"email_verified": bool(row["verified_at"])}


@dataclass(frozen=True)
class AuthSettings:
    origin: str
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"
    registration_enabled: bool = False
    auth_mode: str = "verified_email"

    def __post_init__(self):
        if self.auth_mode not in {"verified_email", "internal"}:
            raise ValueError("LTX_AUTH_MODE must be verified_email or internal")

    @classmethod
    def from_env(cls):
        origin = os.environ.get("LTX_PUBLIC_ORIGIN", "").rstrip("/")
        if origin:
            parsed = urlsplit(origin)
            if (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path or not parsed.hostname or
                    (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}))):
                raise ValueError("LTX_PUBLIC_ORIGIN must be an HTTPS origin (HTTP only for loopback)")
        mode = os.environ.get("LTX_AUTH_MODE", "verified_email")
        if mode == "internal":
            # Dormant SMTP secrets/configuration must not prevent local testing.
            return cls(origin, registration_enabled=os.environ.get("LTX_REGISTRATION_ENABLED") == "1", auth_mode=mode)
        secret = os.environ.get("LTX_SMTP_PASSWORD", "")
        if os.environ.get("LTX_SMTP_PASSWORD_FILE"):
            path = Path(os.environ["LTX_SMTP_PASSWORD_FILE"])
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise ValueError("SMTP password file must be private (0600) and not a symlink")
            secret = path.read_text().strip()
        return cls(origin, os.environ.get("LTX_SMTP_HOST", ""), int(os.environ.get("LTX_SMTP_PORT", "587")),
                   os.environ.get("LTX_SMTP_USERNAME", ""), secret, os.environ.get("LTX_SMTP_FROM", ""),
                   os.environ.get("LTX_SMTP_SECURITY", "starttls"), os.environ.get("LTX_REGISTRATION_ENABLED") == "1",
                   mode)

    @property
    def verification_required(self):
        return self.auth_mode == "verified_email"

    @property
    def registration_open(self):
        return bool(self.origin and self.registration_enabled and (not self.verification_required or self.email_ready))

    @property
    def email_ready(self):
        return bool(self.origin and self.smtp_host and self.smtp_from and self.smtp_security in {"starttls", "ssl"}
                    and (not self.smtp_user or self.smtp_password))

    @property
    def secure_cookie(self):
        return not self.origin.startswith("http://")

    def send(self, email, token, kind):
        if not self.verification_required:
            raise AuthError("email_disabled_in_internal_mode", 503)
        if not self.email_ready:
            raise AuthError("email_not_configured", 503)
        # Fragment is not sent in HTTP requests/access logs or Referer headers.
        route = "verify" if kind == "verify" else "reset"
        url = f"{self.origin}/auth/{route}#token={token}"
        message = EmailMessage()
        message["From"], message["To"] = self.smtp_from, email
        message["Subject"] = "LTX Local Studio — 驗證電子郵件 / Verify email" if kind == "verify" else "LTX Local Studio — 重設密碼 / Reset password"
        message.set_content(f"LTX Local Studio\n\n{'請確認您的電子郵件。' if kind == 'verify' else '請設定新的密碼。'}\n"
                            f"Open this link within 30 minutes:\n{url}\n\n"
                            "完成後請重新登入；此連結不會自動登入。\n"
                            "If you did not request this, ignore this email. Do not share the link.\n")
        context = ssl.create_default_context()
        try:
            connector = smtplib.SMTP_SSL if self.smtp_security == "ssl" else smtplib.SMTP
            kwargs = {"context": context} if self.smtp_security == "ssl" else {}
            with connector(self.smtp_host, self.smtp_port, timeout=10, **kwargs) as smtp:
                if self.smtp_security == "starttls":
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password)
                if smtp.send_message(message):
                    raise AuthError("email_delivery_failed", 503)
        except (OSError, smtplib.SMTPException):
            raise AuthError("email_delivery_failed", 503) from None


class AuthStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at REAL NOT NULL,
                verified_at REAL, disabled INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS email_tokens (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                kind TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id,kind)")
            db.execute("CREATE TABLE IF NOT EXISTS rate_limits (scope TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL)")
            # Keep enrollment history even if an account is later removed. Never
            # reconstruct this table from users: a dashboard removal is final.
            db.execute("""CREATE TABLE IF NOT EXISTS cloudflare_enrollments (
                email TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE, target TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','adding','synced','review')),
                last_error TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rate(self, scope, limit, window):
        scope, now = digest(scope), time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate_limits WHERE expires_at < ?", (now,))
            row = db.execute("SELECT count FROM rate_limits WHERE scope=?", (scope,)).fetchone()
            if row and row[0] >= limit:
                raise AuthError("rate_limited", 429)
            db.execute("INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(scope) DO UPDATE SET count=count+1", (scope, now + window))

    def register(self, raw, *, access_target=""):
        name, username = raw.get("name"), raw.get("username")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise AuthError("invalid_name")
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,31}", username):
            raise AuthError("invalid_username")
        email, password = normalize_email(raw.get("email")), check_password(raw.get("password"))
        encoded = password_hash(password)
        user_id = secrets.token_hex(16)
        with self.connect() as db:
            try:
                db.execute("INSERT INTO users(id,name,username,email,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                           (user_id, name.strip(), username.lower(), email, encoded, time.time()))
                if access_target:
                    db.execute("INSERT INTO cloudflare_enrollments(email,user_id,target,state,created_at,updated_at) VALUES(?,?,?,'pending',?,?)",
                               (email, user_id, access_target, time.time(), time.time()))
            except sqlite3.IntegrityError:
                db.rollback()
                # Neither overwrite pending passwords nor disclose which field exists.
                return None
        return user_id, email

    def issue_email_token(self, user_id, kind):
        token, now = secrets.token_urlsafe(32), time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT created_at FROM email_tokens WHERE user_id=? AND kind=?", (user_id, kind)).fetchone()
            if previous and now - previous[0] < 60:
                raise AuthError("rate_limited", 429)
            db.execute("DELETE FROM email_tokens WHERE user_id=? AND kind=?", (user_id, kind))
            db.execute("INSERT INTO email_tokens VALUES(?,?,?,?,?)", (digest(token), user_id, kind, now, now + TOKEN_SECONDS))
        return token

    def mail_target(self, email, kind):
        email = normalize_email(email)
        with self.connect() as db:
            row = db.execute("SELECT id,email,verified_at,disabled FROM users WHERE email=?", (email,)).fetchone()
        if not row or row["disabled"] or (kind == "verify" and row["verified_at"]) or (kind == "reset" and not row["verified_at"]):
            return None
        return row["id"], row["email"]

    def consume_token(self, token, kind, new_password=None):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise AuthError("invalid_or_expired_token")
        encoded = password_hash(check_password(new_password)) if kind == "reset" else None
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT t.user_id FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.kind=? AND t.expires_at>? AND u.disabled=0",
                             (digest(token), kind, now)).fetchone()
            if not row:
                raise AuthError("invalid_or_expired_token")
            if kind == "verify":
                db.execute("UPDATE users SET verified_at=? WHERE id=?", (now, row[0]))
            else:
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, row[0]))
            db.execute("DELETE FROM email_tokens WHERE user_id=?", (row[0],))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row[0],))
        # Deliberately no session: verification/reset always requires a fresh login.

    def login(self, username, password, *, require_verified=True, access_email=None):
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 254 or len(password) > PASSWORD_MAX_LENGTH:
            raise AuthError("invalid_credentials", 401)
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        # Do comparable expensive work even for nonexistent accounts.
        dummy = f"scrypt${PASSWORD_N}$8$1$" + "00" * 16 + "$" + "00" * 64
        valid = password_matches(password, row["password_hash"] if row else dummy)
        if not valid or not row or row["disabled"]:
            raise AuthError("invalid_credentials", 401)
        if access_email is not None and row["email"] != access_email:
            raise AuthError("cloudflare_email_mismatch", 403)
        if require_verified and not row["verified_at"] and access_email is None:
            raise AuthError("email_not_verified", 403)
        token, now = secrets.token_urlsafe(32), time.time()
        with self.connect() as db:
            if access_email is not None:
                # Called only with an email from a cryptographically verified
                # Access application token, never a client-supplied email header.
                db.execute("UPDATE users SET verified_at=COALESCE(verified_at,?) WHERE id=? AND password_hash=? AND disabled=0",
                           (now, row["id"], row["password_hash"]))
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            # Recheck password/verified state while creating the session to avoid
            # granting access after a concurrent password reset or disable.
            changed = db.execute("INSERT INTO sessions SELECT ?,id,? FROM users WHERE id=? AND password_hash=? AND (?=0 OR verified_at IS NOT NULL) AND disabled=0",
                                 (digest(token), now + SESSION_SECONDS, row["id"], row["password_hash"], int(require_verified))).rowcount
            if not changed:
                raise AuthError("invalid_credentials", 401)
            row = db.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
        return token, public_user(row)

    def session(self, token, *, require_verified=True):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        with self.connect() as db:
            row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND (?=0 OR u.verified_at IS NOT NULL) AND u.disabled=0",
                             (digest(token), time.time(), int(require_verified))).fetchone()
        return public_user(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))


def csrf_token(session):
    return digest("ltx-csrf-v1:" + session)
