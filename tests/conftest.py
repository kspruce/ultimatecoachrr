import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Never let a test touch a real database: point at a throwaway SQLite file
# unless TEST_DATABASE_URL is given (e.g. a local Postgres).
os.environ['DATABASE_URL'] = os.environ.get('TEST_DATABASE_URL', 'sqlite:///:memory:')
# Somewhere writable for uploads (.env may point at Railway's /app folder).
os.environ['UPLOAD_FOLDER'] = tempfile.mkdtemp(prefix='herd-uploads-')
for key in ('AWS_ACCESS_KEY', 'AWS_SECRET_KEY', 'AWS_BUCKET_NAME'):
    os.environ.pop(key, None)

from app import create_app, db  # noqa: E402
from config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = REMEMBER_COOKIE_SECURE = False  # the test client is plain http
    TWO_FACTOR_REQUIRED = False  # tests/test_two_factor.py turns it on
    RATELIMIT_ENABLED = False  # tests/test_accounts.py turns it on where it's tested
    MAIL_SERVER = None  # no email unless a test sets it up
    ADMINS = []
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def team(app):
    from app.models.team_organization import TeamOrganization
    team = TeamOrganization(name='Thundering Herd', slug='thundering-herd')
    db.session.add(team)
    db.session.commit()
    return team
