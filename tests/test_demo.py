"""The demo team (flask seed-demo): built with a season of everything, a
"Try the demo" button that signs anyone in as its coach, every page of it
opens, and nothing the demo login does is saved."""
import re
from datetime import date

import pytest

from app import db
from app.demo import DEMO_PASSWORD, DEMO_USERNAME, build, demo_team, demo_user, remove
from app.models.drill import SavedDrill
from app.models.game import Game
from app.models.player import Player
from app.models.playbook import Play
from app.models.session import SessionPlan
from app.models.user import User
from tests import stats_data

SKIP = re.compile(r'pdf|discord|youtube|/auth/logout|download|/export', re.I)


@pytest.fixture
def demo(app):
    team = build(app, today=date(2026, 11, 2))
    return team.id


class _Client:
    """A browser: each request in its own app context, as in production."""

    def __init__(self, app):
        self.app, self.client = app, app.test_client()

    def get(self, url, **kw):
        with self.app.app_context():
            return self.client.get(url, **kw)

    def post(self, url, **kw):
        with self.app.app_context():
            return self.client.post(url, **kw)


def _demo_client(app):
    client = _Client(app)
    page = client.get('/auth/login').get_data(as_text=True)
    assert 'Try the demo' in page
    r = client.post('/auth/demo')
    assert r.status_code == 302
    return client


def test_demo_team_has_a_season_of_everything(app, demo):
    team = demo_team()
    assert team.slug == 'demo'
    assert Player.query.filter_by(team_organization_id=demo).count() == 18
    assert SessionPlan.query.filter_by(team_organization_id=demo).count() == 10
    plays = Play.query.filter_by(team_organization_id=demo).all()
    assert len(plays) == 4 and all(p.stage_count >= 2 for p in plays)
    assert SavedDrill.query.filter_by(team_organization_id=demo).count() == 8
    games = Game.query.filter_by(team_organization_id=demo).all()
    played = [g for g in games if g.our_score + g.their_score]
    assert len(played) == 6 and all(max(g.our_score, g.their_score) == 13 for g in played)
    assert len(games) == 9  # and the next tournament's schedule
    # A clip library and a film session, every clip cut from the demo video
    from app.models.clip import Clip
    from app.models.clip_playlist import ClipPlaylist
    clips = Clip.query.filter_by(team_organization_id=demo).all()
    assert len(clips) == 6 and all('1x5QW8DQFaE' in c.embed_url and c.tags and c.players for c in clips)
    playlist = ClipPlaylist.query.filter_by(team_organization_id=demo).one()
    assert len(playlist.items) == 6
    user = demo_user()
    assert user.username == DEMO_USERNAME and user.check_password(DEMO_PASSWORD)
    assert user.is_demo and user.is_guest and user.team_ids == [demo]


def test_try_the_demo_signs_in_as_the_coach_and_every_page_opens(app, demo):
    app.config['PROPAGATE_EXCEPTIONS'] = False
    client = _demo_client(app)
    home = client.get('/').get_data(as_text=True)
    assert 'Riverside Kites' in home and 'nothing you change is saved' in home
    assert 'Harbour Hawks' in home  # the next game

    play = Play.query.filter_by(team_organization_id=demo).first()
    detail = client.get(f'/playbook/plays/{play.id}')
    assert detail.status_code == 200 and b'"stages"' in detail.data
    image = client.get(play.editor_diagram.image_url)
    assert image.status_code == 200 and image.data.startswith(b'\x89PNG')

    failures = []
    rules = sorted({r.rule for r in app.url_map.iter_rules()
                    if 'GET' in r.methods and not r.rule.startswith('/static')})
    for rule in rules:
        if SKIP.search(rule):
            continue
        url = re.sub(r'<(?:int:)?\w+>', '1', rule)
        url = re.sub(r'<(?:string|path):\w+>', 'x', url)
        response = client.get(url)
        if response.status_code >= 500:
            failures.append(f'{response.status_code} {url}')
    assert not failures, '\n'.join(failures)


def test_the_demo_login_cannot_change_anything(app, demo):
    client = _demo_client(app)
    session = SessionPlan.query.filter_by(team_organization_id=demo).first()
    title = session.title
    r = client.post(f'/sessions/edit/{session.id}', data={'title': 'Hacked'})
    assert r.status_code == 302
    client.post('/auth/account', data={'email': 'me@example.com'})
    r = client.post(f'/sessions/{session.id}/rsvp', json={'status': 'attending'})
    assert r.status_code == 403
    assert client.get('/discord/connect').status_code == 302
    assert client.get(f'/sessions/{session.id}/generate-share-link').status_code == 302
    db.session.expire_all()
    assert db.session.get(SessionPlan, session.id).title == title
    assert db.session.get(SessionPlan, session.id).share_token is None
    assert demo_user().email is None and demo_user().check_password(DEMO_PASSWORD)


def test_no_demo_button_without_a_demo_team(app):
    client = _Client(app)
    assert b'Try the demo' not in client.get('/auth/login').data
    assert client.post('/auth/demo').status_code == 302


def test_reset_rebuilds_and_leaves_other_teams_alone(app, demo):
    other = stats_data.build_team('Thundering Herd', 'herd')
    stats_data.build_players(other, 3)
    assert remove(app)
    assert demo_team() is None and User.query.filter_by(username=DEMO_USERNAME).first() is None
    assert Player.query.filter_by(team_organization_id=other.id).count() == 3
    team = build(app, record_games=False)
    assert team.slug == 'demo' and demo_user().team_ids == [team.id]
    with pytest.raises(ValueError):
        build(app)


def test_games_record_with_csrf_protection_on(app):
    # As on the live site, where the superadmin's button builds it
    app.config['WTF_CSRF_ENABLED'] = True
    team = build(app)
    games = Game.query.filter_by(team_organization_id=team.id).all()
    assert sum(1 for g in games if g.our_score + g.their_score) == 6


def test_superadmin_sets_up_and_removes_the_demo_from_the_teams_page(app):
    from tests.test_teams import make_user
    home = stats_data.build_team('Thundering Herd', 'herd')
    boss = make_user(home, 'boss', role='admin', superadmin=True)
    coach = make_user(home, 'herdcoach', role='coach')
    assert stats_data.Client(app, coach.id, home.id).post('/teams/demo').status_code == 302
    assert demo_team() is None  # coaches can't

    client = stats_data.Client(app, boss.id, home.id)
    assert b'Set up the demo team' in client.get('/teams/').data
    client.post('/teams/demo', data={'action': 'build'})
    assert demo_team() is not None and b'Rebuild demo' in client.get('/teams/').data
    client.post('/teams/demo', data={'action': 'build'})  # rebuilt, not doubled
    assert demo_user().team_ids == [demo_team().id]
    assert Player.query.filter_by(team_organization_id=demo_team().id).count() == 18
    assert Game.query.filter_by(team_organization_id=demo_team().id).count() == 9
    client.post('/teams/demo', data={'action': 'remove'})
    assert demo_team() is None and demo_user() is None
    assert db.session.get(type(home), home.id) is not None


def test_throws_saved_without_a_team_dont_stop_it_being_removed(app):
    # Throws recorded before they were stamped with their team (as on the
    # live site): deleting the team must take them too, and only them
    from app.models.throws import Throw
    other = stats_data.build_team('Thundering Herd', 'herd')
    admin = stats_data.build_admin(other, 'herdadmin')
    stats_data.record_season(app, other, admin, stats_data.build_players(other, 14),
                             games_per_tournament=1, points_per_game=2)
    team = build(app)
    assert Throw.query.filter_by(team_organization_id=team.id).count() > 0  # stamped now
    theirs = Throw.query.filter_by(team_organization_id=other.id).count()
    db.session.execute(Throw.__table__.update().values(team_organization_id=None))
    db.session.commit()
    assert remove(app)
    assert Throw.query.count() == theirs and demo_team() is None
