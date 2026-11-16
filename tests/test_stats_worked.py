"""Stats checked against small games worked out by hand.

Each test records a few points through the stat-taker endpoints
(tests/worked_games.py) and checks the numbers the stats pages show. The
comments work every number out on paper, so a coach can follow them.

Positions are metres attacking the right-hand endzone: x runs 0-100 up the
field (the attacking endzone starts at 82), y 0-37 across.
"""
import pytest

from tests.worked_games import WorkedGame


# --- possessions -------------------------------------------------------------

@pytest.fixture
def possession_game(app):
    """Five points against one opponent.

    1. O point, hold:  A catches the pull, B, C scores.          no turns
    2. D point, break: they throw it away (unforced turnover), A, B throws
       it away, D blocks it, C, E scores.                          1 turn, 2 regains
    3. O point, broken: A, B drops it, they score.                 1 turn
    4. D point, break: F catches a Callahan.                      1 regain
    5. D point, their hold: they score.                           nothing
    """
    w = WorkedGame(app)
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 40, 18), ('goal', 'C', 90, 18)])
    w.point('D', [('unforced_turnover', 'opp', 60, 18), ('catch', 'A', 40, 18),
                  ('throwaway', 'B', 50, 10), ('block', 'D', 50, 10),
                  ('catch', 'C', 55, 12), ('goal', 'E', 88, 20)])
    w.point('O', [('catch', 'A', 20, 18), ('drop', 'B', 35, 20), ('scored_on', 'opp', 0, 18)])
    w.point('D', [('callahan', 'F', 15, 18)])
    w.point('D', [('scored_on', 'opp', 0, 18)])
    return w


def test_possessions_count_every_regain(possession_game):
    """Our possessions: 1 for receiving the pull, plus 1 for every time we
    win the disc back (block, forced or unforced turnover, Callahan).

        point 1 (O):  1 (the pull)                       = 1
        point 2 (D):  0 + unforced turnover + block      = 2
        point 3 (O):  1 (the pull)                       = 1
        point 4 (D):  0 + Callahan                       = 1
        point 5 (D):  0                                  = 0
                                                   total = 5
    We scored 3 goals (points 1, 2, 4), so possessions per goal = 5 / 3 = 1.67.
    (Before the fix only blocks counted as regains, and only possessions in
    points we scored: (1 + 1 + 0) / 3 = 0.67, fewer than one possession per
    goal, which can't happen.)

    Won back on D-line points: point 2 twice, point 4 once, point 5 none =
    3 over 3 D-line points = 1.00 per D-point. (Before: blocks only = 0.33.)
    """
    from app.stats.team import calculate_game_stats, calculate_possession_based_team_metrics
    w = possession_game
    ctx = w.context()
    try:
        game = calculate_game_stats(w.game())
        team = calculate_possession_based_team_metrics(w.games())
    finally:
        ctx.pop()
    assert game['possessions'] == 5
    assert game['possessions_gained'] == 3
    assert game['possessions_per_goal'] == pytest.approx(5 / 3)
    assert game['avg_possessions_gained_per_point'] == pytest.approx(1.0)
    assert team['possessions_per_goal'] == pytest.approx(5 / 3)
    assert team['avg_possessions_gained_per_point'] == pytest.approx(1.0)
    # Our turns: B's throwaway (point 2) and B's drop (point 3) = 2.
    assert game['turnovers'] == 2
    # Turnovers per O point: 1 (point 3) over 2 O points = 0.5
    assert team['avg_o_turnovers_per_point'] == pytest.approx(0.5)
    # Clean hold: point 1 of the 2 O points = 50%.
    # Clean break: point 4 (no turn) of the 3 D points = 33.3%.
    # Scored after a turnover of ours: point 2 = 1.
    assert team['clean_hold_percentage'] == pytest.approx(50)
    assert team['clean_break_percentage'] == pytest.approx(100 / 3)
    assert team['regain_offense_count'] == 1
    assert game['breaks'] == 2


def test_possessions_dont_depend_on_the_order_events_load(possession_game):
    """Counting the same events in reverse gives the same answer: possession
    follows the event types, not the order or the is_offensive flag."""
    from app.models.point import Point
    from app.stats.team import analyze_point_possessions
    w = possession_game
    point = Point.query.filter_by(game_id=w.game_id, point_number=2).one()
    events = sorted(point.events, key=lambda e: e.id)
    for e in events:
        e.is_offensive = True  # older points: the flag wasn't reliable
    forward = analyze_point_possessions(point, events)
    backward = analyze_point_possessions(point, list(reversed(events)))
    assert forward == backward == {'our_turnovers': 1, 'our_possessions': 2, 'possessions_gained': 2}


def test_scoring_efficiency_by_hand(possession_game):
    """SE = goals / (goals + turns), both teams, points with full stats.

    Goals: all 5 points ended in a goal                         = 5
    Turns: point 2 unforced turnover, throwaway, block (3);
           point 3 drop (1); point 4 the Callahan (1)          = 5
    SE = 5 / (5 + 5) = 0.5. Every point adds up, so none is left out.
    """
    from app.stats.team import calculate_scoring_efficiency
    w = possession_game
    ctx = w.context()
    try:
        se = calculate_scoring_efficiency(w.games())
    finally:
        ctx.pop()
    assert (se['se_goals'], se['se_turns'], se['se_incomplete']) == (5, 5, 0)
    assert se['se'] == pytest.approx(0.5)
