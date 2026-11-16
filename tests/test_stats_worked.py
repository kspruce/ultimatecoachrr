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


# --- points without a result (the cap, half time) ---------------------------

def test_a_point_stopped_by_the_cap_is_neither_held_nor_broken(app):
    """1. O point: A, B scores.                  hold
    2. D point: they score.                      their hold
    3. O point: A, B... and the hard cap goes.   no result

    Hold % counts O points that ended in a goal: 1 held of 1 = 100%.
    (Before the fix point 3 counted as not held: 1 of 2 = 50%.)
    Break %: 0 of 1 = 0%. Clean holds: point 1 of 1 = 100%.
    Every player was on all three points, so each player's O-line
    conversion is 100% too, and they still played 3 points.
    """
    from app.stats import dashboard, turnovers
    from app.stats.players import get_players_base_stats
    from app.stats.team import (calculate_game_stats, calculate_possession_based_team_metrics,
                                calculate_team_summary)
    w = WorkedGame(app)
    w.point('O', [('catch', 'A', 20, 18), ('goal', 'B', 90, 18)])
    w.point('D', [('scored_on', 'opp', 0, 18)])
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 40, 18)], finish=False)
    ctx = w.context()
    try:
        games = w.games()
        summary = calculate_team_summary(games)
        game = calculate_game_stats(w.game())
        poss = calculate_possession_based_team_metrics(games)
        data = turnovers.ThrowingData(games)
        headline = dashboard.period_numbers(data, {w.game_id}, games)
        a = get_players_base_stats([w.players['A']], games)[w.ids['A']]
    finally:
        ctx.pop()
    assert summary['o_line_conversion_rate'] == pytest.approx(100)
    assert (summary['o_line_conversions'], summary['o_line_points']) == (1, 1)
    assert summary['d_line_conversion_rate'] == 0
    assert summary['total_points'] == 3
    assert game['o_line_conversion_rate'] == pytest.approx(100)
    assert game['unfinished_points'] == 1
    assert game['clean_hold_percentage'] == pytest.approx(100)
    assert poss['clean_hold_percentage'] == pytest.approx(100)
    assert headline['hold'] == pytest.approx(100) and headline['clean_hold'] == pytest.approx(100)
    assert headline['break'] == 0
    assert a['points_played'] == 3 and a['o_line_points_played'] == 2
    assert a['o_line_conversion_rate'] == pytest.approx(100)


# --- Callahans ---------------------------------------------------------------

def test_a_callahan_is_a_goal_and_a_block_everywhere(possession_game):
    """In the possession game F's only play is the Callahan on point 4, and
    D's only play is the block on point 2.

    F: goals 1 (the Callahan), blocks 1 (the Callahan), +/- = 1 + 1 = +2.
       On D-line points: 1 block in 3 D-points = 0.33 blocks per D-point.
    D: blocks 1, +/- +1.
    The team: goals = points 1, 2 and 4's goals = 3, over 5 points with full
    stats = 0.6 goals per point. Blocks on D-points = D's and F's = 2 over 3
    D-points = 0.67.
    (Before the fix F showed 0 goals, 0 blocks and +/- 0 on the dashboard,
    game page and exports, and the team counted 2 goals and 1 block.)
    """
    from app.stats.players import get_players_base_stats
    from app.stats.team import calculate_additional_team_metrics
    w = possession_game
    ctx = w.context()
    try:
        games = w.games()
        stats = get_players_base_stats(list(w.players.values()), games)
        team = calculate_additional_team_metrics(games)
    finally:
        ctx.pop()
    f, d = stats[w.ids['F']], stats[w.ids['D']]
    assert (f['total_goals'], f['total_blocks'], f['callahans'], f['plus_minus']) == (1, 1, 1, 2)
    assert f['d_line_plus_minus'] == 2
    assert f['blocks_per_d_point'] == pytest.approx(1 / 3)
    assert f['goals_per_point'] == pytest.approx(1 / 5)
    assert f['box']['goals'] == 1 and f['box']['blocks'] == 1
    assert (d['total_blocks'], d['plus_minus']) == (1, 1)
    assert team['goals_per_point'] == pytest.approx(3 / 5)
    assert team['blocks_per_point'] == pytest.approx(2 / 3)

    rows = {r['name']: r for r in w.client.get(
        f'/stats/api/player-stats?game_id={w.game_id}').get_json()}
    assert (rows['Player F']['goals'], rows['Player F']['blocks'], rows['Player F']['plus_minus']) == (1, 1, 2)
    page = w.client.get('/stats/').get_data(as_text=True)
    assert 'a Callahan included' in page
