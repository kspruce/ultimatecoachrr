"""Roles and the getting-started guide: captains run their own team (and only
their own team), and every role gets a welcome and a checklist that ticks
itself off from real data."""
import pytest

from app import db, onboarding
from app.models.onboarding import UserOnboarding
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from app.models.user import User
from tests import stats_data


def make_user(team, username, role='player', superadmin=False, email=None, welcomed=False):
    user = User(username=username, email=email, role=role, is_superadmin=superadmin,
                team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    if welcomed:
        db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    db.session.commit()
    return user.id


def login(app, user_id):
    with app.app_context():
        team_id = db.session.get(User, user_id).team_organization_id
    return stats_data.Client(app, user_id, team_id)


def get_user(user_id):
    return db.session.get(User, user_id)


@pytest.fixture
def teams(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Brighton Biscuits', 'biscuits')
    for team in (herd, other):
        db.session.add(TeamSettings(team_id=team.id))
    db.session.commit()
    return {
        'herd': herd.id, 'other': other.id,
        'super': make_user(herd, 'site-owner', role='admin', superadmin=True, welcomed=True),
        'team_admin': make_user(herd, 'herd-admin', role='admin', welcomed=True),
        'captain': make_user(herd, 'herd-captain', role='captain', welcomed=True),
        'coach': make_user(herd, 'herd-coach', role='coach', welcomed=True),
        'player': make_user(herd, 'herd-player', welcomed=True),
        'other_player': make_user(other, 'biscuit-player', welcomed=True),
    }


# ── Captains run their own team ──────────────────────────────

def test_captain_has_team_admin_powers(app, teams):
    captain = get_user(teams['captain'])
    assert captain.is_admin and captain.is_coach and captain.is_stat_taker
    assert not captain.is_superadmin

    c = login(app, teams['captain'])
    # Admin-only pages on their own team
    assert c.get('/fitness/test-day').status_code == 200
    assert c.get('/playbook/plays/add').status_code == 200
    assert c.get(f"/teams/edit/{teams['herd']}").status_code == 200


def test_captain_cannot_reach_other_teams(app, teams):
    c = login(app, teams['captain'])
    r = c.get(f"/teams/edit/{teams['other']}")
    assert r.status_code == 302
    c.post(f"/auth/users/delete/{teams['other_player']}")
    assert get_user(teams['other_player']) is not None
    # Switching team is superadmin only
    c.get(f"/teams/switch/{teams['other']}")
    page = c.get(f"/auth/users?team_id={teams['other']}").get_data(as_text=True)
    assert 'herd-player' in page and 'biscuit-player' not in page
    # Site-wide tools stay superadmin only
    assert c.get('/teams/signups').status_code == 302
    assert c.get('/admin/enhanced-data-management').status_code == 302


def test_captain_manages_coaches_and_players_but_not_team_admin(app, teams):
    c = login(app, teams['captain'])
    c.post(f"/auth/users/edit/{teams['coach']}", data={
        'username': 'herd-coach', 'role': 'captain', 'team_organization_id': teams['herd'],
        'player_id': 0})
    assert get_user(teams['coach']).role == 'captain'

    c.post(f"/auth/users/delete/{teams['player']}")
    assert get_user(teams['player']) is None

    c.post(f"/auth/users/delete/{teams['team_admin']}")
    c.post(f"/auth/users/delete/{teams['super']}")
    assert get_user(teams['team_admin']) is not None
    assert get_user(teams['super']) is not None


def test_coach_cannot_make_a_captain(app, teams):
    c = login(app, teams['coach'])
    c.post(f"/auth/users/edit/{teams['player']}", data={
        'username': 'herd-player', 'role': 'captain', 'team_organization_id': teams['herd'],
        'player_id': 0})
    assert get_user(teams['player']).role == 'player'
    c.post(f"/auth/users/edit/{teams['captain']}", data={
        'username': 'herd-captain', 'role': 'player', 'team_organization_id': teams['herd'],
        'player_id': 0})
    assert get_user(teams['captain']).role == 'captain'


def test_superadmin_manages_every_team(app, teams):
    c = login(app, teams['super'])
    assert c.get(f"/teams/edit/{teams['other']}").status_code == 200
    c.post(f"/auth/users/delete/{teams['other_player']}")
    assert get_user(teams['other_player']) is None


# ── Checklists ───────────────────────────────────────────────

def keys(user_id, team_id):
    return [s.key for s in onboarding.steps_for(get_user(user_id),
                                                 db.session.get(TeamOrganization, team_id))]


def test_each_role_gets_its_own_checklist(app, teams):
    herd = teams['herd']
    assert keys(teams['team_admin'], herd)[0] == 'roster_imported'
    assert 'profile_linked' not in keys(teams['team_admin'], herd)
    captain = keys(teams['captain'], herd)
    assert {'profile_linked', 'staff_added', 'players_invited', 'gameday_tour'} <= set(captain)
    assert keys(teams['coach'], herd)[:2] == ['roster_reviewed', 'first_session']
    assert keys(teams['player'], herd)[:3] == ['profile_linked', 'email_added', 'rsvp_given']
    # Admins can always set up Discord (a webhook needs nothing from the site);
    # players only get "link your Discord" once the site's bot is set up
    assert 'discord' in captain and 'discord_linked' not in keys(teams['player'], herd)

    guest = make_user(db.session.get(TeamOrganization, herd), 'guesty', role='guest')
    assert keys(guest, herd) == []


def test_steps_for_switched_off_features_are_hidden(app, teams):
    settings = TeamSettings.query.filter_by(team_id=teams['herd']).one()
    settings.sessions_enabled = False
    settings.gameday_enabled = False
    db.session.commit()
    coach = keys(teams['coach'], teams['herd'])
    assert 'first_session' not in coach and 'gameday_tour' not in coach


@pytest.fixture
def request_ctx(app):
    # progress() builds step links with url_for
    with app.test_request_context():
        yield


def test_steps_tick_themselves_off(app, teams, request_ctx):
    team = db.session.get(TeamOrganization, teams['herd'])

    def done(user_id):
        return {i['step'].key for i in onboarding.progress(get_user(user_id), team)['items']
                if i['done']}

    assert 'roster_imported' not in done(teams['team_admin'])
    # The captain and coach count as staff for the team admin
    assert 'staff_added' in done(teams['team_admin'])
    players = stats_data.build_players(team, 2)
    assert 'roster_imported' in done(teams['team_admin'])

    player = get_user(teams['player'])
    progress = onboarding.progress(player, team)
    rsvp = next(i for i in progress['items'] if i['step'].key == 'rsvp_given')
    assert rsvp['blocked'] and rsvp['url'] is None

    players[0].user_id = player.id
    player.email = 'me@example.com'
    db.session.commit()
    assert {'profile_linked', 'email_added'} <= done(teams['player'])


def test_placeholder_email_does_not_count(app, teams, request_ctx):
    player = get_user(teams['player'])
    player.email = 'herd-player@no-email.placeholder'
    db.session.commit()
    team = db.session.get(TeamOrganization, teams['herd'])
    items = onboarding.progress(player, team)['items']
    assert not next(i for i in items if i['step'].key == 'email_added')['done']


# ── Welcome page and dashboard ───────────────────────────────

def test_new_user_is_welcomed_once(app, teams):
    team = db.session.get(TeamOrganization, teams['herd'])
    new_id = make_user(team, 'rookie')
    c = login(app, new_id)

    r = c.get('/')
    assert r.status_code == 302 and r.headers['Location'].endswith('/welcome/')
    page = c.get('/welcome/').get_data(as_text=True)
    assert 'Welcome to Thundering Herd' in page and 'Pick your name from the roster' in page

    page = c.get('/').get_data(as_text=True)
    assert 'Getting started as player' in page


def test_deep_links_are_not_hijacked(app, teams):
    team = db.session.get(TeamOrganization, teams['herd'])
    c = login(app, make_user(team, 'rookie'))
    assert c.get('/calendar').status_code == 200


@pytest.mark.parametrize('role', ['admin', 'captain', 'coach', 'stat_taker', 'player'])
def test_welcome_page_renders_for_every_role(app, teams, role):
    team = db.session.get(TeamOrganization, teams['herd'])
    c = login(app, make_user(team, f'new-{role}', role=role))
    page = c.get('/welcome/')
    assert page.status_code == 200
    assert onboarding.ROLES[role]['name'] in page.get_data(as_text=True)


def test_guests_are_not_onboarded(app, teams):
    team = db.session.get(TeamOrganization, teams['herd'])
    c = login(app, make_user(team, 'guesty', role='guest'))
    assert c.get('/').status_code == 200
    assert c.get('/welcome/').status_code == 302


def test_promotion_shows_the_new_welcome_but_demotion_does_not(app, teams):
    assert not onboarding.needs_welcome(get_user(teams['player']))

    admin = login(app, teams['team_admin'])
    admin.post(f"/auth/users/edit/{teams['player']}", data={
        'username': 'herd-player', 'role': 'captain', 'team_organization_id': teams['herd'],
        'player_id': 0})
    assert 'welcome to their new role' in admin.get('/auth/users').get_data(as_text=True)

    c = login(app, teams['player'])
    assert c.get('/').headers['Location'].endswith('/welcome/')
    assert 'As captain you run the team' in c.get('/welcome/').get_data(as_text=True)
    assert c.get('/').status_code == 200

    admin.post(f"/auth/users/edit/{teams['player']}", data={
        'username': 'herd-player', 'role': 'player', 'team_organization_id': teams['herd'],
        'player_id': 0})
    assert c.get('/').status_code == 200


def test_existing_users_keep_a_quiet_dashboard(app, teams):
    record = UserOnboarding.query.filter_by(user_id=teams['coach']).one()
    record.dismissed_at = db.func.now()
    db.session.commit()
    page = login(app, teams['coach']).get('/').get_data(as_text=True)
    assert 'Getting started as coach' not in page
    assert '/welcome/' in page  # still in the user menu


def test_checklist_can_be_hidden_and_brought_back(app, teams):
    c = login(app, teams['coach'])
    assert 'Getting started as coach' in c.get('/').get_data(as_text=True)
    c.post('/welcome/dismiss')
    assert 'Getting started as coach' not in c.get('/').get_data(as_text=True)
    c.post('/welcome/restore')
    assert 'Getting started as coach' in c.get('/').get_data(as_text=True)


def test_opening_a_look_around_step_ticks_it_off(app, teams):
    c = login(app, teams['coach'])
    r = c.get('/welcome/go/roster_reviewed')
    assert r.status_code == 302 and r.headers['Location'].endswith('/team/')
    assert UserOnboarding.query.filter_by(user_id=teams['coach']).one().has_completed('roster_reviewed')

    # Steps from another role's list aren't open to you
    assert c.get('/welcome/go/stats_viewed').status_code == 404


def test_player_steps_wait_for_a_linked_profile(app, teams):
    c = login(app, teams['player'])
    r = c.get('/welcome/go/stats_viewed')
    assert r.headers['Location'].endswith('/auth/link_player')
    assert not UserOnboarding.query.filter_by(user_id=teams['player']).one().has_completed('stats_viewed')


# ── Team sign-up progress ────────────────────────────────────

def test_coaches_see_who_has_not_joined(app, teams):
    team = db.session.get(TeamOrganization, teams['herd'])
    players = stats_data.build_players(team, 3)
    players[0].user_id = teams['player']
    db.session.commit()

    c = login(app, teams['coach'])
    dashboard = c.get('/').get_data(as_text=True)
    assert "joined yet" in dashboard and players[1].name in dashboard

    users_page = c.get('/auth/users').get_data(as_text=True)
    assert '1 of 3 active players have an account' in users_page
    assert players[2].name in users_page

    # Players don't get the team tile
    assert "joined yet" not in login(app, teams['player']).get('/').get_data(as_text=True)


def test_deleting_a_user_removes_their_onboarding(app, teams):
    login(app, teams['team_admin']).post(f"/auth/users/delete/{teams['coach']}")
    assert get_user(teams['coach']) is None
    assert UserOnboarding.query.filter_by(user_id=teams['coach']).first() is None
