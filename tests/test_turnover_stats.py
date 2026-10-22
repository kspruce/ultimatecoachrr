"""Where turnovers happen (rates by throw, side, zone and situation), the
focus areas and trends built on them, and cuts worked out from catches."""
import pytest

from app import db
from app.models.cutting_skill import CuttingSkill
from app.models.point import Point
from app.models.throws import Throw
from app.stats import turnovers
from app.stats.throwing import direction, is_break_throw, throw_kind
from tests.test_point_setup import _line, _save, setup  # noqa: F401
from tests.test_stats import season  # noqa: F401


# --- classification (no database) ------------------------------------------

@pytest.mark.parametrize('force, y_end, expected', [
    ('forehand', 25, False),   # to the thrower's right: the open side on a forehand force
    ('forehand', 10, True),    # across to their left: a break
    ('backhand', 25, True),
    ('backhand', 10, False),
    ('forehand', 16.5, False), # only 1.5 m across the mark
    ('middle', 4, True),       # forced middle, thrown to the near (left) sideline
    ('middle', 30, False),
    ('zone', 30, None),
    ('unknown', 30, None),
    (None, 30, None),
])
def test_break_side_comes_from_the_force(force, y_end, expected):
    assert is_break_throw(40, 15, 50, y_end, force) is expected


def test_break_needs_positions():
    assert is_break_throw(None, 15, 50, 20, 'forehand') is None


def test_throw_kinds_and_directions():
    assert throw_kind(50, 18, 49, 30) == 'dump_swing'
    assert throw_kind(50, 18, 60, 18) == 'short'
    assert throw_kind(50, 18, 67, 18) == 'mid'
    assert throw_kind(30, 18, 60, 20) == 'huck'
    assert direction(50, 18, 60, 18) == 'E'   # straight upfield
    assert direction(50, 18, 50, 28) == 'N'   # the thrower's right
    assert direction(50, 18, 50, 8) == 'S'
    assert direction(50, 18, 40, 18) == 'W'


def _data(throws):
    """ThrowingData with hand-made throws and no events."""
    data = turnovers.ThrowingData.__new__(turnovers.ThrowingData)
    data.throws, data.events_by_point, data.points, data.game_of_point = throws, {}, {}, {}
    return data


def _throw(thrower, kind, turnover, side='open'):
    return {'thrower_id': thrower, 'receiver_id': None if turnover else 99, 'game_id': 1,
            'point_id': 1, 'turnover': turnover, 'kind': kind, 'side': side,
            'depth': 'middle_third', 'lane': 'centre', 'line': 'O-line', 'score': 'close',
            'half': 'first', 'x_start': 40, 'y_start': 18, 'x_end': 70, 'y_end': 18,
            'throwing_event_id': None}


def test_focus_area_is_the_bucket_furthest_below_the_team():
    throws = ([_throw(1, 'huck', i < 5) for i in range(10)]          # 50% on hucks
              + [_throw(1, 'short', False) for _ in range(10)]
              + [_throw(2, 'huck', i < 1) for i in range(20)]         # team mate 95%
              + [_throw(2, 'short', i < 1) for i in range(20)])
    focus = turnovers.focus_areas(_data(throws), 1)
    assert focus['weak'][0]['text'] == 'Hucks'
    assert focus['weak'][0]['completion_rate'] == 50
    assert focus['weak'][0]['extra_turnovers'] > 2
    # Player 2 is better than the team on hucks: a strength, not a weakness
    assert not turnovers.focus_areas(_data(throws), 2)['weak'] or \
        turnovers.focus_areas(_data(throws), 2)['weak'][0]['text'] != 'Hucks'


def test_small_samples_are_not_focus_areas():
    throws = [_throw(1, 'huck', True) for _ in range(3)] + [_throw(2, 'huck', False) for _ in range(30)]
    assert turnovers.focus_areas(_data(throws), 1)['weak'] == []


def test_rolling_average_skips_missing_games():
    assert turnovers._rolling([1, None, 3, 5]) == [1, 1, 2, 4]


# --- recorded season --------------------------------------------------------

def test_recorded_throws_are_marked_open_or_break(app, season):
    sides = {t.break_throw for t in Throw.query.all()}
    assert True in sides and False in sides


def test_re_marking_break_throws_uses_the_point_force(app, season):
    point = Point.query.filter(Point.throws.any()).first()
    point.force_direction = 'zone'
    db.session.commit()
    point_id = point.id
    r = season['client'].post('/stats/admin/mark_break_throws')
    assert r.status_code == 302
    db.session.expire_all()
    assert {t.break_throw for t in Throw.query.filter_by(point_id=point_id)} == {None}


def test_player_page_shows_the_improvement_sections(app, season):
    page = season['client'].get(f"/stats/player/{season['player_ids'][0]}").get_data(as_text=True)
    for text in ['Focus Areas', 'Ball Security', 'Turnover Map', 'Completion by Throw and Situation',
                 'Completion by Field Zone', 'Ball Security Trend', 'Which way you throw',
                 'Cuts thrown to', 'vs your earlier games']:
        assert text in page, text
    # The page's own styles and scripts are in the base template's block
    assert 'heatmap.min.js' in page and '.cutting-grid' in page


def test_team_page_shows_the_turnover_sections(app, season):
    page = season['client'].get('/stats/team').get_data(as_text=True)
    for text in ['Practice Focus', 'What Turnovers Cost', 'Where Turnovers Come From',
                 'Ball Security by Player', 'teamBallSecurityChart']:
        assert text in page, text


def test_filtered_pages_render(app, season):
    client = season['client']
    pid = season['player_ids'][3]
    for url in [f'/stats/player/{pid}?tournament_id=1', f'/stats/player/{pid}?game_id=2',
                '/stats/team?tournament_id=2', '/stats/team?season=2026']:
        assert client.get(url).status_code == 200, url


def test_turnover_cost_counts_every_turnover_with_a_position(app, season):
    from app.models.event import Event
    from app.models.game import Game
    with app.test_request_context():
        from flask_login import login_user
        from app.models.user import User
        login_user(User.query.first())
        data = turnovers.ThrowingData(Game.query.all())
        cost = turnovers.turnover_cost(data)
    ours = Event.query.filter(Event.event_type.in_(turnovers.OUR_TURNOVERS),
                              Event.is_offensive.is_(True)).count()
    assert cost['turnovers'] == ours
    assert 0 < cost['conceded'] <= ours


# --- stalls -----------------------------------------------------------------

def test_a_stall_is_recorded_and_counts_as_a_turnover(setup):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    a = _line()[0]
    client = setup['client']
    for event in ['catch', 'stall']:
        r = client.post(f'/stats/record/{point.id}', json={
            'player_id': str(a), 'event_type': event, 'field_position_x': 50,
            'field_position_y': 18, 'is_offensive': True})
        assert r.status_code == 201, r.get_data(as_text=True)
    page = client.get(f'/stats/player/{a}').get_data(as_text=True)
    assert 'Stalls 1' in page


# --- cuts -------------------------------------------------------------------

def test_one_tap_open_not_thrown_to_needs_no_position(setup):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    a, b = _line()[:2]
    client = setup['client']
    r = client.post(f'/stats/record_cutting_skill/{point.id}', json={
        'player_id': b, 'cutting_type': 'unspecified', 'outcome': 'open_looked_off'})
    assert r.status_code == 201, r.get_data(as_text=True)
    skill = CuttingSkill.query.one()
    assert skill.field_position_x is None and skill.cutting_type == 'unspecified'
    # b gets one upfield catch on the same point: used 1 of the 2 times open
    for pid, event, x in [(a, 'catch', 30), (b, 'catch', 42)]:
        client.post(f'/stats/record/{point.id}', json={
            'player_id': str(pid), 'event_type': event, 'field_position_x': x,
            'field_position_y': 18, 'is_offensive': True})
    page = client.get(f'/stats/player/{b}').get_data(as_text=True)
    assert 'Open, not thrown to' in page
    assert '<div class="cutting-stat-value">50%</div>' in page  # used when open
    # The recording screen has a chip for every player on the line
    record = client.get(f'/stats/record/{point.id}').get_data(as_text=True)
    assert record.count('class="looked-off-add"') == 7


def test_cuts_come_from_upfield_catches(app, season):
    from app.models.game import Game
    from app.stats.cutting import cut_profile, derived_cuts
    with app.test_request_context():
        from flask_login import login_user
        from app.models.user import User
        login_user(User.query.first())
        data = turnovers.ThrowingData(Game.query.all())
        pid = season['player_ids'][2]
        cuts = derived_cuts(data, pid)
        profile = cut_profile(data, pid)
    expected = [t for t in Throw.query.filter_by(receiver_id=pid, is_completion=True)
                if throw_kind(t.x_start, t.y_start, t.x_end, t.y_end) not in (None, 'dump_swing')]
    assert len(cuts) == len(expected) == profile['receptions']
    assert sum(q['thrown_to'] for q in profile['by_type'].values()) + profile['unknown_side'] == len(cuts)


def test_recorder_lists_players_by_kit_number_with_no_mode_switch(setup):
    from app.models.player import Player
    line = _line()  # men then women: not kit-number order
    _save(setup, line)
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    db.session.get(Player, line[0]).jersey_number = None  # no number goes last
    db.session.commit()
    page = setup['client'].get(f'/stats/record/{point.id}').get_data(as_text=True)
    grid = page.split('id="player-select"')[1].split('data-player-id="unknown"')[0]
    shown = [int(x) for x in __import__('re').findall(r'data-player-id="(\d+)"', grid)]
    numbers = {p.id: p.jersey_number for p in Player.query.filter(Player.id.in_(line))}
    expected = sorted(line, key=lambda pid: (numbers[pid] is None, numbers[pid] or 0))
    assert shown == expected and shown[-1] == line[0]
    assert 'mode-toggle' not in page and 'LOG CUT' in page
