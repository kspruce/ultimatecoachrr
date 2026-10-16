"""Password-reset links.

A link is a signed token holding the user's id and a fingerprint of their
current password hash, so it stops working as soon as the password changes
(it can only be used once) and needs no database table. How long it lasts
is signed into the token too: an hour for links sent by email, three days
for links a coach hands out.
"""
import hashlib

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app import db
from app.models.user import User

EMAIL_LINK_SECONDS = 60 * 60
COACH_LINK_SECONDS = 3 * 24 * 60 * 60
_SALT = 'password-reset'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def _fingerprint(user):
    return hashlib.sha256((user.password_hash or 'no-password').encode()).hexdigest()[:16]


def make_reset_token(user, valid_for=EMAIL_LINK_SECONDS):
    return _serializer().dumps({'u': user.id, 'f': _fingerprint(user), 't': valid_for})


def reset_url(user, valid_for=EMAIL_LINK_SECONDS):
    return url_for('auth.reset_password', token=make_reset_token(user, valid_for), _external=True)


def user_for_reset_token(token):
    """The user a still-valid token belongs to, else None."""
    try:
        data = _serializer().loads(token, max_age=COACH_LINK_SECONDS)
        user = db.session.get(User, int(data['u']))
        # Re-check age against this link's own lifetime
        _serializer().loads(token, max_age=int(data['t']))
    except (BadSignature, KeyError, TypeError, ValueError):
        return None
    if user is None or data.get('f') != _fingerprint(user):
        return None
    return user
