"""Unplayed games aren't draws, search stays inside the team, the result
card link, the visitor navbar, the install manifest and the sessions list."""
from datetime import date, timedelta

from app import db
from app.models.clip import Clip
from app.models.event import Event
from app.models.game import Game
from app.models.playbook import Play
from app.models.point import Point
from app.models.session import SessionPlan, SessionRSVP
from app.models.theory import TheorySection, TheoryTopic
from tests import stats_data
from tests.test_team_isolation import make_user, teams, client, page  # noqa: F401


# ── A 0-0 game hasn't been played ────────────────────────────────

def test_unplayed_game_is_not_a_draw(app, team):
    unplayed = Game(opponent='A', team_organization_id=team.id)
    drawn = Game(opponent='B', our_score=7, their_score=7, team_organization_id=team.id)
    won = Game(opponent='C', our_score=9, their_score=3, team_organization_id=team.id)
    db.session.add_all([unplayed, drawn, won])
    db.session.commit()
    assert not unplayed.is_played and not unplayed.is_tie and not unplayed.is_win and not unplayed.is_loss
    assert unplayed.result_string == 'Not played'
    assert drawn.is_tie and drawn.result_string == 'T 7-7'
    assert won.is_win and not won.is_tie

    from app.stats.team import calculate_team_summary
    summary = calculate_team_summary([unplayed, drawn, won])
    assert (summary['wins'], summary['losses'], summary['ties'], summary['games_played']) == (1, 0, 1, 2)


# ── Search ───────────────────────────────────────────────────────

def test_search_only_finds_your_teams_things(app, teams):
    c = client(app, teams)
    for word in ('secret', 'Herd opponent', 'Herd clip', 'Herd session'):
        html = page(c, f'/search?q={word}')
        assert 'Nothing found' in html, word
    html = page(c, '/search?q=drill')
    assert 'Huck drill' in html and 'Zone drill' in html and 'Herd secret huck drill' not in html
    assert 'Other opponent' in page(c, '/search?q=opponent')
    assert 'Other tour' in page(c, '/search?q=tour')
    assert 'Other play' in page(c, '/search?q=play')


def test_search_hides_drafts_and_hidden_clips_from_players(app, teams):
    other = teams['other']
    section = TheorySection(name='Offence', slug='offence', team_organization_id=other)
    db.session.add(section)
    db.session.flush()
    db.session.add_all([
        Play(name='Zebra draft play', status='draft', team_organization_id=other),
        Play(name='Zebra live play', team_organization_id=other),
        TheoryTopic(section_id=section.id, name='Zebra draft topic', published=False, team_organization_id=other),
        TheoryTopic(section_id=section.id, name='Zebra live topic', published=True, team_organization_id=other),
        Clip(title='Zebra hidden clip', is_hidden=True, team_organization_id=other),
        Clip(title='Zebra open clip', is_hidden=False, team_organization_id=other),
    ])
    from app.models.team_organization import TeamOrganization
    player = make_user(db.session.get(TeamOrganization, other), 'other-player', 'player')
    db.session.commit()

    coach = page(client(app, teams, 'coach'), '/search?q=zebra')
    for name in ('draft play', 'live play', 'draft topic', 'live topic', 'hidden clip', 'open clip'):
        assert f'Zebra {name}' in coach, name
    as_player = page(stats_data.Client(app, player.id, other), '/search?q=zebra')
    for name in ('live play', 'live topic', 'open clip'):
        assert f'Zebra {name}' in as_player, name
    for name in ('draft play', 'draft topic', 'hidden clip'):
        assert f'Zebra {name}' not in as_player, name


def test_search_needs_a_login_and_two_letters(app, teams):
    assert app.test_client().get('/search?q=drill').status_code == 302
    c = client(app, teams)
    assert 'at least two letters' in page(c, '/search?q=d')
    # % and _ are searched for as typed, not as wildcards
    assert 'Nothing found' in page(c, '/search?q=%25%25')


# ── Result card ──────────────────────────────────────────────────

def test_result_card_link_is_made_and_stopped_by_a_coach(app, teams):
    game_id = teams['other_game']
    game = db.session.get(Game, game_id)
    game.our_score, game.their_score = 13, 9
    point = db.session.get(Point, teams['other_point'])
    db.session.add_all([
        Event(point_id=point.id, player_id=teams['other_player'], event_type='goal',
              team_organization_id=teams['other']),
        # another team's player on this game's events is never named
        Event(point_id=point.id, player_id=teams['herd_player'], event_type='block',
              team_organization_id=teams['other']),
    ])
    db.session.commit()
    c = client(app, teams, 'coach')
    assert 'Share the result' in page(c, f"/games/{game_id}")

    r = c.post(f"/games/{game_id}/share")
    assert r.status_code == 302 and f'/games/{game_id}' in r.headers['Location']
    db.session.expire_all()
    token = db.session.get(Game, game_id).share_token
    assert token and len(token) >= 20

    anyone = app.test_client()
    r = anyone.get(f'/games/result/{token}')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Other opponent' in html and '>13<' in html and 'noindex' in html
    assert 'Goals' in html and 'Blocks' not in html

    assert c.post(f"/games/{game_id}/share", data={'stop': '1'}).status_code == 302
    db.session.expire_all()
    assert db.session.get(Game, game_id).share_token is None
    assert anyone.get(f'/games/result/{token}').status_code == 404
    assert anyone.get('/games/result/short').status_code == 404


def test_result_card_cannot_be_made_for_another_teams_game(app, teams):
    herd_game = Game.query.filter_by(team_organization_id=teams['herd']).first()
    c = client(app, teams, 'coach')
    herd_game_id = herd_game.id
    assert c.post(f'/games/{herd_game_id}/share').status_code == 404
    db.session.expire_all()
    assert db.session.get(Game, herd_game_id).share_token is None


def test_public_name_is_first_name_and_initial():
    from app.routes.game import _public_name
    assert _public_name('Zoe Carter') == 'Zoe C.'
    assert _public_name('Ana Maria de Souza') == 'Ana S.'
    assert _public_name('Kai') == 'Kai' and _public_name(None) == ''


# ── Visitors, install, tour ──────────────────────────────────────

def test_visitors_get_their_own_navbar(app):
    html = app.test_client().get('/').get_data(as_text=True)
    assert 'What it does' in html and 'bi-book-fill' in html
    for menu in ('Team Roster', 'Drill Library', 'Game Stats', 'uc-tabbar'):
        assert menu not in html, menu


def test_manifest(app):
    r = app.test_client().get('/manifest.webmanifest')
    data = r.get_json(force=True)
    assert r.status_code == 200 and data['display'] == 'standalone' and data['start_url'] == '/'
    assert {i['sizes'] for i in data['icons']} == {'192x192', '512x512'}


def test_demo_tour_links_stay_in_the_team(app, teams):
    c = client(app, teams)
    r = c.get('/demo/tour/play')
    play = Play.query.filter_by(team_organization_id=teams['other']).first()
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/plays/{play.id}') or \
        str(play.id) in r.headers['Location']
    assert c.get('/demo/tour/session').status_code == 302
    assert c.get('/demo/tour/nowhere').status_code == 404
    assert app.test_client().get('/demo/tour/play').status_code == 302  # to the login page


# ── Sessions list ────────────────────────────────────────────────

def test_sessions_list_shows_replies_and_friendly_dates(app, teams):
    soon = date.today() + timedelta(days=1)
    plan = SessionPlan(title='Tomorrow session', date=soon, team_organization_id=teams['other'])
    db.session.add(plan)
    db.session.flush()
    db.session.add(SessionRSVP(session_id=plan.id, player_id=teams['other_player'], status='attending',
                               team_organization_id=teams['other']))
    db.session.commit()
    html = page(client(app, teams), '/sessions/')
    assert 'Tomorrow' in html and '<b>1</b> yes' in html
    assert 'Apply Filters' not in html and 'sessionFilters' in html
    filtered = page(client(app, teams), '/sessions/?focus_area=Other+focus')
    assert 'Clear 1 filter' in filtered
