"""Accounts across teams: who may manage whom, team join links, team sign-up
links, password resets and rate limits."""
import re

import pytest

from app import db, limiter
from app.models.feedback import PlayerFeedback
from app.models.invite_token import InviteToken
from app.models.site_settings import SiteSettings
from app.models.team_organization import TeamOrganization
from app.models.team_signup_invite import TeamSignupInvite
from app.models.user import User
from app.utils.password_reset import COACH_LINK_SECONDS, make_reset_token
from tests import stats_data


def make_user(team, username, role='player', superadmin=False, email=None):
    user = User(username=username, email=email, role=role, is_superadmin=superadmin,
                team_organization_id=team.id if team else None)
    user.set_password('old-password')
    db.session.add(user)
    db.session.commit()
    return user.id


class Anon:
    """A logged-out visitor; each request in its own app context."""

    def __init__(self, app):
        self.app = app
        self.client = app.test_client()

    def get(self, url, **kw):
        with self.app.app_context():
            return self.client.get(url, **kw)

    def post(self, url, **kw):
        with self.app.app_context():
            return self.client.post(url, **kw)


def login(app, user_id):
    with app.app_context():
        team_id = db.session.get(User, user_id).team_organization_id
    return stats_data.Client(app, user_id, team_id)


def user(username):
    return User.query.filter_by(username=username).first()


@pytest.fixture
def teams(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Brighton Biscuits', 'biscuits')
    players = stats_data.build_players(herd, 2)
    ids = {
        'herd': herd.id, 'other': other.id, 'player_row': players[0].id,
        'super': make_user(herd, 'site-owner', role='admin', superadmin=True),
        'team_admin': make_user(herd, 'herd-admin', role='admin'),
        'coach': make_user(herd, 'herd-coach', role='coach'),
        'coach2': make_user(herd, 'herd-coach-2', role='coach'),
        'player': make_user(herd, 'herd-player', email='player@example.com'),
        'other_coach': make_user(other, 'biscuit-coach', role='coach'),
    }
    return ids


# ── Who may manage whom ──────────────────────────────────────

def test_coach_cannot_create_a_team_admin(app, teams):
    c = login(app, teams['coach'])
    c.post('/auth/users/add', data={'username': 'sneaky', 'role': 'admin',
                                    'team_organization_id': teams['herd'], 'player_id': 0})
    assert user('sneaky') is None
    c.post('/auth/users/add', data={'username': 'co-coach', 'role': 'coach',
                                    'team_organization_id': teams['herd'], 'player_id': 0})
    assert user('co-coach').role == 'coach'


def test_coach_cannot_promote_themselves(app, teams):
    c = login(app, teams['coach'])
    r = c.post(f"/auth/users/edit/{teams['coach']}", data={
        'username': 'herd-coach', 'role': 'admin', 'team_organization_id': teams['herd'], 'player_id': 0})
    assert r.status_code == 302
    assert user('herd-coach').role == 'coach'


@pytest.mark.parametrize('target', ['super', 'team_admin', 'coach2'])
def test_coach_cannot_touch_equal_or_higher_accounts(app, teams, target):
    c = login(app, teams['coach'])
    target_id = teams[target]
    with app.app_context():
        old_hash = db.session.get(User, target_id).password_hash

    c.post(f'/auth/users/edit/{target_id}', data={
        'username': 'renamed', 'role': 'player', 'password': 'taken-over-1',
        'confirm_password': 'taken-over-1', 'team_organization_id': teams['herd'], 'player_id': 0})
    r = c.post(f'/auth/users/{target_id}/reset-link')
    assert b'reset-password' not in r.data
    c.post(f'/auth/users/delete/{target_id}')

    with app.app_context():
        target_user = db.session.get(User, target_id)
        assert target_user is not None
        assert target_user.username != 'renamed'
        assert target_user.password_hash == old_hash


def test_team_admin_manages_coaches_but_not_superadmin(app, teams):
    c = login(app, teams['team_admin'])
    c.post(f"/auth/users/edit/{teams['coach']}", data={
        'username': 'herd-coach', 'role': 'captain', 'team_organization_id': teams['herd'], 'player_id': 0})
    assert user('herd-coach').role == 'captain'

    c.post(f"/auth/users/delete/{teams['super']}")
    assert user('site-owner') is not None


def test_coach_cannot_manage_another_teams_users(app, teams):
    c = login(app, teams['other_coach'])
    c.post(f"/auth/users/delete/{teams['player']}")
    assert user('herd-player') is not None
    # Asking for another team's list shows your own team instead
    page = c.get(f"/auth/users?team_id={teams['herd']}").get_data(as_text=True)
    assert 'biscuit-coach' in page and 'herd-player' not in page


def test_users_page_hides_actions_on_protected_accounts(app, teams):
    page = login(app, teams['coach']).get('/auth/users').get_data(as_text=True)
    assert f"/auth/users/edit/{teams['player']}" in page
    for protected in ('super', 'team_admin', 'coach2'):
        assert f"/auth/users/edit/{teams[protected]}" not in page


def test_site_backups_are_superadmin_only(app, teams):
    assert login(app, teams['team_admin']).get('/admin/enhanced-data-management').status_code == 302
    assert login(app, teams['team_admin']).get('/admin/export-json-zip').status_code == 302
    assert login(app, teams['super']).get('/admin/enhanced-data-management').status_code == 200


def test_deleting_a_coach_keeps_their_team_records(app, teams):
    with app.app_context():
        db.session.add(InviteToken.create(teams['player_row'], teams['herd'], teams['coach']))
        db.session.add(PlayerFeedback(player_id=teams['player_row'], coach_id=teams['coach'],
                                      content='Great hucks'))
        db.session.commit()

    login(app, teams['team_admin']).post(f"/auth/users/delete/{teams['coach']}")

    assert user('herd-coach') is None
    assert InviteToken.query.one().created_by_id is None
    assert PlayerFeedback.query.one().coach_id == teams['team_admin']


# ── Team join link ───────────────────────────────────────────

def join_code(team_id):
    return db.session.get(TeamOrganization, team_id).join_code


def test_players_join_with_the_team_link(app, teams):
    coach = login(app, teams['coach'])
    coach.post('/auth/join-link', data={'action': 'enable'})
    code = join_code(teams['herd'])
    assert code and code in coach.get('/auth/users').get_data(as_text=True)

    visitor = Anon(app)
    r = visitor.post('/auth/join', data={'code': code.lower()})
    assert r.headers['Location'].endswith(f'/auth/join/{code}')
    r = visitor.post(f'/auth/join/{code}', data={
        'username': 'new-player', 'email': '', 'password': 'long-enough',
        'confirm_password': 'long-enough'})
    assert r.status_code == 302
    new = user('new-player')
    assert (new.team_organization_id, new.role, new.email) == (teams['herd'], 'player', None)


def test_join_link_can_be_switched_off_and_replaced(app, teams):
    coach = login(app, teams['coach'])
    coach.post('/auth/join-link', data={'action': 'enable'})
    old_code = join_code(teams['herd'])
    coach.post('/auth/join-link', data={'action': 'regenerate'})
    assert join_code(teams['herd']) != old_code

    visitor = Anon(app)
    assert visitor.get(f'/auth/join/{old_code}').status_code == 302
    coach.post('/auth/join-link', data={'action': 'disable'})
    visitor.post(f"/auth/join/{join_code(teams['herd'])}", data={
        'username': 'late', 'password': 'long-enough', 'confirm_password': 'long-enough'})
    assert user('late') is None


def test_players_cannot_manage_the_join_link(app, teams):
    login(app, teams['player']).post('/auth/join-link', data={'action': 'enable'})
    assert not db.session.get(TeamOrganization, teams['herd']).join_enabled


# ── Team sign-up ─────────────────────────────────────────────

TEAM_FORM = {'team_name': 'Lisbon Discos', 'username': 'lisbon-admin', 'email': '',
             'password': 'long-enough', 'confirm_password': 'long-enough'}


def test_team_signup_is_invite_only_by_default(app, teams):
    visitor = Anon(app)
    assert 'by invitation' in visitor.get('/auth/register-team').get_data(as_text=True)
    visitor.post('/auth/register-team', data=TEAM_FORM)
    assert TeamOrganization.query.filter_by(name='Lisbon Discos').first() is None


def test_team_signs_up_with_a_link_once(app, teams):
    owner = login(app, teams['super'])
    owner.post('/teams/signups/links', data={'note': 'Lisbon', 'days': 14})
    invite = TeamSignupInvite.query.one()

    visitor = Anon(app)
    r = visitor.post('/auth/register-team', data={**TEAM_FORM, 'invite': invite.token})
    assert r.status_code == 302
    team = TeamOrganization.query.filter_by(name='Lisbon Discos').one()
    founder = user('lisbon-admin')
    assert (founder.team_organization_id, founder.role, founder.is_superadmin) == (team.id, 'admin', False)
    db.session.refresh(invite)
    assert invite.status == 'used' and invite.team_organization_id == team.id

    again = Anon(app)
    again.post('/auth/register-team', data={**TEAM_FORM, 'team_name': 'Second Try',
                                            'username': 'second', 'invite': invite.token})
    assert TeamOrganization.query.filter_by(name='Second Try').first() is None


def test_revoked_link_stops_working(app, teams):
    owner = login(app, teams['super'])
    owner.post('/teams/signups/links', data={'days': 7})
    invite = TeamSignupInvite.query.one()
    owner.post(f'/teams/signups/links/{invite.id}/revoke')
    Anon(app).post('/auth/register-team', data={**TEAM_FORM, 'invite': invite.token})
    assert TeamOrganization.query.filter_by(name='Lisbon Discos').first() is None


def test_superadmin_can_open_team_signup(app, teams):
    login(app, teams['super']).post('/teams/signups/open', data={'open': '1'})
    Anon(app).post('/auth/register-team', data=TEAM_FORM)
    assert TeamOrganization.query.filter_by(name='Lisbon Discos').one()


def test_only_superadmin_controls_team_signup(app, teams):
    admin = login(app, teams['team_admin'])
    admin.post('/teams/signups/open', data={'open': '1'})
    admin.post('/teams/signups/links', data={'days': 7})
    assert SiteSettings.get().open_team_registration is False
    assert TeamSignupInvite.query.count() == 0


def test_old_register_page_creates_no_teamless_accounts(app, teams):
    visitor = Anon(app)
    assert visitor.get('/auth/register').status_code == 200
    visitor.post('/auth/register', data={'username': 'drifter', 'email': 'd@example.com',
                                         'password': 'x', 'password2': 'x'})
    assert user('drifter') is None


# ── Passwords ────────────────────────────────────────────────

def test_coach_reset_link_works_once(app, teams):
    page = login(app, teams['coach']).post(f"/auth/users/{teams['player']}/reset-link").get_data(as_text=True)
    path = re.search(r'/auth/reset-password/[\w.-]+', page).group(0)

    visitor = Anon(app)
    visitor.post(path, data={'password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'})
    assert user('herd-player').check_password('brand-new-pw')

    r = Anon(app).post(path, data={'password': 'second-use-pw', 'confirm_password': 'second-use-pw'})
    assert r.headers['Location'].endswith('/auth/forgot-password')
    assert user('herd-player').check_password('brand-new-pw')


def test_reset_token_cannot_be_forged_or_outlive_its_lifetime(app, teams):
    from itsdangerous import URLSafeTimedSerializer
    from app.utils.password_reset import user_for_reset_token
    player = db.session.get(User, teams['player'])
    assert user_for_reset_token('nonsense') is None
    forged = URLSafeTimedSerializer('wrong-key', salt='password-reset').dumps({'u': player.id})
    assert user_for_reset_token(forged) is None
    assert user_for_reset_token(make_reset_token(player, COACH_LINK_SECONDS)) == player
    assert user_for_reset_token(make_reset_token(player, valid_for=-1)) is None


def test_forgot_password_emails_a_link_when_email_is_set_up(app, teams):
    app.config.update(MAIL_SERVER='smtp.example.com', MAIL_DEFAULT_SENDER='coach@example.com')
    visitor = Anon(app)
    assert b'Email me a reset link' in visitor.get('/auth/forgot-password').data
    visitor.post('/auth/forgot-password', data={'identifier': 'player@example.com'})
    visitor.post('/auth/forgot-password', data={'identifier': 'nobody'})

    sent = app.extensions.get('sent_emails', [])
    assert [m['To'] for m in sent] == ['player@example.com']
    assert '/auth/reset-password/' in sent[0].get_content()


def test_forgot_password_without_email_points_to_the_coach(app, teams):
    page = Anon(app).get('/auth/forgot-password').get_data(as_text=True)
    assert 'Ask your coach' in page and 'identifier' not in page


def test_changing_password_needs_the_current_one(app, teams):
    c = login(app, teams['player'])
    c.post('/auth/account', data={'action': 'password', 'current_password': 'wrong',
                                  'password': 'new-password', 'confirm_password': 'new-password'})
    assert user('herd-player').check_password('old-password')
    c.post('/auth/account', data={'action': 'password', 'current_password': 'old-password',
                                  'password': 'new-password', 'confirm_password': 'new-password'})
    assert user('herd-player').check_password('new-password')



def test_changing_password_signs_out_other_devices(app, teams):
    phone = login(app, teams['player'])
    laptop = login(app, teams['player'])
    assert laptop.get('/auth/account').status_code == 200
    phone.post('/auth/account', data={'action': 'password', 'current_password': 'old-password',
                                      'password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'})
    assert phone.get('/auth/account').status_code == 200  # the device that changed it stays in
    assert laptop.get('/auth/account').status_code == 302  # back to the login page


def test_coach_reset_link_signs_the_player_out(app, teams):
    from app.utils.password_reset import make_reset_token
    player = login(app, teams['player'])
    with app.test_request_context():
        token = make_reset_token(db.session.get(User, teams['player']))
    Anon(app).post(f'/auth/reset-password/{token}',
                   data={'password': 'second-use-pw', 'confirm_password': 'second-use-pw'})
    assert user('herd-player').check_password('second-use-pw')
    assert player.get('/auth/account').status_code == 302


def test_old_style_login_cookies_are_ignored(app, teams):
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(teams['player'])  # plain id, no password fingerprint
    assert client.get('/auth/account').status_code == 302


@pytest.mark.parametrize('weak', ['password123', 'Ultimate1', 'aaaaaaaa', 'abababab'])
def test_common_passwords_are_refused(app, teams, weak):
    c = login(app, teams['player'])
    c.post('/auth/account', data={'action': 'password', 'current_password': 'old-password',
                                  'password': weak, 'confirm_password': weak})
    assert user('herd-player').check_password('old-password')

# ── Rate limits ──────────────────────────────────────────────

@pytest.fixture
def rate_limited(app):
    app.config['RATELIMIT_ENABLED'] = True
    limiter.init_app(app)
    limiter.reset()
    yield app
    limiter.reset()


def test_login_is_rate_limited(rate_limited, teams):
    visitor = Anon(rate_limited)
    codes = [visitor.post('/auth/login', data={'username': 'herd-player', 'password': 'guess'}).status_code
             for _ in range(11)]
    assert codes[:10] == [302] * 10
    assert codes[10] == 429


def test_logout_needs_a_post(app, teams):
    c = login(app, teams['player'])
    c.get('/auth/logout')  # e.g. an <img> on another site
    assert c.get('/auth/account').status_code == 200
    app.config['WTF_CSRF_ENABLED'] = True  # works from a page whose token has expired
    c.post('/auth/logout')
    app.config['WTF_CSRF_ENABLED'] = False
    assert c.get('/auth/account').status_code == 302
