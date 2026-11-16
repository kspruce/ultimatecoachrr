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


CLUB_INFO = 'Welcome to the Herd!\nFees are £60 for the season. Training is Tuesdays at 7pm.'


def test_invites_carry_the_clubs_message(app, herd, discord_calls):
    """After trials the club sends its information with the invite: the
    message goes in each email, is kept for later reminders, and shows on
    the page where they set up their account."""
    coach = login(app, herd['coach'])
    coach.post('/auth/remind-unjoined', data={'invite_message': f'  {CLUB_INFO}  '})
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().invite_message == CLUB_INFO
    body = app.extensions['sent_emails'][0].get_content()
    assert 'Fees are £60 for the season.' in body and 'Welcome to the Herd!' in body

    page = coach.get('/auth/users').get_data(as_text=True)
    assert 'Training is Tuesdays at 7pm.' in page  # the box keeps it for next time

    token = InviteToken.query.filter_by(player_id=herd['players'][0]).one().token
    page = app.test_client().get(f'/auth/invite/accept/{token}').get_data(as_text=True)
    assert 'Fees are £60 for the season.' in page

    # Emptying the box removes it from later invites
    for t in InviteToken.query.all():
        t.created_at = datetime.utcnow() - timedelta(days=4)
    db.session.commit()
    coach.post('/auth/remind-unjoined', data={'invite_message': ''})
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().invite_message is None
    assert 'Fees' not in app.extensions['sent_emails'][-1].get_content()


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


def _newbie(herd, **extra):
    from app.models.player import Player
    from app.models.invite_token import InviteToken
    player = Player(name='New Player', active=True, team_organization_id=herd['team'], **extra)
    db.session.add(player)
    db.session.flush()
    invite = InviteToken.create(player_id=player.id, team_id=herd['team'], created_by_id=herd['coach'])
    db.session.add(invite)
    db.session.commit()
    return player.id, invite.token


def _number(player_id):
    from app.models.player import Player
    db.session.expire_all()
    p = db.session.get(Player, player_id)
    return p.jersey_number, p.number_provisional


def _account(number):
    return {'username': 'newbie', 'email': 'newbie@example.com', 'password': 'a-strong-passphrase-9',
            'confirm_password': 'a-strong-passphrase-9', 'jersey_number': number}


def test_new_players_pick_a_free_number_and_a_coach_confirms(app, herd):
    """Numbers are unique across the club (0-99). A new player picks one of
    the free ones when they set up their account; it's provisional until a
    coach confirms it."""
    from app.models.player import Player
    db.session.get(Player, herd['players'][2]).active = False  # left the club: number 3 is free again
    db.session.commit()
    player_id, token = _newbie(herd)
    visitor = app.test_client()
    page = visitor.get(f'/auth/invite/accept/{token}').get_data(as_text=True)
    assert '<option value="0">0</option>' in page and '<option value="3">3</option>' in page
    assert '<option value="1">' not in page and '<option value="2">' not in page

    visitor.post(f'/auth/invite/accept/{token}', data=_account('2'))  # taken
    assert User.query.filter_by(username='newbie').first() is None and _number(player_id) == (None, False)
    visitor.post(f'/auth/invite/accept/{token}', data=_account('7'))
    assert User.query.filter_by(username='newbie').first() is not None
    assert _number(player_id) == (7, True)

    coach = login(app, herd['coach'])
    assert 'picked a number' in coach.get('/').get_data(as_text=True)  # Needs attention
    page = coach.get('/team/numbers').get_data(as_text=True)
    assert 'New Player' in page and 'Provisional' in page
    newbie = User.query.filter_by(username='newbie').one()
    login(app, newbie.id).post(f'/team/numbers/{player_id}/confirm')
    assert _number(player_id) == (7, True)  # players can't confirm
    coach.post(f'/team/numbers/{player_id}/confirm')
    assert _number(player_id) == (7, False)


def test_new_players_can_decide_their_number_later(app, herd):
    player_id, token = _newbie(herd)
    app.test_client().post(f'/auth/invite/accept/{token}', data=_account(''))
    assert User.query.filter_by(username='newbie').first() is not None and _number(player_id) == (None, False)


def test_a_coach_given_number_is_not_offered_again(app, herd):
    player_id, token = _newbie(herd, jersey_number=12)
    page = app.test_client().get(f'/auth/invite/accept/{token}').get_data(as_text=True)
    assert 'name="jersey_number"' not in page and '#12' in page
    app.test_client().post(f'/auth/invite/accept/{token}', data=_account('40'))
    assert _number(player_id) == (12, False)
