"""Discord: Yes / Maybe / No buttons save answers like the site does, teams
set it up with one click (or a webhook), players connect by signing in with
Discord, and posts go out once. Discord itself is never called: requests to
it are recorded instead."""
import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app import db
from app.discord import api, events, messages, notify
from app.models.session import SessionPlan, SessionRSVP
from app.models.team_settings import TeamSettings
from app.models.tournament import Tournament
from app.models.user import User
from tests.test_training import add_schedule, club, login, week  # noqa: F401

WEBHOOK = 'https://discord.com/api/webhooks/1/abc'


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class Calls(list):
    replies = None


@pytest.fixture
def discord_calls(monkeypatch):
    """Record requests to Discord; answer with canned responses."""
    calls = Calls()
    replies = {}

    def fake(method, url, **kwargs):
        calls.append((method, url, kwargs))
        for key, reply in replies.items():
            if key in url:
                return reply(method, url, kwargs) if callable(reply) else reply
        return FakeResponse(200, {'id': '1'})

    monkeypatch.setattr(api.requests, 'request', fake)
    calls.replies = replies
    return calls


@pytest.fixture
def bot(app):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    app.config.update(DISCORD_CLIENT_ID='123', DISCORD_CLIENT_SECRET='s', DISCORD_BOT_TOKEN='t',
                      DISCORD_PUBLIC_KEY=public, BASE_URL='https://coach.example')
    return key


def signed_post(app, key, payload, good=True):
    body = json.dumps(payload).encode()
    timestamp = '1700000000'
    signature = key.sign(timestamp.encode() + body).hex()
    if not good:
        signature = '00' * 64
    return app.test_client().post('/discord/interactions', data=body, content_type='application/json',
                                  headers={'X-Signature-Ed25519': signature, 'X-Signature-Timestamp': timestamp})


def click(session, status, discord_id='999', in_dm=False):
    who = {'user': {'id': discord_id}} if in_dm else {'member': {'user': {'id': discord_id}}}
    return {'type': 3, 'data': {'custom_id': messages.custom_id(session.id, status)}, **who}


# ── Button clicks ──────────────────────────────────────────────────────────

def test_discord_must_sign_every_request(app, bot):
    assert signed_post(app, bot, {'type': 1}).get_json() == {'type': 1}
    assert signed_post(app, bot, {'type': 1}, good=False).status_code == 401
    # Without the site's bot set up, nothing is accepted
    app.config['DISCORD_PUBLIC_KEY'] = ''
    assert signed_post(app, bot, {'type': 1}).status_code == 401


def test_a_button_tap_saves_the_players_answer(app, bot, club, week):
    session = week['sat'].sessions.first()
    club['ann_user'].discord_id = '999'
    db.session.commit()
    ann_id, team_id = club['ann'].id, club['team'].id
    reply = signed_post(app, bot, click(session, 'maybe')).get_json()
    assert reply['type'] == 4 and reply['data']['flags'] == 64 and 'Maybe' in reply['data']['content']
    rsvp = SessionRSVP.query.one()
    assert (rsvp.player_id, rsvp.status, rsvp.team_organization_id) == (ann_id, 'maybe', team_id)
    # Again from a direct message: the answer changes, still one row
    signed_post(app, bot, click(session, 'attending', in_dm=True))
    assert SessionRSVP.query.one().status == 'attending'


def test_strangers_are_sent_to_connect(app, bot, club, week):
    session = week['sat'].sessions.first()
    coach_id = club['coach'].id
    reply = signed_post(app, bot, click(session, 'attending', discord_id='555')).get_json()
    assert '/discord/connect' in reply['data']['content'] and SessionRSVP.query.count() == 0
    # A connected account with no player on this team can't answer for anyone
    db.session.get(User, coach_id).discord_id = '555'
    db.session.commit()
    reply = signed_post(app, bot, click(session, 'attending', discord_id='555')).get_json()
    assert "isn't linked to a player" in reply['data']['content'] and SessionRSVP.query.count() == 0


def test_cancelled_and_unknown_buttons(app, bot, club, week):
    session = week['sat'].sessions.first()
    session.status = 'cancelled'
    db.session.commit()
    assert 'cancelled' in signed_post(app, bot, click(session, 'attending')).get_json()['data']['content']
    junk = {'type': 3, 'data': {'custom_id': 'rsvp:abc:yes'}, 'member': {'user': {'id': '1'}}}
    assert "doesn't do anything" in signed_post(app, bot, junk).get_json()['data']['content']
    assert messages.parse_custom_id('rsvp:12:not_attending') == (12, 'not_attending')
    assert messages.parse_custom_id('rsvp:12:yes') is None


# ── Posting ────────────────────────────────────────────────────────────────

def test_webhooks_post_without_buttons(app, club, week, discord_calls):
    settings = TeamSettings(team_id=club['team'].id, discord_enabled=True, discord_webhook_url=WEBHOOK)
    db.session.add(settings)
    db.session.commit()
    session = week['sat'].sessions.first()
    assert notify.post(club['team'].id, messages.session_post(session))
    method, url, kwargs = discord_calls[-1]
    assert url == WEBHOOK and 'components' not in kwargs['json']
    assert kwargs['json']['embeds'][0]['url'].endswith(f'/sessions/{session.id}/detail')


def test_the_bot_posts_with_buttons(app, bot, club, week, discord_calls):
    db.session.add(TeamSettings(team_id=club['team'].id, discord_enabled=True, discord_guild_id='42',
                                discord_notification_channel_id='77', discord_webhook_url=WEBHOOK))
    db.session.commit()
    session = week['sat'].sessions.first()
    assert notify.post(club['team'].id, messages.session_post(session))
    method, url, kwargs = discord_calls[-1]
    assert url.endswith('/channels/77/messages') and kwargs['headers']['Authorization'] == 'Bot t'
    buttons = kwargs['json']['components'][0]['components']
    assert [b.get('custom_id') for b in buttons[:3]] == [
        f'rsvp:{session.id}:attending', f'rsvp:{session.id}:maybe', f'rsvp:{session.id}:not_attending']


def test_a_failed_post_never_breaks_anything(app, club, discord_calls):
    db.session.add(TeamSettings(team_id=club['team'].id, discord_enabled=True, discord_webhook_url=WEBHOOK))
    db.session.commit()
    discord_calls.replies['webhooks'] = FakeResponse(404, {'message': 'Unknown Webhook'})
    assert notify.post(club['team'].id, messages.plain('hi')) is False


def test_the_weekly_post_goes_once_on_its_day(app, bot, club, week, discord_calls):
    from datetime import datetime
    today = date.today()
    db.session.add(TeamSettings(team_id=club['team'].id, discord_enabled=True, discord_guild_id='42',
                                discord_notification_channel_id='77', discord_notify_upcoming_events=True,
                                discord_week_post_day=today.weekday()))
    db.session.commit()
    morning = datetime.combine(today, datetime.min.time()).replace(hour=10)
    assert notify.due_week_posts(morning.replace(hour=8)) == []  # not before 9am
    assert [t.id for t in notify.due_week_posts(morning)] == [club['team'].id]
    sessions_this_week = SessionPlan.query.filter(SessionPlan.date >= today,
                                                  SessionPlan.date <= today + timedelta(days=6)).count()
    assert len(discord_calls) == 1 + sessions_this_week
    assert notify.due_week_posts(morning) == []


def test_new_tournaments_are_announced_when_the_team_wants(app, club, discord_calls, monkeypatch):
    class Inline:  # run the post-commit thread straight away
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(events.threading, 'Thread', Inline)
    db.session.add(Tournament(name='Quiet Cup', start_date=date.today(), team_organization_id=club['team'].id))
    db.session.commit()
    assert discord_calls == []
    db.session.add(TeamSettings(team_id=club['team'].id, discord_enabled=True, discord_webhook_url=WEBHOOK,
                                discord_notify_new_events=True))
    db.session.commit()
    db.session.add(Tournament(name='Loud Cup', start_date=date.today(), team_organization_id=club['team'].id))
    db.session.commit()
    assert len(discord_calls) == 1 and 'Loud Cup' in discord_calls[0][2]['json']['embeds'][0]['title']
    # Schedule dates aren't announced one by one (the weekly post covers them)
    add_schedule(club, 'Sunday', 6)
    assert len(discord_calls) == 1


# ── Setting it up ──────────────────────────────────────────────────────────

def test_webhook_setup(app, club, discord_calls):
    c = login(app, club, 'admin')
    assert 'Post with a webhook' in c.get('/discord/settings').get_data(as_text=True)
    c.post('/discord/settings', data={'action': 'webhook', 'webhook_url': 'https://evil.example/hook'})
    assert TeamSettings.query.filter_by(team_id=club['team'].id).one().discord_webhook_url is None
    c.post('/discord/settings', data={'action': 'webhook', 'webhook_url': WEBHOOK})
    settings = TeamSettings.query.filter_by(team_id=club['team'].id).one()
    assert settings.discord_webhook_url == WEBHOOK and settings.discord_enabled
    assert discord_calls[-1][1] == WEBHOOK  # a hello message to check it works
    # Coaches and players can't change it
    assert login(app, club, 'coach').get('/discord/settings').status_code == 403


def _start(c, path):
    r = c.get(path)
    assert r.status_code == 302 and r.location.startswith('https://discord.com/oauth2/authorize')
    return parse_qs(urlparse(r.location).query)


def test_one_click_server_setup(app, bot, club, discord_calls, monkeypatch):
    c = login(app, club, 'admin')
    query = _start(c, '/discord/add')
    assert query['scope'] == ['identify bot'] and query['permissions'] == [str(api.BOT_PERMISSIONS)]
    discord_calls.replies['oauth2/token'] = FakeResponse(200, {
        'access_token': 'a', 'guild': {'id': '42', 'name': 'Herd server', 'system_channel_id': '77'}})
    discord_calls.replies['users/@me'] = FakeResponse(200, {'id': '1001', 'username': 'boss'})
    discord_calls.replies['guilds/42/channels'] = FakeResponse(200, [
        {'id': '77', 'name': 'general', 'type': 0, 'position': 0},
        {'id': '78', 'name': 'training', 'type': 0, 'position': 1},
        {'id': '79', 'name': 'Voice', 'type': 2, 'position': 2}])

    # A forged or replayed state is refused
    r = c.get('/discord/callback?code=x&state=forged')
    assert TeamSettings.query.filter_by(team_id=club['team'].id).first() is None or \
        not TeamSettings.query.filter_by(team_id=club['team'].id).one().discord_guild_id

    query = _start(c, '/discord/add')
    r = c.get(f"/discord/callback?code=x&state={query['state'][0]}")
    assert r.status_code == 302
    db.session.expire_all()
    settings = TeamSettings.query.filter_by(team_id=club['team'].id).one()
    assert (settings.discord_guild_id, settings.discord_guild_name, settings.discord_notification_channel_id) == \
        ('42', 'Herd server', '77')
    assert db.session.get(User, club['admin'].id).discord_id == '1001'

    page = c.get('/discord/settings').get_data(as_text=True)
    assert 'Connected to Herd server' in page and '#training' in page and 'Voice' not in page
    c.post('/discord/settings', data={'action': 'channel', 'channel_id': '78'})
    db.session.expire_all()
    assert TeamSettings.query.filter_by(team_id=club['team'].id).one().discord_notification_channel_id == '78'
    assert discord_calls[-1][1].endswith('/channels/78/messages')
    # Only the server's own channels
    c.post('/discord/settings', data={'action': 'channel', 'channel_id': '12345'})
    db.session.expire_all()
    assert TeamSettings.query.filter_by(team_id=club['team'].id).one().discord_notification_channel_id == '78'


def test_players_connect_by_signing_in(app, bot, club, discord_calls):
    other = club['bea_user']
    other.discord_id = '2002'
    db.session.commit()
    c = login(app, club, 'ann')
    query = _start(c, '/discord/connect')
    assert query['scope'] == ['identify']
    discord_calls.replies['oauth2/token'] = FakeResponse(200, {'access_token': 'a'})
    discord_calls.replies['users/@me'] = FakeResponse(200, {'id': '2002', 'username': 'ann_d',
                                                            'global_name': 'Ann D'})
    c.get(f"/discord/callback?code=x&state={query['state'][0]}")
    db.session.expire_all()
    assert (db.session.get(User, club['ann_user'].id).discord_id,
            db.session.get(User, club['ann_user'].id).discord_username) == ('2002', 'Ann D')
    assert db.session.get(User, other.id).discord_id is None  # one Discord account, one login
    assert 'Connected as' in c.get('/auth/profile').get_data(as_text=True)
    c.post('/discord/disconnect')
    db.session.expire_all()
    assert db.session.get(User, club['ann_user'].id).discord_id is None


def test_site_setup_page(app, bot, club, discord_calls):
    club['admin'].is_superadmin = True
    db.session.commit()
    discord_calls.replies['applications/@me'] = FakeResponse(200, {'name': 'Ultimate Coach',
                                                                   'interactions_endpoint_url': None})
    c = login(app, club, 'admin')
    page = c.get('/discord/setup').get_data(as_text=True)
    assert 'Set it for me' in page and '/discord/callback' in page
    c.post('/discord/setup')
    method, url, kwargs = discord_calls[-1]
    assert method == 'PATCH' and kwargs['json']['interactions_endpoint_url'].endswith('/discord/interactions')
    assert login(app, club, 'coach').get('/discord/setup').status_code == 403


def test_reminders_go_by_discord_when_connected(app, bot, club, week, discord_calls):
    from app.utils import reminders
    club['ann_user'].discord_id = '999'
    db.session.commit()
    reached, _ = reminders.send_for_team(club['team'].id)
    dms = [c for c in discord_calls if c[1].endswith('/users/@me/channels')]
    assert reached >= 1 and dms and dms[0][2]['json'] == {'recipient_id': '999'}
    message = next(c for c in discord_calls if c[1].endswith('/messages'))[2]['json']
    assert message['components'][0]['components'][0]['custom_id'].startswith('rsvp:')
