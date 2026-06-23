from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


PASSWORD_ITERATIONS = 310_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(connection, user_id: int, duration_hours: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (utc_now() + timedelta(hours=duration_hours)).isoformat()
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires_at),
    )
    return token


def resolve_session(connection, token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = connection.execute(
        """
        SELECT u.id, u.username, u.full_name, u.email, u.role, u.active, s.expires_at
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.revoked_at IS NULL
        """,
        (token_hash,),
    ).fetchone()
    if not row or not row["active"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) <= utc_now():
        return None
    return row


def revoke_session(connection, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    connection.execute(
        "UPDATE sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token_hash = ?",
        (token_hash,),
    )
