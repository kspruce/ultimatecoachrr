"""One login on several teams: joining another team, switching between
teams, a role and a player per team, and who may change a shared login."""
import pytest

from app import db
from app.models.invite_token import InviteToken
from app.models.player import Player
from app.models.team_membership import TeamMembership
from app.models.team_organization import TeamOrganization
from app.models.user import User
from tests import stats_data
from tests.test_accounts import login, make_user


def get_user(user_id):
    db.session.expire_all()  # see what the requests saved
    return db.session.get(User, user_id)


def team_roles(user_id):
    return {m.team_organization_id: m.role for m in get_user(user_id).memberships}


@pytest.fixture
def clubs(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Brighton Biscuits', 'biscuits')
    other.join_code, other.join_enabled = 'BISC2345', True
    herd_players = stats_data.build_players(herd, 2)
    other_players = stats_data.build_players(other, 2)
    db.session.commit()
    return {
        'herd': herd.id, 'other': other.id,
        'herd_player_row': herd_players[0].id, 'other_player_row': other_players[0].id,
        'super': make_user(herd, 'site-owner', role='admin', superadmin=True),
        'herd_coach': make_user(herd, 'herd-coach', role='coach'),
        'other_coach': make_user(other, 'biscuit-coach', role='coach'),
        'other_admin': make_user(other, 'biscuit-admin', role='admin'),
        'alex': make_user(herd, 'alex', email='alex@example.com'),
    }


def join_other(app, clubs, user_id):
    c = login(app, user_id)
    c.post('/auth/join/BISC2345')
    return c


# ── Joining another team ─────────────────────────────────────

def test_every_account_is_a_member_of_its_team(app, clubs):
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player'}
    assert team_roles(clubs['herd_coach']) == {clubs['herd']: 'coach'}


def test_logged_in_player_adds_a_team_after_confirming(app, clubs):
    c = login(app, clubs['alex'])
    page = c.get('/auth/join/BISC2345')
    assert page.status_code == 200 and 'Join Brighton Biscuits' in page.get_data(as_text=True)
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player'}  # a GET adds nothing

    c.post('/auth/join/BISC2345')
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player', clubs['other']: 'player'}
    alex = get_user(clubs['alex'])
    assert alex.team_organization_id == clubs['herd']  # home team unchanged
    assert alex.email == 'alex@example.com'
    assert User.query.filter_by(email='alex@example.com').count() == 1


def test_signing_up_again_with_the_same_email_points_to_logging_in(app, clubs):
    page = app.test_client().post('/auth/join/BISC2345', data={
        'username': 'alex-again', 'email': 'alex@example.com',
        'password': 'a long passphrase', 'confirm_password': 'a long passphrase'},
        follow_redirects=True)
    text = page.get_data(as_text=True)
    assert 'already registered' in text and 'log in' in text
    assert User.query.filter_by(username='alex-again').first() is None
    assert '/auth/login?next=' in text


def test_switching_teams(app, clubs):
    c = join_other(app, clubs, clubs['alex'])
    # Joining switches to the new team
    assert 'Brighton Biscuits' in c.get('/auth/profile').get_data(as_text=True)
    c.get(f"/teams/switch/{clubs['herd']}")
    with c.client.session_transaction() as s:
        assert s['current_team_id'] == clubs['herd']
    menu = c.get('/auth/profile').get_data(as_text=True)
    assert 'Switch Team' in menu and f"/teams/switch/{clubs['other']}" in menu


def test_cannot_switch_to_a_team_youre_not_on(app, clubs):
    c = login(app, clubs['alex'])
    c.get(f"/teams/switch/{clubs['other']}")
    with c.client.session_transaction() as s:
        assert s['current_team_id'] == clubs['herd']
    assert f"/teams/switch/{clubs['other']}" not in c.get('/auth/profile').get_data(as_text=True)


def test_one_team_shows_no_switcher(app, clubs):
    assert 'Switch Team' not in login(app, clubs['alex']).get('/auth/profile').get_data(as_text=True)


def test_a_team_theyre_not_on_in_the_session_falls_back_to_home(app, clubs):
    c = stats_data.Client(app, clubs['alex'], clubs['other'])
    text = c.get('/auth/profile').get_data(as_text=True)
    assert 'Thundering Herd' in text and 'Brighton Biscuits' not in text


# ── A role and a player per team ─────────────────────────────

def test_role_is_per_team(app, clubs):
    # A coach on the Herd who also plays for the Biscuits
    join_other(app, clubs, clubs['herd_coach'])
    assert team_roles(clubs['herd_coach']) == {clubs['herd']: 'coach', clubs['other']: 'player'}

    on_herd = stats_data.Client(app, clubs['herd_coach'], clubs['herd'])
    assert on_herd.get('/auth/users').status_code == 200

    on_other = stats_data.Client(app, clubs['herd_coach'], clubs['other'])
    assert on_other.get('/auth/users').status_code == 302  # sent away


def test_player_profile_is_per_team(app, clubs):
    c = join_other(app, clubs, clubs['alex'])
    herd_row, other_row = clubs['herd_player_row'], clubs['other_player_row']
    db.session.get(Player, herd_row).user_id = clubs['alex']
    db.session.commit()

    c.post('/auth/link_player', data={'player_id': other_row})  # current team: Biscuits
    alex = get_user(clubs['alex'])
    assert {p.id for p in alex.player_profiles} == {herd_row, other_row}
    assert alex.player_for(clubs['herd']).id == herd_row
    assert alex.player_for(clubs['other']).id == other_row

    with app.test_request_context():
        from flask import session
        from flask_login import login_user
        login_user(alex)
        session['current_team_id'] = clubs['other']
        assert alex.player.id == other_row


def test_cannot_link_another_teams_player(app, clubs):
    c = login(app, clubs['alex'])
    c.post('/auth/link_player', data={'player_id': clubs['other_player_row']})
    assert db.session.get(Player, clubs['other_player_row']).user_id is None


# ── Managing someone who is on several teams ─────────────────

def test_users_page_lists_members_from_other_home_teams(app, clubs):
    join_other(app, clubs, clubs['alex'])
    page = stats_data.Client(app, clubs['other_coach'], clubs['other']).get('/auth/users')
    text = page.get_data(as_text=True)
    assert 'alex' in text and 'with the same login' in text


def test_coach_changes_role_on_their_team_only(app, clubs):
    join_other(app, clubs, clubs['alex'])
    c = stats_data.Client(app, clubs['other_admin'], clubs['other'])
    c.post(f"/auth/users/edit/{clubs['alex']}", data={
        'username': 'alex', 'email': 'alex@example.com', 'role': 'coach',
        'team_organization_id': clubs['other'], 'player_id': 0})
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player', clubs['other']: 'coach'}


def test_coach_on_one_team_cannot_change_a_shared_login(app, clubs):
    join_other(app, clubs, clubs['herd_coach'])  # a Herd coach who plays for the Biscuits
    c = stats_data.Client(app, clubs['other_admin'], clubs['other'])

    c.post(f"/auth/users/edit/{clubs['herd_coach']}", data={
        'username': 'hijacked', 'email': 'attacker@example.com', 'password': 'new password 123',
        'confirm_password': 'new password 123', 'role': 'player',
        'team_organization_id': clubs['other'], 'player_id': 0})
    coach = get_user(clubs['herd_coach'])
    assert coach.username == 'herd-coach' and coach.email is None
    assert coach.check_password('old-password')
    assert team_roles(clubs['herd_coach'])[clubs['herd']] == 'coach'

    r = c.post(f"/auth/users/{clubs['herd_coach']}/reset-link")
    assert r.status_code == 302  # refused: no reset link page


def test_coach_on_one_team_cannot_change_a_shared_login_from_the_roster(app, clubs):
    join_other(app, clubs, clubs['herd_coach'])
    row = db.session.get(Player, clubs['other_player_row'])
    row.user_id = clubs['herd_coach']
    db.session.commit()
    c = stats_data.Client(app, clubs['other_admin'], clubs['other'])
    c.post(f"/team/edit_player/{clubs['other_player_row']}", data={
        'name': row.name, 'gender_match': 'female', 'active': 'y', 'create_account': 'y',
        'username': 'hijacked', 'password': 'new password 123'})
    coach = get_user(clubs['herd_coach'])
    assert coach.username == 'herd-coach' and coach.check_password('old-password')


def test_someone_running_all_their_teams_can_change_the_login(app, clubs):
    join_other(app, clubs, clubs['alex'])
    c = login(app, clubs['super'])
    c.post(f"/auth/users/edit/{clubs['alex']}", data={
        'username': 'alex', 'email': 'alex@new.example.com', 'role': 'player',
        'team_organization_id': clubs['herd'], 'player_id': 0})
    assert get_user(clubs['alex']).email == 'alex@new.example.com'


def test_removing_a_multi_team_member_keeps_their_account(app, clubs):
    join_other(app, clubs, clubs['alex'])
    row = db.session.get(Player, clubs['other_player_row'])
    row.user_id = clubs['alex']
    db.session.commit()

    stats_data.Client(app, clubs['other_coach'], clubs['other']).post(
        f"/auth/users/delete/{clubs['alex']}")
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player'}
    assert db.session.get(Player, clubs['other_player_row']).user_id is None
    assert get_user(clubs['alex']) is not None


def test_removing_someone_from_their_home_team_moves_their_home(app, clubs):
    join_other(app, clubs, clubs['alex'])
    stats_data.Client(app, clubs['herd_coach'], clubs['herd']).post(f"/auth/users/delete/{clubs['alex']}")
    alex = get_user(clubs['alex'])
    assert team_roles(clubs['alex']) == {clubs['other']: 'player'}
    assert alex.team_organization_id == clubs['other']
    # and they land on the Biscuits next time
    assert 'Brighton Biscuits' in login(app, clubs['alex']).get('/auth/profile').get_data(as_text=True)


# ── Invites ──────────────────────────────────────────────────

def test_logged_in_player_accepts_an_invite_from_another_team(app, clubs):
    invite = InviteToken.create(player_id=clubs['other_player_row'], team_id=clubs['other'],
                                created_by_id=clubs['other_coach'])
    db.session.add(invite)
    db.session.commit()
    token = invite.token

    c = login(app, clubs['alex'])
    page = c.get(f'/auth/invite/accept/{token}')
    assert 'Join Brighton Biscuits' in page.get_data(as_text=True)
    c.post(f'/auth/invite/accept/{token}')

    assert team_roles(clubs['alex']) == {clubs['herd']: 'player', clubs['other']: 'player'}
    assert db.session.get(Player, clubs['other_player_row']).user_id == clubs['alex']
    db.session.expire_all()
    assert InviteToken.query.filter_by(token=token).first().used_at is not None


def test_invite_page_offers_logging_in(app, clubs):
    invite = InviteToken.create(player_id=clubs['other_player_row'], team_id=clubs['other'],
                                created_by_id=clubs['other_coach'])
    db.session.add(invite)
    db.session.commit()
    text = app.test_client().get(f'/auth/invite/accept/{invite.token}').get_data(as_text=True)
    assert 'Log in to add Brighton Biscuits' in text


# ── Deleting a team ──────────────────────────────────────────

def test_deleting_a_team_keeps_accounts_also_on_other_teams(app, clubs):
    join_other(app, clubs, clubs['alex'])        # home: Herd, also Biscuits
    join_other(app, clubs, clubs['herd_coach'])
    from app.utils.team_data import delete_team_data
    delete_team_data(clubs['herd'])
    db.session.commit()

    alex = get_user(clubs['alex'])
    assert alex is not None and alex.team_organization_id == clubs['other']
    assert team_roles(clubs['alex']) == {clubs['other']: 'player'}
    assert db.session.get(TeamOrganization, clubs['herd']) is None
    assert get_user(clubs['other_coach']) is not None


def test_team_download_includes_members_from_other_home_teams(app, clubs):
    join_other(app, clubs, clubs['alex'])
    from app.utils.team_data import team_tables
    tables = team_tables(clubs['other'])
    assert 'alex' in {u['username'] for u in tables['user']}
    assert {m['user_id'] for m in tables['team_membership']} >= {clubs['alex']}


def test_restoring_an_old_backup_gives_everyone_their_home_membership(app, clubs):
    from app.models.team_membership import add_missing_home_memberships
    TeamMembership.query.filter_by(user_id=clubs['alex']).delete()  # as in a backup from before memberships
    db.session.commit()
    assert add_missing_home_memberships() == 1
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player'}


def test_site_backup_round_trips_memberships(app, clubs, tmp_path):
    from app.utils.enhanced_data_manager import EnhancedDataManager
    join_other(app, clubs, clubs['alex'])
    manager = EnhancedDataManager(export_dir=str(tmp_path))
    buffer, name = manager.export_all_to_json_zip(timestamp=False)
    zip_path = tmp_path / name
    zip_path.write_bytes(buffer.getvalue())

    Player.query.update({'user_id': None})
    TeamMembership.query.delete()
    User.query.delete()
    db.session.commit()

    manager.import_from_zip(str(zip_path))
    assert team_roles(clubs['alex']) == {clubs['herd']: 'player', clubs['other']: 'player'}
    assert team_roles(clubs['herd_coach']) == {clubs['herd']: 'coach'}


def test_account_page_lists_your_teams(app, clubs):
    c = join_other(app, clubs, clubs['alex'])
    text = c.get('/auth/account').get_data(as_text=True)
    assert 'Your teams' in text and 'Thundering Herd' in text and 'Brighton Biscuits' in text


def test_edit_page_locks_a_shared_login(app, clubs):
    join_other(app, clubs, clubs['herd_coach'])
    c = stats_data.Client(app, clubs['other_admin'], clubs['other'])
    text = c.get(f"/auth/users/edit/{clubs['herd_coach']}").get_data(as_text=True)
    assert 'Also on Thundering Herd' in text
    assert 'name="username"' in text and 'disabled' in text
