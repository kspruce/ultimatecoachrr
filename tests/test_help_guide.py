"""The How to Use guide, the About tour and the help around the site: one
description of each feature (app/help_guide.py), shown to each reader for
their role and their team's features, plus the one getting-started email."""
from datetime import datetime, timedelta

import pytest

from app import db, help_guide, onboarding
from app.models.onboarding import UserOnboarding
from app.models.team_settings import TeamSettings
from app.models.user import User
from tests import stats_data
from tests.test_onboarding import login, make_user

ROLES = ['super', 'team_admin', 'captain', 'coach', 'stat_taker', 'player', 'guest']


@pytest.fixture
def club(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    db.session.add(TeamSettings(team_id=herd.id))
    db.session.commit()
    ids = {
        'herd': herd.id,
        'super': make_user(herd, 'site-owner', role='admin', superadmin=True, welcomed=True),
        'team_admin': make_user(herd, 'herd-admin', role='admin', welcomed=True),
        'captain': make_user(herd, 'herd-captain', role='captain', welcomed=True),
        'coach': make_user(herd, 'herd-coach', role='coach', welcomed=True),
        'stat_taker': make_user(herd, 'herd-stats', role='stat_taker', welcomed=True),
        'player': make_user(herd, 'herd-player', welcomed=True),
        'guest': make_user(herd, 'herd-guest', role='guest', welcomed=True),
    }
    return ids


def set_flags(team_id, on):
    settings = TeamSettings.query.filter_by(team_id=team_id).one()
    for flag in help_guide.FLAGS:
        setattr(settings, flag, on)
    db.session.commit()


# ── The registry points at real pages ────────────────────────

def test_every_feature_links_to_a_real_page(app):
    endpoints = set(app.view_functions)
    for feature in help_guide.FEATURES:
        assert feature.endpoint in endpoints, feature.key
        if feature.coach_endpoint:
            assert feature.coach_endpoint in endpoints, feature.key
        for prefix in feature.pages:
            assert any(e.startswith(prefix) for e in endpoints), (feature.key, prefix)
        assert feature.section in {s['key'] for s in help_guide.SECTIONS}
    assert set(help_guide.BY_FLAG) == set(help_guide.FLAGS) == set(help_guide.FLAG_LABELS)
    for preset in help_guide.PRESETS:
        assert set(preset['flags']) <= set(help_guide.FLAGS)


def test_each_page_finds_its_help(app):
    find = lambda e: getattr(help_guide.feature_for_endpoint(e), 'key', None)
    assert find('session.drills') == 'drills'
    assert find('session.drill_detail') == 'drills'
    assert find('session.index') == 'sessions'
    assert find('training.availability') == 'sessions'
    assert find('stats_dashboard.index') == 'stats'
    assert find('playbook.position_view') == 'playbook'
    assert find('main.index') is None and find(None) is None


# ── The guide, for each reader ───────────────────────────────

@pytest.mark.parametrize('on', [True, False])
def test_guide_renders_for_every_role(app, club, on):
    set_flags(club['herd'], on)
    for role in ROLES:
        page = login(app, club[role]).get('/how-to-use')
        assert page.status_code == 200, role
        html = page.get_data(as_text=True)
        assert 'id="make-it-yours"' in html and 'Team Roster' in html
    anon = app.test_client().get('/how-to-use').get_data(as_text=True)
    assert 'Get your team started' in anon and 'Coaches can also' in anon


def test_coaches_see_what_they_could_turn_on(app, club):
    settings = TeamSettings.query.filter_by(team_id=club['herd']).one()
    settings.clip_enabled = False
    db.session.commit()

    coach = login(app, club['coach']).get('/how-to-use').get_data(as_text=True)
    assert 'Clip Library' in coach and 'Off for Thundering Herd' in coach
    assert '/team/settings/features#row-clip_enabled' in coach
    # The season plan starts off, so it's offered too
    assert '#row-season_plan_enabled' in coach

    player = login(app, club['player']).get('/how-to-use').get_data(as_text=True)
    assert 'Clip Library' not in player and 'Off for' not in player
    assert 'Seasons &amp; Squads' not in player and 'Live Game Day Tracker' not in player
    assert 'Ask the team to learn a play' not in player  # coach-only steps stay hidden
    assert 'ask them to turn it on' in player


def test_guide_starts_from_the_readers_role_and_checklist(app, club):
    coach = login(app, club['coach']).get('/how-to-use').get_data(as_text=True)
    assert "You're a coach on Thundering Herd" in coach
    assert 'Your getting-started checklist' in coach and '/welcome/' in coach
    assert 'Create the team' not in coach  # the old superadmin-only step

    admin = login(app, club['team_admin']).get('/how-to-use').get_data(as_text=True)
    assert 'Switch Team. The team badge' not in admin
    owner = login(app, club['super']).get('/how-to-use').get_data(as_text=True)
    assert 'Switch Team. The team badge' in owner

    guest = login(app, club['guest']).get('/how-to-use').get_data(as_text=True)
    assert 'read-only demo' in guest


def test_make_it_yours(app, club):
    coach = login(app, club['coach']).get('/how-to-use').get_data(as_text=True)
    for url in ('/team/settings/features', '/team/settings/colours', '/sessions/settings'):
        assert url in coach
    assert 'For your team' in coach and 'Dark mode' in coach

    player = login(app, club['player']).get('/how-to-use').get_data(as_text=True)
    assert 'For your team' not in player and '/team/settings/colours' not in player
    assert 'Calendar on your phone' in player and '/account' in player


# ── Around the site ──────────────────────────────────────────

def test_help_link_opens_the_pages_card(app, club):
    coach = login(app, club['coach'])
    assert 'how-to-use#playbook' in coach.get('/playbook/').get_data(as_text=True)
    assert 'how-to-use#drills' in coach.get('/sessions/drills').get_data(as_text=True)
    home = app.test_client().get('/').get_data(as_text=True)
    assert '/about' in home and '/how-to-use' in home


def test_about_is_a_public_tour(app):
    page = app.test_client().get('/about')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for feature in help_guide.FEATURES:
        assert f'/how-to-use#{feature.key}' in html
    assert 'Get your team started' in html and 'Make it yours' in html


def test_feature_settings_explain_each_switch(app, club):
    coach = login(app, club['coach'])
    html = coach.get('/team/settings/features').get_data(as_text=True)
    assert 'Start from a preset' in html and 'Training team' in html
    assert 'id="row-clip_enabled"' in html and '/how-to-use#clips' in html

    coach.post('/team/settings/features', data={'stats_enabled': 'on', 'gameday_enabled': 'on'})
    settings = TeamSettings.query.filter_by(team_id=club['herd']).one()
    db.session.refresh(settings)
    assert settings.stats_enabled and settings.gameday_enabled
    assert not settings.playbook_enabled and not settings.season_plan_enabled


def test_checklist_links_to_the_guide(app, club):
    html = login(app, club['coach']).get('/welcome/').get_data(as_text=True)
    assert 'How it works' in html and '/how-to-use#sessions' in html


# ── The one getting-started email ───────────────────────────

def test_new_users_get_one_reminder(app, club):
    app.config.update(MAIL_SERVER='smtp.example.com', MAIL_DEFAULT_SENDER='coach@example.com',
                      BASE_URL='https://coach.example.com')
    from app.models.team_organization import TeamOrganization
    herd = db.session.get(TeamOrganization, club['herd'])
    now = datetime.utcnow()

    def new_user(name, days_old, **kw):
        user_id = make_user(herd, name, email=f'{name}@example.com', **kw)
        db.session.get(User, user_id).created_at = now - timedelta(days=days_old)
        db.session.commit()
        return user_id

    fresh = new_user('fresh', 5)
    new_user('too-new', 1)
    new_user('old-hand', 60)
    hidden = new_user('hid-it', 5)
    db.session.add(UserOnboarding(user_id=hidden, dismissed_at=now, completed_steps=[]))
    quiet = new_user('quiet', 5)
    db.session.get(User, quiet).email_event_updates = False
    db.session.commit()

    assert onboarding.send_nudges(now) == 1
    sent = app.extensions['sent_emails']
    assert [m['To'] for m in sent] == ['fresh@example.com']
    body = sent[0].get_content()
    assert 'Pick your name from the roster' in body
    assert 'https://coach.example.com/welcome' in body and 'https://coach.example.com/how-to-use' in body
    assert db.session.get(UserOnboarding, UserOnboarding.query.filter_by(user_id=fresh).one().id).nudged_at

    assert onboarding.send_nudges(now) == 0  # only ever once


def test_no_reminders_without_email(app, club):
    assert onboarding.send_nudges() == 0
