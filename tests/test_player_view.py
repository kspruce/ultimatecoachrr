"""Player view: coaches, captains and admins see the site as a player does,
with none of their higher access, and switch back. A coach who doesn't play
previews as a roster player instead, look-only."""
import pytest

from app import db
from app.models.feedback import PlayerFeedback
from app.models.team_role import PlayerRole
from app.models.user import User
from app.models.playbook import PlayerPosition
from tests import stats_data
from tests.test_feedback import make_user


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    players = stats_data.build_players(team, 4)
    coach = make_user(team, 'coach', 'coach')                      # doesn't play
    captain = make_user(team, 'captain', 'captain', players[1])    # plays
    ann = make_user(team, 'ann', 'player', players[0])
    boss = make_user(team, 'boss', 'admin')
    boss.is_superadmin = True
    db.session.add(PlayerFeedback(player_id=players[0].id, coach_id=coach.id, shared=True,
                                  content='Great hucks'))
    db.session.add(PlayerPosition(team_organization_id=team.id, name='Deep'))
    db.session.commit()
    return {'team': team.id, 'other': other.id, 'players': [p.id for p in players],
            'coach': stats_data.Client(app, coach.id, team.id),
            'captain': stats_data.Client(app, captain.id, team.id),
            'ann': stats_data.Client(app, ann.id, team.id),
            'boss': stats_data.Client(app, boss.id, team.id)}


def text(r):
    return r.get_data(as_text=True)


def test_menu_offers_player_view_to_coaches_not_players(app, club):
    assert 'Player View' in text(club['captain'].get('/'))
    assert 'Player View' in text(club['coach'].get('/'))
    assert 'Player View' not in text(club['ann'].get('/'))
    assert club['ann'].get('/player-view/').status_code == 403
    assert club['ann'].post('/player-view/start', data={'player': 'me'}).status_code == 403


def test_captain_loses_their_access_until_they_leave(app, club):
    c = club['captain']
    assert c.get('/team/roles/').status_code == 200
    c.post('/player-view/start', data={'player': 'me'})
    home = text(c.get('/'))
    assert 'Exit player view' in home and 'User Management' not in home
    r = c.get('/team/roles/')
    assert r.status_code == 302  # coaches only
    c.post('/player-view/stop')
    assert c.get('/team/roles/').status_code == 200
    assert 'Exit player view' not in text(c.get('/'))


def test_playing_coach_keeps_their_own_profile_and_can_act_as_themselves(app, club):
    c = club['captain']
    deep = PlayerPosition.query.filter_by(name='Deep').one()
    c.post('/player-view/start', data={'player': 'me'})
    c.post(f"/team/roles/player/{club['players'][1]}", data={'kind': 'preferred', 'role_id': deep.id})
    assert PlayerRole.query.filter_by(kind='preferred').count() == 1


def test_non_playing_coach_previews_as_a_player_look_only(app, club):
    c = club['coach']
    page = text(c.get('/player-view/'))
    assert 'Choose a player' in page and 'Herd Player 01' in page
    c.post('/player-view/start', data={'player': club['players'][0]})
    assert 'seeing the site as Herd Player 01' in text(c.get('/'))
    mine = c.get('/feedback/mine')
    assert mine.status_code == 200 and 'Great hucks' in text(mine)
    db.session.expire_all()
    assert PlayerFeedback.query.one().seen_at is None  # still new for Ann
    # Nothing is saved on their behalf
    deep = PlayerPosition.query.filter_by(name='Deep').one()
    r = c.post(f"/team/roles/player/{club['players'][0]}", data={'kind': 'preferred', 'role_id': deep.id})
    assert r.status_code == 302
    assert PlayerRole.query.count() == 0
    # ... nor as a coach
    assert c.get('/team/roles/').status_code == 302
    # They can switch who they see, or leave
    assert c.get('/player-view/').status_code == 200
    c.post('/player-view/stop')
    assert c.get('/team/roles/').status_code == 200


def test_preview_as_an_unlinked_player(app, club):
    c = club['coach']
    c.post('/player-view/start', data={'player': 'none'})
    assert 'no linked profile' in text(c.get('/'))
    assert c.get('/feedback/mine').status_code == 404


def test_cant_preview_another_teams_player(app, club):
    from app.models.team_organization import TeamOrganization
    other_player = stats_data.build_players(db.session.get(TeamOrganization, club['other']), 1)[0]
    c = club['coach']
    c.post('/player-view/start', data={'player': other_player.id})
    assert 'Exit player view' not in text(c.get('/'))


def test_superadmin_powers_are_off_too(app, club):
    c = club['boss']
    assert c.get('/admin/enhanced-data-management').status_code == 200
    c.post('/player-view/start', data={'player': 'none'})
    assert c.get('/admin/enhanced-data-management').status_code == 302
    home = text(c.get('/'))
    assert 'Thundering Herd' in home  # still on the same team
    c.post('/player-view/stop')
    assert c.get('/admin/enhanced-data-management').status_code == 200
    # The real flag is untouched, and still queryable
    assert User.query.filter_by(is_superadmin=True).count() == 1
    assert User.query.filter(User.is_superadmin.is_(True)).one().username == 'boss'


def test_other_peoples_roles_are_unaffected(app, club):
    c = club['captain']
    c.post('/player-view/start', data={'player': 'me'})
    with app.test_request_context():
        from flask import session
        captain = User.query.filter_by(username='captain').one()
        coach = User.query.filter_by(username='coach').one()
        session['player_view'] = {'user': captain.id, 'player': None}
        assert captain.role_in(club['team']) == 'player'
        assert captain.real_role_in(club['team']) == 'captain'
        assert coach.role_in(club['team']) == 'coach'


def test_record_is_only_in_the_menu_for_stat_takers_and_up(app, club):
    record = 'bi-record-circle-fill'
    assert record in text(club['coach'].get('/'))
    assert record not in text(club['ann'].get('/'))
    club['coach'].post('/player-view/start', data={'player': 'none'})
    assert record not in text(club['coach'].get('/'))
