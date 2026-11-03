"""Local credentials: salted PBKDF2-SHA256; never store plaintext passwords."""

import hashlib
import hmac
import re
import secrets


def normalize_username(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._@-]{2,63}", value):
        raise ValueError("账号需为 3–64 位字母、数字或 . _ @ -")
    return value


def hash_password(password):
    if not 12 <= len(password) <= 128:
        raise ValueError("密码长度需为 12–128 个字符")
    salt = secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return f"pbkdf2_sha256$600000${salt.hex()}${value.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(rounds) != 600000 or len(password) > 128:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
