"""Two-step sign-in (authenticator app codes), required for superadmins."""
import time

import pyotp
import pytest

from app import db
from app.models.user import User
from app.utils import two_factor
from tests import stats_data


@pytest.fixture
def site(app):
    app.config['TWO_FACTOR_REQUIRED'] = True
    team = stats_data.build_team()
    boss = User(username='boss', email='boss@example.com', role='admin', is_superadmin=True,
                team_organization_id=team.id)
    coach = User(username='coachy', role='coach', team_organization_id=team.id)
    for user in (boss, coach):
        user.set_password('right-password')
    db.session.add_all([boss, coach])
    db.session.commit()
    return {'team': team.id, 'boss': boss.id, 'coach': coach.id}


def turn_on(user_id):
    """Two-step sign-in for a user as if they'd done the setup."""
    user = db.session.get(User, user_id)
    secret = two_factor.new_secret()
    codes = two_factor.enable(user, secret)
    db.session.commit()
    return pyotp.TOTP(secret), codes


class Browser:
    """A visitor; each request in its own app context, as in production."""

    def __init__(self, app):
        self.app, self.client = app, app.test_client()

    def get(self, url, **kw):
        with self.app.app_context():
            return self.client.get(url, **kw)

    def post(self, url, **kw):
        with self.app.app_context():
            return self.client.post(url, **kw)

    def session_transaction(self):
        return self.client.session_transaction()


def log_in(app, username='boss', password='right-password', next_page=None):
    client = Browser(app)
    url = '/auth/login' + (f'?next={next_page}' if next_page else '')
    r = client.post(url, data={'username': username, 'password': password})
    return client, r


def logged_in(client):
    return client.get('/auth/account').status_code == 200


def test_superadmins_must_set_it_up_before_anything_else(app, site):
    client, r = log_in(app)
    assert r.status_code == 302
    page = client.get('/team/')
    assert page.status_code == 302 and '/auth/two-factor/setup' in page.location

    setup = client.get('/auth/two-factor/setup')
    assert setup.status_code == 200 and b'data:image/png;base64' in setup.data  # QR code
    with client.session_transaction() as s:
        secret = s['tfa_setup_secret']
    assert client.post('/auth/two-factor/setup', data={'code': '000000'}).status_code == 200
    assert db.session.get(User, site['boss']).totp_secret is None  # wrong code: not on

    r = client.post('/auth/two-factor/setup', data={'code': pyotp.TOTP(secret).now()})
    assert b'Save your recovery codes' in r.data
    db.session.expire_all()
    boss = db.session.get(User, site['boss'])
    assert boss.totp_secret == secret and two_factor.recovery_codes_left(boss) == 10
    assert client.get('/team/').status_code == 200  # still logged in, and through


def test_other_roles_are_not_made_to(app, site):
    client, _ = log_in(app, 'coachy')
    assert client.get('/team/').status_code == 200


def test_login_needs_the_code_after_the_password(app, site):
    totp, _ = turn_on(site['boss'])
    client, r = log_in(app, next_page='/team/')
    assert '/auth/two-factor' in r.location
    assert not logged_in(client)

    client.post('/auth/two-factor', data={'code': '123456'})
    assert not logged_in(client)
    r = client.post('/auth/two-factor', data={'code': totp.now()})
    assert r.status_code == 302 and r.location.endswith('/team/')
    assert logged_in(client)


def test_a_code_works_only_once(app, site):
    totp, _ = turn_on(site['boss'])
    code = totp.now()
    first, _ = log_in(app)
    first.post('/auth/two-factor', data={'code': code})
    assert logged_in(first)
    second, _ = log_in(app)
    second.post('/auth/two-factor', data={'code': code})
    assert not logged_in(second)


def test_recovery_codes_work_once_each(app, site):
    _, codes = turn_on(site['boss'])
    client, _ = log_in(app)
    client.post('/auth/two-factor', data={'code': codes[0].upper()})
    assert logged_in(client)
    assert two_factor.recovery_codes_left(db.session.get(User, site['boss'])) == 9
    again, _ = log_in(app)
    again.post('/auth/two-factor', data={'code': codes[0]})
    assert not logged_in(again)


def test_too_many_wrong_codes_start_the_login_again(app, site):
    totp, _ = turn_on(site['boss'])
    client, _ = log_in(app)
    for _ in range(5):
        client.post('/auth/two-factor', data={'code': '000000'})
    r = client.post('/auth/two-factor', data={'code': totp.now()})
    assert '/auth/login' in r.location and not logged_in(client)


def test_the_code_step_expires(app, site, monkeypatch):
    totp, _ = turn_on(site['boss'])
    client, _ = log_in(app)
    later = time.time() + 6 * 60
    monkeypatch.setattr(time, 'time', lambda: later)
    client.post('/auth/two-factor', data={'code': totp.now()})
    assert not logged_in(client)


def test_wrong_password_never_reaches_the_code_step(app, site):
    turn_on(site['boss'])
    client, r = log_in(app, password='wrong-password')
    assert '/auth/two-factor' not in r.location
    assert client.get('/auth/two-factor').status_code == 302


def test_setting_it_up_again_signs_out_other_devices(app, site):
    totp, _ = turn_on(site['boss'])
    laptop, _ = log_in(app)
    laptop.post('/auth/two-factor', data={'code': totp.now()})
    assert logged_in(laptop)
    turn_on(site['boss'])  # e.g. moved to a new phone on another device
    assert not logged_in(laptop)


def test_moving_to_a_new_phone_needs_the_password(app, site):
    totp, _ = turn_on(site['boss'])
    client, _ = log_in(app)
    client.post('/auth/two-factor', data={'code': totp.now()})
    client.get('/auth/two-factor/setup')
    with client.session_transaction() as s:
        new = pyotp.TOTP(s['tfa_setup_secret'])
    old_secret = db.session.get(User, site['boss']).totp_secret
    client.post('/auth/two-factor/setup', data={'code': new.now(), 'password': 'wrong'})
    db.session.expire_all()
    assert db.session.get(User, site['boss']).totp_secret == old_secret
    client.post('/auth/two-factor/setup', data={'code': new.now(), 'password': 'right-password'})
    db.session.expire_all()
    assert db.session.get(User, site['boss']).totp_secret == new.secret
    assert logged_in(client)


def test_command_line_reset_for_a_lost_phone(app, site):
    turn_on(site['boss'])
    result = app.test_cli_runner().invoke(args=['reset-two-factor', 'boss'])
    assert result.exit_code == 0, result.output
    db.session.expire_all()
    assert not db.session.get(User, site['boss']).two_factor_enabled


def test_secrets_never_go_in_a_team_download(app, site):
    from app.utils.team_data import team_tables
    turn_on(site['boss'])
    users = team_tables(site['team'])['user']
    assert all('totp_secret' not in u and 'totp_recovery_codes' not in u and 'password_hash' not in u
               for u in users)
