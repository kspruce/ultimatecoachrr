"""Tournaments, replies, squad picks, game line-ups, the calendar and the
roster: a coach can go from "we're going" to "everyone knows which games
they play", and a player can answer in one tap."""
from datetime import date, time, timedelta

import pytest

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.onboarding import UserOnboarding
from app.models.player import Player
from app.models.season import SeasonRoster, Squad
from app.models.session import SessionPlan, SessionRSVP
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.user import User
from app.utils import event_notify
from app.utils.schedule_parse import parse_schedule
from app.utils.season import ensure_seasons
from tests import stats_data

TODAY = date.today()


def _user(team, username, role, player=None):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=role == 'admin', team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    if player is not None:
        player.user_id = user.id
    db.session.commit()
    return user


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    players = stats_data.build_players(team, 6)
    ensure_seasons(team.id)
    coach = _user(team, 'coach', 'coach')
    users = [_user(team, f'p{i}', 'player', p) for i, p in enumerate(players[:4])]
    tournament = Tournament(name='Nationals', start_date=TODAY + timedelta(days=20),
                            end_date=TODAY + timedelta(days=21), location='Bristol',
                            rsvp_deadline=TODAY + timedelta(days=10), team_organization_id=team.id)
    db.session.add(tournament)
    db.session.commit()
    return {
        'app': app, 'team': team.id, 'tournament': tournament.id,
        'players': [p.id for p in players], 'coach': coach.id, 'users': [u.id for u in users],
        'coach_client': stats_data.Client(app, coach.id, team.id),
        'player_client': stats_data.Client(app, users[0].id, team.id),
    }


def _rsvp(tournament_id, player_id):
    db.session.expire_all()
    return TournamentRSVP.query.filter_by(tournament_id=tournament_id, player_id=player_id).first()


def _emails(app):
    app.config.update(MAIL_SERVER='smtp.example.com', MAIL_DEFAULT_SENDER='coach@example.com')
    return app.extensions.setdefault('sent_emails', [])


# ── Fixes ──────────────────────────────────────────────────────────────────

def test_roster_filters_by_line_and_saves_it(app, club):
    c = club['coach_client']
    pid = club['players'][0]
    r = c.post(f'/team/roster/{pid}', json={'field': 'line_preference', 'value': 'O-line'})
    assert r.get_json()['success']
    db.session.expire_all()
    assert db.session.get(Player, pid).line_preference == 'O-line'
    page = c.get('/team/?line_preference=O-line&active_only=y')
    assert page.status_code == 200
    assert db.session.get(Player, pid).name in page.get_data(as_text=True)
    assert db.session.get(Player, club['players'][1]).name not in page.get_data(as_text=True)


def test_coaches_not_just_admins_get_the_squad_tools(club):
    page = club['coach_client'].get(f"/tournaments/{club['tournament']}").get_data(as_text=True)
    assert 'Pick the squad' in page and 'tab=squad' in page
    assert club['coach_client'].get(f"/tournaments/{club['tournament']}?tab=squad").status_code == 200
    # Players get the overview, never the squad tab
    player_page = club['player_client'].get(f"/tournaments/{club['tournament']}?tab=squad").get_data(as_text=True)
    assert 'Can you make it?' in player_page and 'btn-check js-pick' not in player_page
    # The old pages now open the right tab
    old = club['coach_client'].get(f"/tournaments/{club['tournament']}/rsvps")
    assert old.status_code == 302 and 'tab=squad' in old.location


def test_rsvp_only_accepts_real_answers(club):
    c = club['player_client']
    bad = c.post('/api/rsvp', json={'id': club['tournament'], 'type': 'tournament', 'status': 'yes please'})
    assert bad.status_code == 400
    assert _rsvp(club['tournament'], club['players'][0]) is None
    ok = c.post('/api/rsvp', json={'id': club['tournament'], 'type': 'tournament', 'status': 'maybe',
                                   'notes': 'Sunday only'})
    assert ok.get_json()['success']
    answer = _rsvp(club['tournament'], club['players'][0])
    assert answer.status == 'maybe' and answer.notes == 'Sunday only' and answer.responded_at
    other = c.post('/api/rsvp', json={'id': 9999, 'type': 'tournament', 'status': 'maybe'})
    assert other.status_code == 404


def test_one_tap_answer_and_late_replies_are_flagged(club):
    c = club['player_client']
    r = c.post(f"/tournaments/{club['tournament']}/rsvp", json={'status': 'attending'})
    assert r.get_json()['success'] and not r.get_json()['late']
    t = db.session.get(Tournament, club['tournament'])
    t.rsvp_deadline = TODAY - timedelta(days=1)
    db.session.commit()
    r = c.post(f"/tournaments/{club['tournament']}/rsvp", json={'status': 'not_attending'})
    assert r.get_json()['late']
    # The plain form (no JavaScript) works too
    r = c.post(f"/tournaments/{club['tournament']}/rsvp", data={'status': 'maybe'})
    assert r.status_code == 302
    assert _rsvp(club['tournament'], club['players'][0]).status == 'maybe'


def test_picking_someone_who_never_replied_does_not_invent_an_answer(club):
    c = club['coach_client']
    tid, quiet, said_no = club['tournament'], club['players'][5], club['players'][1]
    r = c.post(f'/tournaments/{tid}/selection', json={'player_id': quiet, 'selection': 'picked'})
    assert r.get_json()['success'] and r.get_json()['summary']['picked'] == 1
    row = _rsvp(tid, quiet)
    assert row.selection == 'picked' and row.selected_by_admin and row.status is None

    club['app'].extensions.pop('sent_emails', None)
    stats_data.Client(club['app'], club['users'][1], club['team']).post(
        f'/tournaments/{tid}/rsvp', json={'status': 'not_attending'})
    r = c.post(f'/tournaments/{tid}/selection', json={'player_id': said_no, 'selection': 'picked'})
    assert "can't make it" in r.get_json()['warning']


def test_unpicking_takes_a_player_out_of_the_games(club):
    c = club['coach_client']
    tid, pid = club['tournament'], club['players'][0]
    c.post(f'/tournaments/{tid}/selection', json={'player_id': pid, 'selection': 'picked'})
    c.post(f'/tournaments/{tid}/schedule', data={'schedule': 'vs Hucks', 'action': 'save'})
    game = Game.query.filter_by(tournament_id=tid).one()
    assert GamePlayer.query.filter_by(game_id=game.id, player_id=pid).count() == 1
    c.post(f'/tournaments/{tid}/selection', json={'player_id': pid, 'selection': 'reserve'})
    db.session.expire_all()
    assert GamePlayer.query.filter_by(game_id=game.id, player_id=pid).count() == 0


def test_new_games_start_with_the_picked_players(club):
    c = club['coach_client']
    tid = club['tournament']
    picked = club['players'][:3]
    # Someone attending but not picked is left out once there's a squad
    stats_data.Client(club['app'], club['users'][3], club['team']).post(
        f'/tournaments/{tid}/rsvp', json={'status': 'attending'})
    for pid in picked:
        c.post(f'/tournaments/{tid}/selection', json={'player_id': pid, 'selection': 'picked'})
    c.post('/games/add', data={'opponent': 'Clapham', 'tournament_id': tid, 'our_score': 0, 'their_score': 0,
                               'date': (TODAY + timedelta(days=20)).isoformat(), 'start_time': '09:30',
                               'field': 'Pitch 4'})
    game = Game.query.filter_by(opponent='Clapham').one()
    assert game.start_time == time(9, 30) and game.field == 'Pitch 4'
    assert {gp.player_id for gp in game.assigned_players} == set(picked)


def test_add_multiple_games_copes_with_blank_scores(club):
    c = club['coach_client']
    tid = club['tournament']
    c.post(f'/tournaments/{tid}/selection', json={'player_id': club['players'][0], 'selection': 'picked'})
    r = c.post(f'/games/add_multiple?tournament_id={tid}', data={
        'opponent[]': ['Fire', 'Ice', ''], 'date[]': ['', 'not a date', ''], 'start_time[]': ['10:00', '', ''],
        'field[]': ['1', '', ''], 'our_score[]': ['', '13', ''], 'their_score[]': ['', 'x', ''],
        'youtube_link[]': ['', '', ''], 'notes[]': ['', '', '']})
    assert r.status_code == 302
    games = {g.opponent: g for g in Game.query.filter_by(tournament_id=tid)}
    assert set(games) == {'Fire', 'Ice'}
    assert games['Fire'].date == TODAY + timedelta(days=20) and games['Fire'].start_time == time(10)
    assert games['Ice'].our_score == 13 and games['Ice'].their_score == 0
    assert [gp.player_id for gp in games['Fire'].assigned_players] == [club['players'][0]]


def test_a_squads_tournament_only_asks_that_squad(club):
    team_id, tid = club['team'], club['tournament']
    ones = Squad(name='1s', team_organization_id=team_id)
    db.session.add(ones)
    db.session.flush()
    t = db.session.get(Tournament, tid)
    t.squad_id = ones.id
    rows = SeasonRoster.query.filter_by(season_id=t.season_id).all()
    assert rows, 'players start on the season roster'
    for row in rows[:2]:
        row.squad_id = ones.id
    rows[2].status = 'left'
    db.session.commit()
    page = club['coach_client'].get(f'/tournaments/{tid}?tab=squad').get_data(as_text=True)
    names = {db.session.get(Player, r.player_id).name for r in rows[:2]}
    for name in names:
        assert name in page
    assert db.session.get(Player, rows[3].player_id).name not in page


# ── Selection and notifications ────────────────────────────────────────────

def test_players_see_the_pick_only_once_it_is_published(club):
    app, c, tid = club['app'], club['coach_client'], club['tournament']
    sent = _emails(app)
    p0, p1 = club['players'][0], club['players'][1]
    stats_data.Client(app, club['users'][1], club['team']).post(f'/tournaments/{tid}/rsvp', json={'status': 'attending'})
    c.post(f'/tournaments/{tid}/selection', json={'player_id': p0, 'selection': 'picked'})
    page = club['player_client'].get(f'/tournaments/{tid}').get_data(as_text=True)
    assert "You're in the squad" not in page

    sent.clear()
    c.post(f'/tournaments/{tid}/publish')
    page = club['player_client'].get(f'/tournaments/{tid}').get_data(as_text=True)
    assert "You're in the squad" in page
    subjects = {m['To']: m['Subject'] for m in sent}
    assert subjects['p0@example.com'] == "You're in for Nationals"
    assert subjects['p1@example.com'] == 'Nationals squad'  # replied, not picked
    assert 'p2@example.com' not in subjects  # never replied, not picked

    c.post(f'/tournaments/{tid}/publish', data={'unpublish': '1'})
    assert "You're in the squad" not in club['player_client'].get(f'/tournaments/{tid}').get_data(as_text=True)


def test_new_tournament_asks_players_and_nudge_reminds_non_repliers(club):
    app, c = club['app'], club['coach_client']
    sent = _emails(app)
    sent.clear()
    r = c.post('/tournaments/add', data={'name': 'Regionals', 'start_date': (TODAY + timedelta(days=30)).isoformat(),
                                         'end_date': (TODAY + timedelta(days=30)).isoformat(),
                                         'rsvp_deadline': (TODAY + timedelta(days=14)).isoformat(),
                                         'notes': 'Bring both shirts', 'ask_players': 'y', 'season': '', 'squad_id': ''})
    assert r.status_code == 302
    t = Tournament.query.filter_by(name='Regionals').one()
    assert t.notes == 'Bring both shirts'
    assert sorted(m['To'] for m in sent) == [f'p{i}@example.com' for i in range(4)]
    assert 'Bring both shirts' in sent[0].get_content()

    stats_data.Client(app, club['users'][0], club['team']).post(f'/tournaments/{t.id}/rsvp', json={'status': 'attending'})
    user = db.session.get(User, club['users'][1])
    user.email_event_updates = False
    db.session.commit()
    sent.clear()
    c.post(f'/tournaments/{t.id}/nudge')
    assert sorted(m['To'] for m in sent) == ['p2@example.com', 'p3@example.com']


def test_daily_reminders_go_once_near_the_deadline(club):
    app = club['app']
    sent = _emails(app)
    t = db.session.get(Tournament, club['tournament'])
    t.rsvp_deadline = TODAY + timedelta(days=5)
    db.session.commit()
    assert event_notify.send_due_reminders() == (0, 0)
    t.rsvp_deadline = TODAY + timedelta(days=2)
    db.session.commit()
    sent.clear()
    assert event_notify.send_due_reminders() == (1, 4)
    assert event_notify.send_due_reminders() == (0, 0)


def test_players_are_emailed_their_games(club):
    app, c, tid = club['app'], club['coach_client'], club['tournament']
    sent = _emails(app)
    for pid in club['players'][:2]:
        c.post(f'/tournaments/{tid}/selection', json={'player_id': pid, 'selection': 'picked'})
    c.post(f'/tournaments/{tid}/schedule', data={'schedule': 'Sat 09:00 vs Hucks Field 2\nSun 11:00 vs Fire', 'action': 'save'})
    games = Game.query.filter_by(tournament_id=tid).order_by(Game.date).all()
    # Player 1 sits out Sunday
    r = c.post(f'/tournaments/{tid}/games/{games[1].id}/player', json={'player_id': club['players'][1], 'playing': False})
    assert r.get_json()['count'] == 1
    sent.clear()
    c.post(f'/tournaments/{tid}/send-schedule')
    bodies = {m['To']: m.get_content() for m in sent}
    assert 'vs Hucks, Field 2' in bodies['p0@example.com'] and 'vs Fire' in bodies['p0@example.com']
    assert 'vs Fire' not in bodies['p1@example.com']
    # The player's page lists their games
    page = club['player_client'].get(f'/tournaments/{tid}').get_data(as_text=True)
    assert 'Your games' in page


# ── Schedule ───────────────────────────────────────────────────────────────

def test_schedule_lines_are_understood():
    sat, sun = date(2026, 11, 7), date(2026, 11, 8)
    games = parse_schedule('Sat 09:00 vs Rival FC Field 3\n'
                           'Sunday 2pm v Hucks @ Pitch 2\n'
                           '2026-11-08 10:00 Brighton (field 4)\n'
                           '# a comment\n'
                           '3 Peaks\n'
                           'Mon 10:00 vs Nobody\n'
                           'vs\n', sat, sun)
    simple = [(g['date'], g['start_time'], g['opponent'], g['field'], bool(g['error'])) for g in games]
    assert simple == [
        (sat, time(9), 'Rival FC', 'Field 3', False),
        (sun, time(14), 'Hucks', 'Pitch 2', False),
        (sun, time(10), 'Brighton', 'field 4', False),
        (sat, None, '3 Peaks', None, False),
        (sat, time(10), 'Nobody', None, True),
        (sat, None, '', None, True),
    ]


def test_schedule_preview_then_save(club):
    c, tid = club['coach_client'], club['tournament']
    text = 'Sat 09:00 vs Hucks\nnot a game vs\nvs'
    preview = c.post(f'/tournaments/{tid}/schedule', data={'schedule': text, 'action': 'preview'})
    assert preview.status_code == 200 and 'Add 2 games' in preview.get_data(as_text=True)
    assert Game.query.filter_by(tournament_id=tid).count() == 0
    c.post(f'/tournaments/{tid}/schedule', data={'schedule': text, 'action': 'save'})
    assert Game.query.filter_by(tournament_id=tid).count() == 2


# ── Calendar ───────────────────────────────────────────────────────────────

def _events(client, start, end, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    return client.get(f'/calendar/events?start={start}&end={end}&{query}').get_json()


def test_calendar_shows_past_running_and_future_events(club):
    team_id = club['team']
    db.session.add_all([
        Tournament(name='Last spring', start_date=TODAY - timedelta(days=200), team_organization_id=team_id),
        Tournament(name='Happening now', start_date=TODAY - timedelta(days=1), end_date=TODAY + timedelta(days=1),
                   team_organization_id=team_id),
        Game(opponent='Friendly', date=TODAY + timedelta(days=3), start_time=time(18, 30), team_organization_id=team_id),
        SessionPlan(title='Throwing', date=TODAY + timedelta(days=2), team_organization_id=team_id),
    ])
    db.session.commit()
    c = club['player_client']
    past = _events(c, TODAY - timedelta(days=210), TODAY - timedelta(days=190))
    assert [e['title'] for e in past] == ['Last spring']
    now = {e['title']: e for e in _events(c, TODAY - timedelta(days=3), TODAY + timedelta(days=30))}
    assert {'Happening now', 'Nationals', 'vs Friendly', 'Throwing'} <= set(now)
    assert now['vs Friendly']['allDay'] is False and now['vs Friendly']['start'].endswith('18:30:00')
    only_games = _events(c, TODAY, TODAY + timedelta(days=30), types='game')
    assert [e['type'] for e in only_games] == ['game']
    assert 'edit_url' not in now['Nationals']  # players don't get coach links
    assert 'edit_url' in {e['title']: e for e in _events(club['coach_client'], TODAY, TODAY + timedelta(days=30))}['Nationals']


def test_calendar_only_mine(club):
    c, tid = club['player_client'], club['tournament']
    c.post(f'/tournaments/{tid}/rsvp', json={'status': 'not_attending'})
    events = _events(c, TODAY, TODAY + timedelta(days=30), mine='1')
    assert 'Nationals' not in [e['title'] for e in events]


def test_calendar_session_reply(club):
    session_plan = SessionPlan(title='Track', date=TODAY + timedelta(days=1), team_organization_id=club['team'])
    db.session.add(session_plan)
    db.session.commit()
    r = club['player_client'].post('/api/rsvp', json={'id': session_plan.id, 'type': 'session', 'status': 'attending'})
    assert r.get_json()['success']
    assert SessionRSVP.query.filter_by(session_id=session_plan.id).one().status == 'attending'


def test_calendar_subscription_feed(club, app):
    c = club['player_client']
    tid = club['tournament']
    c.post('/calendar/feed-link')
    db.session.expire_all()
    token = db.session.get(User, club['users'][0]).calendar_token
    assert token and len(token) >= 24
    anon = app.test_client()
    with app.app_context():
        feed = anon.get(f'/calendar/feed/{token}.ics')
    assert feed.status_code == 200 and feed.mimetype == 'text/calendar'
    body = feed.get_data(as_text=True)
    assert 'BEGIN:VCALENDAR' in body and 'SUMMARY:Nationals' in body
    start = (TODAY + timedelta(days=20)).strftime('%Y%m%d')
    assert f'DTSTART;VALUE=DATE:{start}' in body
    # Said no: it drops out of their feed
    c.post(f'/tournaments/{tid}/rsvp', json={'status': 'not_attending'})
    with app.app_context():
        assert 'Nationals' not in anon.get(f'/calendar/feed/{token}.ics').get_data(as_text=True)
        assert anon.get('/calendar/feed/not-a-token.ics').status_code == 404


# ── Roster and home page ───────────────────────────────────────────────────

def test_roster_cells_save_to_the_season(club):
    c = club['coach_client']
    pid = club['players'][0]
    season_id = Tournament.query.get(club['tournament']).season_id
    assert c.post(f'/team/roster/{pid}', json={'field': 'jersey', 'value': '77', 'season_id': season_id}).get_json()['success']
    assert c.post(f'/team/roster/{pid}', json={'field': 'status', 'value': 'injured', 'season_id': season_id}).get_json()['success']
    bad = c.post(f'/team/roster/{pid}', json={'field': 'position', 'value': 'goalie', 'season_id': season_id})
    assert bad.status_code == 400
    db.session.expire_all()
    row = SeasonRoster.query.filter_by(season_id=season_id, player_id=pid).one()
    assert row.jersey_number == 77 and row.status == 'injured'
    assert db.session.get(Player, pid).jersey_number == 77
    assert club['player_client'].post(f'/team/roster/{pid}', json={'field': 'jersey', 'value': '1'}).status_code == 302


def test_quick_add_puts_names_on_the_roster(club):
    c = club['coach_client']
    existing = db.session.get(Player, club['players'][0]).name
    c.post('/team/quick-add', data={'names': f'Sam Jones\n#12 Priya Patel\n\n{existing}\n'})
    db.session.expire_all()
    priya = Player.query.filter_by(name='Priya Patel').one()
    assert Player.query.filter_by(name=existing).count() == 1
    season_id = Tournament.query.get(club['tournament']).season_id
    entry = SeasonRoster.query.filter_by(season_id=season_id, player_id=priya.id).one()
    assert entry.jersey_number == 12 and entry.status == 'active'


def test_home_page_lists_what_needs_a_reply(club):
    c, tid = club['player_client'], club['tournament']
    page = c.get('/').get_data(as_text=True)
    assert 'Can you make it?' in page and 'Nationals' in page
    c.post(f'/tournaments/{tid}/rsvp', json={'status': 'attending'})
    assert 'Can you make it?' not in c.get('/').get_data(as_text=True)


def test_email_preference_is_saved_without_a_password(club):
    c = club['player_client']
    c.post('/auth/account', data={'action': 'notifications'})
    db.session.expire_all()
    assert db.session.get(User, club['users'][0]).email_event_updates is False


def test_tournament_games_are_in_the_tournaments_season(club):
    """A game added to a tournament goes in the tournament's season, whatever
    its own date, so the games list for that season shows it."""
    c = club['coach_client']
    next_year = TODAY.year + 1
    c.post('/tournaments/add', data={'name': 'Next year open', 'season': str(next_year), 'squad_id': ''})
    t = Tournament.query.filter_by(name='Next year open').one()
    c.post('/games/add', data={'opponent': 'Dated today', 'tournament_id': t.id, 'our_score': 0,
                               'their_score': 0, 'date': TODAY.isoformat()})
    c.post('/games/add', data={'opponent': 'No date', 'tournament_id': t.id, 'our_score': 0, 'their_score': 0})
    c.post(f'/tournaments/{t.id}/schedule', data={'schedule': 'vs Pasted', 'action': 'save'})
    db.session.expire_all()
    games = Game.query.filter_by(tournament_id=t.id).all()
    assert len(games) == 3 and {g.season_id for g in games} == {t.season_id}

    def listed(url):
        page = c.get(url).get_data(as_text=True)
        return {g.opponent for g in games if f'/games/{g.id}"' in page}, page

    shown, _ = listed(f'/games/?season={next_year}')
    assert shown == {'Dated today', 'No date', 'Pasted'}
    # Viewing this season: they're not listed, but the page says so and links to all
    shown, page = listed('/games/')
    assert shown == set()
    assert '3 more games are in other seasons' in page and 'season=all' in page
    shown, _ = listed('/games/?season=all&squad=all')
    assert shown == {'Dated today', 'No date', 'Pasted'}


def test_existing_games_are_moved_into_their_tournaments_season(club):
    """The migration's repair: games already in the wrong season move."""
    import importlib.util
    import pathlib
    from unittest import mock

    from app.models.season import Season

    t = db.session.get(Tournament, club['tournament'])
    other = Season(team_organization_id=club['team'], year=TODAY.year + 5,
                   start_date=date(TODAY.year + 5, 1, 1), end_date=date(TODAY.year + 5, 12, 31))
    db.session.add(other)
    db.session.flush()
    game = Game(opponent='Stray', tournament_id=t.id, team_organization_id=club['team'], season_id=other.id)
    db.session.add(game)
    db.session.commit()
    db.session.execute(db.text('UPDATE game SET season_id = :s WHERE id = :g'), {'s': other.id, 'g': game.id})
    db.session.commit()

    path = next(pathlib.Path('migrations/versions').glob('b5d7f9a1c3e6_*.py'))
    spec = importlib.util.spec_from_file_location('repair', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with mock.patch.object(module, 'op', mock.Mock(execute=lambda sql: db.session.execute(db.text(sql)))):
        module.upgrade()
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Game, game.id).season_id == t.season_id
