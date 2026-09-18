#!/usr/bin/env python3
"""Time-based one-time passwords, the way every authenticator app expects.

RFC 6238 on top of RFC 4226: a shared secret, the clock divided into
thirty-second steps, HMAC over the step number, and six digits taken from
the result. Thirty lines of standard library, and the same six digits that
Google Authenticator, Aegis, 1Password and the rest produce.

Two details keep it honest:

    a window     phones and servers disagree about the clock by a few
                 seconds. One step either side is accepted, no more.
    replay       a code stays valid for thirty seconds, which is long
                 enough to be used twice. The caller records the step it
                 accepted and refuses anything not newer.

Verified against the test vectors in RFC 6238, appendix B — see the self
test, group 'two factor'.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

DIGITS = 6
STEP = 30
WINDOW = 1          # Steps accepted either side of now.
SECRET_BYTES = 20   # 160 bits, as RFC 4226 recommends.


def new_secret() -> str:
    """A fresh secret, in the base32 spelling the apps read."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def normalise(secret: str) -> bytes:
    """Accepts what a person may paste: spaces, lower case, missing padding."""
    cleaned = secret.replace(" ", "").replace("-", "").upper()
    cleaned += "=" * (-len(cleaned) % 8)
    return base64.b32decode(cleaned, casefold=True)


def code_at(secret: str, step: int, *, digest=hashlib.sha1, digits: int = DIGITS) -> str:
    """The code for one time step. RFC 4226, section 5.3."""
    mac = hmac.new(normalise(secret), struct.pack(">Q", step), digest).digest()
    offset = mac[-1] & 0x0F
    truncated = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def current_step(when: float | None = None) -> int:
    return int((time.time() if when is None else when) // STEP)


def check(secret: str, presented: str, *, last_step: int = -1,
          when: float | None = None) -> tuple[bool, int]:
    """Returns (accepted, step). The step must be recorded against replay."""
    digits = "".join(character for character in presented if character.isdigit())
    if len(digits) != DIGITS:
        return False, last_step
    now = current_step(when)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if step <= last_step:
            continue                      # Already spent: no second use.
        if hmac.compare_digest(code_at(secret, step), digits):
            return True, step
    return False, last_step


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The otpauth:// URI an authenticator app scans."""
    label = urllib.parse.quote(f"{issuer}:{account}", safe="")
    query = urllib.parse.urlencode({"secret": secret, "issuer": issuer,
                                    "algorithm": "SHA1", "digits": DIGITS,
                                    "period": STEP})
    return f"otpauth://totp/{label}?{query}"


def recovery_codes(count: int = 10) -> list[str]:
    """Codes for the day the phone is gone. Shown once, stored hashed."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"   # No look-alikes.
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes
