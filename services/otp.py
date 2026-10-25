"""TOTP（RFC 6238）与恢复码。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

from services import settings

STEP = 30
DIGITS = 6
RECOVERY_N = 10
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def base32_encode(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def base32_decode(text: str) -> bytes:
    text = (text or "").strip().replace(" ", "").upper()
    pad = (-len(text)) % 8
    return base64.b32decode(text + "=" * pad)


def new_secret() -> str:
    return base32_encode(secrets.token_bytes(20))


def secret() -> str:
    return settings.get_str("otp_secret", "").strip()


def emergency_off() -> bool:
    return settings.bool_of("otp_emergency_off", False)


def configured() -> bool:
    return bool(secret())


def enabled() -> bool:
    return configured() and settings.bool_of("otp_enabled", False) and not emergency_off()


def totp_code(secret_b32: str, timestamp: int | None = None) -> str:
    if not secret_b32:
        return ""
    counter = int((timestamp if timestamp is not None else time.time()) // STEP)
    key = base32_decode(secret_b32)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** DIGITS)).zfill(DIGITS)


def verify(secret_b32: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    now = int(time.time())
    for offset in range(-window, window + 1):
        expected = totp_code(secret_b32, now + offset * STEP)
        if expected and hmac.compare_digest(expected, code):
            return True
    return False


def otpauth_uri(secret_b32: str, username: str, issuer: str = "infowe Blog") -> str:
    label = quote(f"{issuer}:{username}")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"
    )


def gen_recovery_codes(count: int = RECOVERY_N) -> tuple[list[str], list[str]]:
    codes = []
    for _ in range(count):
        code = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
        code += "-"
        code += "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
        codes.append(code)
    # 与消费端一致：先规范化（去连字符、大写）再哈希
    hashes = [hashlib.sha256(normalize_recovery(c).encode()).hexdigest() for c in codes]
    return codes, hashes


def recovery_hashes() -> list[str]:
    raw = settings.get_str("otp_recovery_codes", "")
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return [str(v) for v in value] if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def recovery_remaining() -> int:
    return len(recovery_hashes())


def normalize_recovery(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def consume_recovery(code: str) -> bool:
    norm = normalize_recovery(code)
    if not norm:
        return False
    digest = hashlib.sha256(norm.encode()).hexdigest()
    # 兼容旧版（PHP）直接对含连字符原文哈希的存储
    legacy = hashlib.sha256((code or "").strip().upper().encode()).hexdigest()
    hashes = recovery_hashes()
    matched = digest if digest in hashes else (legacy if legacy in hashes else "")
    if not matched:
        return False
    hashes = [h for h in hashes if h != matched]
    settings.set_value("otp_recovery_codes", json.dumps(hashes))
    return True


def reset() -> None:
    settings.set_many(
        {"otp_secret": "", "otp_recovery_codes": "[]", "otp_enabled": "0", "otp_emergency_off": "0"}
    )
