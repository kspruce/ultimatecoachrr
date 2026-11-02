"""Stored throws follow from the recorded events.

Every change to a point's events (recorded, undone, the point edited, a
player deleted) rebuilds its throws, so the Throw table never drifts:
no pass into a pickup, none from a substitution, none for a drop (the
receiver's turnover), and every throw has its distance."""
from flask_login import login_user

from app import db
from app.models.event import Event
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point
from app.models.throws import Throw
from app.models.user import User
from app.stats.team import calculate_additional_team_metrics
from app.stats.throw_rebuild import rebuild_point_throws
from tests.test_point_detail import _point, _record, setup  # noqa: F401


def _throws(point_id):
    db.session.expire_all()
    return [(t.throw_type, t.thrower_id, t.receiver_id, t.is_completion)
            for t in Throw.query.filter_by(point_id=point_id).order_by(Throw.id)]


def test_no_pass_into_a_pickup(setup):
    a, b, c, d, e, f = setup['line'][:6]
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'catch', 1, 35, 10, True)
    _record(setup, point_id, 'throwaway', 1, 60, 30, True)
    _record(setup, point_id, 'block', 2, 40, 20, False)        # c gets the D
    _record(setup, point_id, 'catch', 3, 42, 20, True)         # d picks up
    _record(setup, point_id, 'catch', 4, 60, 18, True)
    _record(setup, point_id, 'catch', 0, 75, 15, True)
    _record(setup, point_id, 'goal', 5, 88, 18, True)

    assert _throws(point_id) == [
        ('regular', a, b, True), ('throwaway', b, None, False),
        ('regular', d, e, True), ('hockey_assist', e, a, True), ('assist', a, f, True)]
    # Not credited to the blocker, and every throw has its distance
    assert Throw.query.filter_by(thrower_id=c).count() == 0
    assert all(t.distance for t in Throw.query.filter_by(point_id=point_id))


def test_opponent_turnover_then_pickup(setup):
    point_id = _point(setup, start='defense')
    _record(setup, point_id, 'unforced_turnover', 'opponent', 30, 20, False)
    _record(setup, point_id, 'catch', 2, 30, 20, True)
    _record(setup, point_id, 'catch', 3, 50, 20, True)
    assert _throws(point_id) == [('regular', setup['line'][2], setup['line'][3], True)]


def test_a_drop_is_not_an_incomplete_throw(setup):
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'drop', 1, 40, 10, True)
    # The receiver's turnover; nothing for the thrower
    assert _throws(point_id) == []


def test_substitution_isnt_in_the_chain(setup):
    a, b, sub = setup['line'][0], setup['line'][1], setup['line'][6]
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    r = setup['client'].post(f'/stats/substitute_player/{point_id}',
                             json={'player_out_id': sub, 'player_in_id': sub})
    assert r.status_code == 200
    _record(setup, point_id, 'catch', 1, 40, 18, True)
    _record(setup, point_id, 'catch', 2, 60, 18, True)
    _record(setup, point_id, 'goal', 3, 85, 18, True)

    assert _throws(point_id)[0] == ('regular', a, b, True)
    assert Throw.query.filter_by(thrower_id=sub).count() == 0
    # The goal still finds its assist and hockey assist across the sub
    types = [e.event_type for e in Event.query.filter_by(point_id=point_id).order_by(Event.id)]
    assert types == ['catch', 'substitution', 'hockey_assist', 'assist', 'goal']


def test_undo_and_redo_a_goal(setup):
    point_id = _point(setup)
    for i, x in enumerate((20, 40, 60)):
        _record(setup, point_id, 'catch', i, x, 18, True)
    _record(setup, point_id, 'goal', 3, 85, 18, True)
    scored = _throws(point_id)
    assert [t[0] for t in scored] == ['regular', 'hockey_assist', 'assist']

    assert setup['client'].post(f'/stats/undo_event/{point_id}').status_code == 200
    assert [t[0] for t in _throws(point_id)] == ['regular', 'regular']
    assert [e.event_type for e in Event.query.filter_by(point_id=point_id)] == ['catch'] * 3

    _record(setup, point_id, 'goal', 3, 85, 18, True)
    assert _throws(point_id) == scored


def test_editing_the_point_rebuilds_its_throws(setup):
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 5, True)
    _record(setup, point_id, 'catch', 1, 40, 25, True)    # across the field
    db.session.expire_all()
    throw = Throw.query.filter_by(point_id=point_id).one()
    assert throw.force_direction == 'forehand'
    breaks_on_forehand = throw.break_throw

    point = db.session.get(Point, point_id)
    point.force_direction = 'backhand'
    rebuild_point_throws(point)
    db.session.commit()
    throw = Throw.query.filter_by(point_id=point_id).one()
    assert throw.force_direction == 'backhand' and throw.break_throw is (not breaks_on_forehand)


def test_rebuild_repairs_throws_saved_by_older_versions(setup):
    point_id = _point(setup)
    a, b, c, d = setup['line'][:4]
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'throwaway', 0, 60, 30, True)
    _record(setup, point_id, 'block', 2, 40, 20, False)
    _record(setup, point_id, 'catch', 3, 42, 20, True)
    good = _throws(point_id)
    # What the old recorder saved: a pass from the blocker into the pickup,
    # and a duplicate with no distance
    db.session.add_all([
        Throw(point_id=point_id, thrower_id=c, receiver_id=d, throw_type='regular', is_completion=True,
              x_start=40, y_start=20, x_end=42, y_end=20, team_organization_id=setup['team_id']),
        Throw(point_id=point_id, thrower_id=a, receiver_id=None, throw_type='throwaway', is_completion=False,
              team_organization_id=setup['team_id']),
    ])
    db.session.commit()

    r = setup['client'].post('/stats/admin/rebuild_throws')
    assert r.status_code == 302
    assert _throws(point_id) == good


def test_rebuild_command(app, setup):
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'catch', 1, 40, 18, True)
    Throw.query.filter_by(point_id=point_id).delete()
    db.session.commit()

    result = app.test_cli_runner().invoke(args=['rebuild-throws', '--dry-run'])
    assert '1 throws replaced' not in result.output and 'Dry run' in result.output
    assert _throws(point_id) == []
    result = app.test_cli_runner().invoke(args=['rebuild-throws'])
    assert result.exit_code == 0, result.output
    assert len(_throws(point_id)) == 1


def test_deleting_a_player_keeps_their_plays(setup):
    a, b, c = setup['line'][:3]
    point_id = _point(setup, outcome='scored')
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'catch', 1, 40, 18, True)
    _record(setup, point_id, 'goal', 2, 85, 18, True)

    r = setup['client'].post(f'/team/delete_player/{b}')
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(Player, b) is None
    events = Event.query.filter_by(point_id=point_id).order_by(Event.id).all()
    assert [(e.event_type, e.player_id) for e in events] == [
        ('hockey_assist', a), ('assist', None), ('goal', c)]
    assert events[1].is_unknown_player
    # The passes are still there, now with an unknown player
    assert _throws(point_id) == [('hockey_assist', a, None, True), ('assist', None, c, True)]


def test_positions_are_kept_on_the_pitch(setup):
    point_id = _point(setup)
    event = Event(point_id=point_id, event_type='catch', player_id=setup['line'][0],
                  field_position_x=104.0, field_position_y=-3.0, team_organization_id=setup['team_id'])
    assert (event.field_position_x, event.field_position_y) == (100.0, 0.0)


def test_catch_rate_and_turnovers_forced(app, setup):
    point_id = _point(setup, start='defense')
    _record(setup, point_id, 'forced_turnover', 2, 40, 20, False)
    _record(setup, point_id, 'catch', 0, 40, 20, True)
    _record(setup, point_id, 'drop', 1, 50, 20, True)
    _record(setup, point_id, 'block', 3, 45, 20, False)
    _record(setup, point_id, 'catch', 0, 45, 20, True)
    _record(setup, point_id, 'catch', 1, 60, 20, True)
    _record(setup, point_id, 'catch', 4, 70, 20, True)
    _record(setup, point_id, 'goal', 5, 88, 20, True)

    admin = User.query.filter_by(username='admin').one()
    with app.test_request_context():
        login_user(admin)
        metrics = calculate_additional_team_metrics([db.session.get(Game, setup['game_id'])])
    # 5 catches (two catches, the hockey assist, the assist and the goal)
    # and 1 drop; only 'catch' events used to count (2 of 3)
    assert round(metrics['catch_rate'], 1) == round(500 / 6, 1)
    # The forced turnover and the block
    assert metrics['turnovers_forced_per_point'] == 2
