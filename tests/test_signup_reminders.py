"""Chasing people who haven't got going: coaches remind roster players with
no account (each gets their own invite link, the team's Discord gets who's
left), and new users with no email get their one getting-started reminder
by Discord instead."""
from datetime import date, datetime, timedelta

import pytest

from app import db, onboarding
from app.discord import notify
from app.models.invite_token import InviteToken
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from app.models.user import User
from tests import stats_data
from tests.test_discord import WEBHOOK, bot, discord_calls  # noqa: F401
from tests.test_onboarding import login, make_user


@pytest.fixture
def herd(app):
    app.config.update(MAIL_SERVER='smtp.example.com', MAIL_DEFAULT_SENDER='coach@example.com',
                      BASE_URL='https://coach.example.com')
    team = stats_data.build_team('Thundering Herd', 'herd')
    db.session.add(TeamSettings(team_id=team.id, discord_enabled=True, discord_webhook_url=WEBHOOK))
    players = stats_data.build_players(team, 3)
    players[0].email = 'ana@example.com'
    players[1].email = 'ben@example.com'
    db.session.commit()
    coach = make_user(team, 'herd-coach', role='coach', welcomed=True)
    return {'team': team.id, 'coach': coach, 'players': [p.id for p in players]}


def sent_to(app):
    return [m['To'] for m in app.extensions.get('sent_emails', [])]


def test_coach_reminds_players_who_havent_joined(app, herd, discord_calls):
    coach = login(app, herd['coach'])
    page = coach.get('/auth/users').get_data(as_text=True)
    assert 'Remind them' in page and '/auth/remind-unjoined' in page

    r = coach.post('/auth/remind-unjoined', follow_redirects=True)
    html = r.get_data(as_text=True)
    assert 'Emailed 2 players their invite link.' in html
    assert "Posted who&#39;s left to your Discord." in html
    assert 'No email for Herd Player 03' in html

    assert sorted(sent_to(app)) == ['ana@example.com', 'ben@example.com']
    body = app.extensions['sent_emails'][0].get_content()
    token = InviteToken.query.filter_by(player_id=herd['players'][0]).one()
    assert f'/auth/invite/accept/{token.token}' in body and 'herd-coach has added you' in body

    note = discord_calls[-1][2]['json']['content']
    assert '3 players still need to sign up for Thundering Herd' in note
    assert 'Herd Player 01, Herd Player 02, Herd Player 03' in note
    assert 'ask a coach' in note  # join link is off

    # Straight away again: nobody is emailed twice, Discord still hears
    html = coach.post('/auth/remind-unjoined', follow_redirects=True).get_data(as_text=True)
    assert len(sent_to(app)) == 2 and InviteToken.query.count() == 2
    assert "2 had an invite in the last few days" in html

    # A few days on, a fresh link replaces the old one
    for t in InviteToken.query.all():
        t.created_at = datetime.utcnow() - timedelta(days=4)
    db.session.commit()
    coach.post('/auth/remind-unjoined')
    assert len(sent_to(app)) == 4 and InviteToken.query.count() == 2


def test_players_cant_send_reminders(app, herd):
    team = db.session.get(TeamOrganization, herd['team'])
    player = make_user(team, 'herd-player', welcomed=True)
    login(app, player).post('/auth/remind-unjoined')
    assert sent_to(app) == [] and InviteToken.query.count() == 0


def test_nothing_to_do_once_everyone_has_joined(app, herd, discord_calls):
    team = db.session.get(TeamOrganization, herd['team'])
    from app.models.player import Player
    for i, player_id in enumerate(herd['players']):
        db.session.get(Player, player_id).user_id = make_user(team, f'joined-{i}')
    db.session.commit()
    html = login(app, herd['coach']).post('/auth/remind-unjoined', follow_redirects=True).get_data(as_text=True)
    assert 'Everyone on the roster has an account.' in html
    assert sent_to(app) == [] and discord_calls == []


def test_weekly_post_says_whos_left_while_the_join_link_is_on(app, bot, herd, discord_calls):
    team = db.session.get(TeamOrganization, herd['team'])
    team.join_enabled, team.join_code = True, 'HERD1234'
    settings = TeamSettings.query.filter_by(team_id=team.id).one()
    settings.discord_notify_upcoming_events = True
    settings.discord_week_post_day = date.today().weekday()
    db.session.commit()
    # A session this week, so the weekly post goes out
    from app.models.session import SessionPlan
    db.session.add(SessionPlan(title='Training', date=date.today() + timedelta(days=1),
                               team_organization_id=team.id))
    db.session.commit()

    morning = datetime.combine(date.today(), datetime.min.time()).replace(hour=10)
    assert notify.due_week_posts(morning)
    note = discord_calls[-1][2]['json']['content']
    assert 'still need to sign up' in note and '/auth/join/HERD1234' in note


def test_new_users_without_email_get_their_reminder_on_discord(app, bot, herd, discord_calls):
    team = db.session.get(TeamOrganization, herd['team'])
    now = datetime.utcnow()
    user_id = make_user(team, 'discord-only')
    user = db.session.get(User, user_id)
    user.created_at, user.discord_id = now - timedelta(days=5), '555'
    db.session.commit()

    assert onboarding.send_nudges(now) == 1
    assert sent_to(app) == []
    dm = [c for c in discord_calls if c[1].endswith('/messages') and 'content' in (c[2].get('json') or {})]
    assert 'Pick your name from the roster' in dm[-1][2]['json']['content']
    assert 'https://coach.example.com/welcome' in dm[-1][2]['json']['content']
    assert onboarding.send_nudges(now) == 0
