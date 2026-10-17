"""Two-step sign-in with an authenticator app (TOTP: Google Authenticator,
1Password, Authy...). Required for superadmins, who can see every team.

Codes are checked one step either side of now (phone clocks drift) and each
can only be used once. Ten one-time recovery codes are given at setup and
stored hashed, like passwords.
"""
import base64
import io
import json
import secrets
from datetime import datetime

import pyotp
from werkzeug.security import check_password_hash, generate_password_hash

ISSUER = 'Ultimate Coach'
RECOVERY_CODE_COUNT = 10


def new_secret():
    return pyotp.random_base32()


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=ISSUER)


def qr_data_uri(uri):
    """The setup link as a QR code PNG data URI (None if qrcode is missing)."""
    try:
        import qrcode
    except ImportError:
        return None
    img = qrcode.make(uri, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _clean(code):
    return ''.join(ch for ch in (code or '') if ch.isalnum()).lower()


def matching_step(secret, code, after=None):
    """The time step the 6-digit code belongs to (now, or one step either
    side), or None. Steps at or before `after` were already used."""
    code = _clean(code)
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    now = totp.timecode(datetime.now())
    for step in (now, now - 1, now + 1):
        if after is not None and step <= after:
            continue
        if secrets.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def verify_code(user, code):
    """Check a code from the app and use it up. The caller commits."""
    if not user.totp_secret:
        return False
    step = matching_step(user.totp_secret, code, after=user.totp_last_step)
    if step is None:
        return False
    user.totp_last_step = step
    return True


def new_recovery_codes():
    """(codes to show once, JSON of their hashes to store)."""
    codes = [f'{secrets.token_hex(2)}-{secrets.token_hex(2)}' for _ in range(RECOVERY_CODE_COUNT)]
    return codes, json.dumps([generate_password_hash(_clean(c)) for c in codes])


def use_recovery_code(user, code):
    """Check a recovery code and cross it off. The caller commits."""
    code = _clean(code)
    if len(code) != 8:
        return False
    hashes = json.loads(user.totp_recovery_codes or '[]')
    for stored in hashes:
        if check_password_hash(stored, code):
            hashes.remove(stored)
            user.totp_recovery_codes = json.dumps(hashes)
            return True
    return False


def recovery_codes_left(user):
    return len(json.loads(user.totp_recovery_codes or '[]'))


def enable(user, secret):
    """Turn it on with a confirmed secret; returns the recovery codes to
    show. The caller commits."""
    codes, hashed = new_recovery_codes()
    user.totp_secret = secret
    user.totp_recovery_codes = hashed
    return codes


def disable(user):
    user.totp_secret = None
    user.totp_recovery_codes = None
    user.totp_last_step = None


def required_for(user):
    return bool(getattr(user, 'is_superadmin', False))
