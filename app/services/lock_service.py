"""PIN lock: salted PBKDF2 hashes in app_meta, lockout, biometrics preference."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db import get_meta, set_meta

PIN_LENGTH = 4
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
PBKDF2_ITERATIONS = 120_000
SALT_BYTES = 16

KEY_LOCK_ENABLED = "lock_enabled"
KEY_PIN_SALT = "pin_salt"
KEY_PIN_HASH = "pin_hash"
KEY_PIN_ITERS = "pin_iterations"
KEY_BIOMETRICS = "biometrics_enabled"
KEY_SETUP_DONE = "lock_setup_done"
KEY_FAIL_COUNT = "pin_fail_count"
KEY_LOCKOUT_UNTIL = "pin_lockout_until"

_PIN_RE = re.compile(rf"^\d{{{PIN_LENGTH}}}$")


@dataclass(frozen=True)
class UnlockResult:
    ok: bool
    reason: str  # ok | wrong | lockout | invalid | no_pin
    remaining_attempts: int = MAX_ATTEMPTS
    lockout_remaining_sec: float = 0.0
    shake: bool = False


def is_valid_pin(pin: str | None) -> bool:
    return bool(_PIN_RE.fullmatch(pin or ""))


def hash_pin(
    pin: str,
    *,
    salt: bytes | None = None,
    iterations: int = PBKDF2_ITERATIONS,
) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) using PBKDF2-HMAC-SHA256. Never store ``pin``."""
    if salt is None:
        salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", (pin or "").encode("utf-8"), salt, int(iterations))
    return salt.hex(), dk.hex()


def verify_pin(
    pin: str | None,
    salt_hex: str | None,
    hash_hex: str | None,
    *,
    iterations: int = PBKDF2_ITERATIONS,
) -> bool:
    try:
        salt = bytes.fromhex(salt_hex or "")
        expected = bytes.fromhex(hash_hex or "")
    except (TypeError, ValueError):
        return False
    if not salt or not expected:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        (pin or "").encode("utf-8"),
        salt,
        int(iterations),
    )
    return hmac.compare_digest(dk, expected)


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _iters(session: Session) -> int:
    raw = get_meta(session, KEY_PIN_ITERS)
    try:
        v = int(str(raw).strip()) if raw else PBKDF2_ITERATIONS
    except (TypeError, ValueError):
        v = PBKDF2_ITERATIONS
    return v if v > 0 else PBKDF2_ITERATIONS


def has_pin(session: Session) -> bool:
    salt = get_meta(session, KEY_PIN_SALT)
    digest = get_meta(session, KEY_PIN_HASH)
    return bool(salt and digest)


def is_lock_enabled(session: Session) -> bool:
    return _truthy(get_meta(session, KEY_LOCK_ENABLED)) and has_pin(session)


def should_gate_main(session: Session) -> bool:
    """True when the lock screen must sit in front of the main UI."""
    return is_lock_enabled(session)


def needs_pin_setup(session: Session) -> bool:
    return get_meta(session, KEY_SETUP_DONE) != "1"


def is_biometrics_enabled(session: Session) -> bool:
    return _truthy(get_meta(session, KEY_BIOMETRICS))


def is_biometrics_available() -> bool:
    """Desktop Flet has no Face ID / local auth; iOS would report True later."""
    return False


def biometrics_unavailable_message() -> str:
    return "Face ID недоступен на этом устройстве — используйте PIN"


def skip_lock_setup(session: Session) -> None:
    """User chose «Настроить позже»: lock stays off until enabled in Settings."""
    set_meta(session, KEY_SETUP_DONE, "1")
    set_meta(session, KEY_LOCK_ENABLED, "0")
    session.commit()


def setup_pin(session: Session, pin: str, *, biometrics: bool = False) -> None:
    if not is_valid_pin(pin):
        raise ValueError("PIN must be exactly 4 digits")
    salt_hex, hash_hex = hash_pin(pin)
    set_meta(session, KEY_PIN_SALT, salt_hex)
    set_meta(session, KEY_PIN_HASH, hash_hex)
    set_meta(session, KEY_PIN_ITERS, str(PBKDF2_ITERATIONS))
    set_meta(session, KEY_LOCK_ENABLED, "1")
    set_meta(session, KEY_SETUP_DONE, "1")
    set_meta(session, KEY_BIOMETRICS, "1" if biometrics else "0")
    set_meta(session, KEY_FAIL_COUNT, "0")
    set_meta(session, KEY_LOCKOUT_UNTIL, "")
    session.commit()


def change_pin(session: Session, pin: str) -> None:
    if not is_valid_pin(pin):
        raise ValueError("PIN must be exactly 4 digits")
    salt_hex, hash_hex = hash_pin(pin)
    set_meta(session, KEY_PIN_SALT, salt_hex)
    set_meta(session, KEY_PIN_HASH, hash_hex)
    set_meta(session, KEY_PIN_ITERS, str(PBKDF2_ITERATIONS))
    set_meta(session, KEY_SETUP_DONE, "1")
    set_meta(session, KEY_FAIL_COUNT, "0")
    set_meta(session, KEY_LOCKOUT_UNTIL, "")
    session.commit()


def set_lock_enabled(session: Session, enabled: bool) -> bool:
    """Enable only when a PIN hash already exists. Disable always allowed."""
    if enabled:
        if not has_pin(session):
            return False
        set_meta(session, KEY_LOCK_ENABLED, "1")
        set_meta(session, KEY_SETUP_DONE, "1")
    else:
        set_meta(session, KEY_LOCK_ENABLED, "0")
    session.commit()
    return True


def set_biometrics_enabled(session: Session, enabled: bool) -> None:
    set_meta(session, KEY_BIOMETRICS, "1" if enabled else "0")
    session.commit()


def _now(now: float | None) -> float:
    return float(now) if now is not None else time.time()


def _fail_count(session: Session) -> int:
    raw = get_meta(session, KEY_FAIL_COUNT)
    try:
        return max(0, int(str(raw).strip())) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def lockout_remaining_sec(session: Session, *, now: float | None = None) -> float:
    raw = get_meta(session, KEY_LOCKOUT_UNTIL)
    try:
        until = float(raw) if raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        until = 0.0
    return max(0.0, until - _now(now))


def _clear_failures(session: Session) -> None:
    set_meta(session, KEY_FAIL_COUNT, "0")
    set_meta(session, KEY_LOCKOUT_UNTIL, "")


def unlock(session: Session, pin: str, *, now: float | None = None) -> UnlockResult:
    ts = _now(now)
    remaining_lock = lockout_remaining_sec(session, now=ts)
    if remaining_lock > 0:
        return UnlockResult(
            ok=False,
            reason="lockout",
            remaining_attempts=0,
            lockout_remaining_sec=remaining_lock,
            shake=False,
        )
    if get_meta(session, KEY_LOCKOUT_UNTIL):
        _clear_failures(session)

    if not has_pin(session):
        return UnlockResult(ok=False, reason="no_pin", shake=False)

    if not is_valid_pin(pin):
        return UnlockResult(ok=False, reason="invalid", shake=True)

    salt = get_meta(session, KEY_PIN_SALT)
    digest = get_meta(session, KEY_PIN_HASH)
    if verify_pin(pin, salt, digest, iterations=_iters(session)):
        _clear_failures(session)
        session.commit()
        return UnlockResult(ok=True, reason="ok", remaining_attempts=MAX_ATTEMPTS)

    count = _fail_count(session) + 1
    set_meta(session, KEY_FAIL_COUNT, str(count))
    if count >= MAX_ATTEMPTS:
        set_meta(session, KEY_LOCKOUT_UNTIL, str(ts + LOCKOUT_SECONDS))
        session.commit()
        return UnlockResult(
            ok=False,
            reason="lockout",
            remaining_attempts=0,
            lockout_remaining_sec=float(LOCKOUT_SECONDS),
            shake=True,
        )
    session.commit()
    return UnlockResult(
        ok=False,
        reason="wrong",
        remaining_attempts=MAX_ATTEMPTS - count,
        shake=True,
    )
