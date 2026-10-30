"""Search boxes, filter dropdowns and posted ids never reach another team's data.

Herd 2028's admin (and coach) try to see or use Thundering Herd's tournaments,
focus areas, plays, fitness metrics, clips and players.
"""
import pytest

from app import db
from app.models.clip import Clip, ClipPointSegment
from app.models.drill import SavedDrill
from app.models.event import Event
from app.models.fitness import FitnessMetric
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.onboarding import UserOnboarding
from app.models.playbook import Play
from app.models.point import Point
from app.models.session import Attendance, SessionPlan
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.user import User
from tests import stats_data


def make_user(team, username, role):
    user = User(username=username, email=f'{username}@example.com', role=role,
                team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    return user


@pytest.fixture
def teams(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    herd_player = stats_data.build_players(herd, 1)[0]
    other_player = stats_data.build_players(other, 1)[0]

    herd_game = Game(opponent='Herd opponent', team_organization_id=herd.id)
    other_game = Game(opponent='Other opponent', team_organization_id=other.id)
    db.session.add_all([herd_game, other_game])
    db.session.flush()
    herd_clip = Clip(title='Herd clip', game_id=herd_game.id, team_organization_id=herd.id)
    db.session.add(herd_clip)
    db.session.flush()
    segment = ClipPointSegment(clip_id=herd_clip.id, point_number=1, start_time=0,
                               team_organization_id=herd.id)
    other_point = Point(game_id=other_game.id, point_number=1, our_line_type='O-line',
                        starting_position='offense', team_organization_id=other.id)
    herd_session = SessionPlan(title='Herd session', focus_area='Herd secret focus',
                               team_organization_id=herd.id)
    other_session = SessionPlan(title='Other session', focus_area='Other focus',
                                team_organization_id=other.id)
    other_tournament = Tournament(name='Other tour', team_organization_id=other.id)
    db.session.add_all([
        segment, other_point, herd_session, other_session, other_tournament,
        Tournament(name='Herd secret tour', team_organization_id=herd.id),
        Play(name='Herd secret play', team_organization_id=herd.id),
        Play(name='Other play', team_organization_id=other.id),
        SavedDrill(title='Herd secret huck drill', team_organization_id=herd.id),
        SavedDrill(title='Huck drill', skill_level='advanced', team_organization_id=other.id),
        SavedDrill(title='Zone drill', skill_level='beginner', team_organization_id=other.id),
    ])
    herd_metric = FitnessMetric(name='Herd secret sprint', unit='s', team_organization_id=herd.id)
    shared_metric = FitnessMetric(name='Shared beep test', unit='lvl', team_organization_id=None)
    db.session.add_all([herd_metric, shared_metric])
    admin = make_user(other, 'other-admin', 'admin')
    coach = make_user(other, 'other-coach', 'coach')
    db.session.commit()
    return {
        'herd': herd.id, 'other': other.id,
        'herd_player': herd_player.id, 'other_player': other_player.id,
        'herd_clip': herd_clip.id, 'segment': segment.id,
        'other_game': other_game.id, 'other_point': other_point.id,
        'herd_session': herd_session.id, 'other_session': other_session.id,
        'other_tournament': other_tournament.id,
        'herd_metric': herd_metric.id,
        'admin': admin.id, 'coach': coach.id,
    }


def client(app, teams, who='admin'):
    return stats_data.Client(app, teams[who], teams['other'])


def page(c, url):
    r = c.get(url)
    assert r.status_code == 200, url
    return r.get_data(as_text=True)


def test_filter_dropdowns_only_list_your_team(app, teams):
    c = client(app, teams)
    assert 'Herd secret tour' not in page(c, '/scouting/')
    sessions = page(c, '/sessions/')
    assert 'Other focus' in sessions and 'Herd secret focus' not in sessions
    component = page(c, f"/sessions/{teams['other_session']}/add_component")
    assert 'Other play' in component and 'Herd secret play' not in component


def test_fitness_only_offers_the_standard_tests(app, teams):
    c = client(app, teams)
    body = page(c, f"/fitness/player/{teams['other_player']}")
    assert '10 m Sprint' in body and 'Herd secret sprint' not in body
    metric = teams['herd_metric']
    assert c.get(f'/fitness/test-day?metric_id={metric}').status_code == 404
    assert c.post(f"/fitness/record/{teams['other_player']}",
                  data={'metric_id': metric, 'value': '5'}).status_code == 404


def test_cannot_delete_another_teams_clip_segment(app, teams):
    c = client(app, teams)
    with app.app_context():
        r = c.client.delete(f"/clips/{teams['herd_clip']}/segments/{teams['segment']}")
    assert r.status_code == 404
    assert db.session.get(ClipPointSegment, teams['segment']) is not None


def test_stats_cannot_credit_another_teams_player(app, teams):
    c = client(app, teams)
    r = c.post(f"/stats/record/{teams['other_point']}",
               json={'player_id': teams['herd_player'], 'event_type': 'catch'})
    assert r.status_code == 404
    assert Event.query.count() == 0


def test_selections_drop_another_teams_players(app, teams):
    c = client(app, teams)
    both = [teams['herd_player'], teams['other_player']]
    c.post(f"/games/{teams['other_game']}/update_players", data={'player_ids': both})
    assert {gp.player_id for gp in GamePlayer.query.all()} == {teams['other_player']}

    c.post(f"/tournaments/{teams['other_tournament']}/update_selections",
           data={'selected_players': both})
    assert {r.player_id for r in TournamentRSVP.query.all()} == {teams['other_player']}


def test_quick_checkin_is_for_your_own_session_and_players(app, teams):
    url = f"/sessions/{teams['other_session']}/quick_checkin"
    c = client(app, teams)
    assert c.post(url, json={'player_id': teams['herd_player'], 'status': 'present'}).status_code == 404
    assert c.post(f"/sessions/{teams['herd_session']}/quick_checkin",
                  json={'player_id': teams['other_player'], 'status': 'present'}).status_code == 404
    assert Attendance.query.count() == 0

    # Admins only (it's the register's tap-to-mark)
    client(app, teams, 'coach').post(url, json={'player_id': teams['other_player'], 'status': 'present'})
    assert Attendance.query.count() == 0

    assert c.post(url, json={'player_id': teams['other_player'], 'status': 'present'}).status_code == 200
    assert Attendance.query.one().player_id == teams['other_player']


def test_drill_search_filters_your_library(app, teams):
    c = client(app, teams, 'coach')
    everything = page(c, '/sessions/drills')
    assert 'Huck drill' in everything and 'Zone drill' in everything
    assert 'Herd secret' not in everything

    found = page(c, '/sessions/drills?q=huck')
    assert 'Huck drill' in found and 'Zone drill' not in found and 'Herd secret' not in found
    beginner = page(c, '/sessions/drills?skill_level=beginner')
    assert 'Zone drill' in beginner and 'Huck drill' not in beginner


def test_sections_and_tags_are_named_per_team(app, teams):
    from app.models.playbook import PlayTag
    from app.models.theory import TheorySection, TheoryTag
    db.session.add_all([
        TheorySection(name='Defence', slug='defence', team_organization_id=teams['herd']),
        TheoryTag(name='Zone', team_organization_id=teams['herd']),
        PlayTag(name='Herd secret tag', team_organization_id=teams['herd']),
    ])
    db.session.commit()

    c = client(app, teams, 'coach')
    for _ in range(2):
        assert c.post('/theory/add_section', data={'name': 'Defence'}).status_code == 302
    mine = TheorySection.query.filter_by(team_organization_id=teams['other']).order_by(TheorySection.id)
    assert [s.slug for s in mine] == ['defence', 'defence-2']
    assert 'Defence' in page(c, '/theory/section/defence')

    # The same tag names can be used by both teams
    db.session.add_all([TheoryTag(name='Zone', team_organization_id=teams['other']),
                        PlayTag(name='Herd secret tag', team_organization_id=teams['other'])])
    db.session.commit()
    assert TheoryTag.query.filter_by(name='Zone').count() == 2

    # The play form only offers your own tags
    other_tag = PlayTag.query.filter_by(team_organization_id=teams['other']).one()
    herd_tag = PlayTag.query.filter_by(team_organization_id=teams['herd']).one()
    form = page(client(app, teams), '/playbook/plays/add')
    assert f'value="{other_tag.id}"' in form and f'value="{herd_tag.id}"' not in form
