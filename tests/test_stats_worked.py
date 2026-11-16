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


# --- a turnover straight off the pull ----------------------------------------

def test_a_throwaway_before_any_catch_still_counts(app):
    """O point: A picks up the pull and throws it away (no pickup tapped),
    B blocks their first throw, C picks up, D scores.

    A: 1 throw, 1 throwaway, 0 completions -> 1 turnover, completion 0%.
    The team: 1 turnover; throws: A's throwaway and C's goal pass = 2,
    1 completed = 50%. (Before the fix A's throwaway had no stored throw, so
    A showed 0 turnovers while the turnover log listed 1, and the team
    showed 0 turnovers and 100%.)
    """
    from app.stats import turnovers
    from app.stats.players import get_players_base_stats
    from app.stats.team import calculate_additional_team_metrics
    w = WorkedGame(app)
    w.point('O', [('throwaway', 'A', 25, 18), ('block', 'B', 30, 18),
                  ('catch', 'C', 30, 18), ('goal', 'D', 90, 18)])
    ctx = w.context()
    try:
        games = w.games()
        a = get_players_base_stats([w.players['A']], games)[w.ids['A']]
        data = turnovers.ThrowingData(games)
        mine = turnovers.handling_summary(data, w.ids['A'], None)
        team = turnovers.handling_summary(data, None, None)
        log = turnovers.turnover_log(data, w.ids['A'])
        metrics = calculate_additional_team_metrics(games)
    finally:
        ctx.pop()
    assert (a['throws'], a['throwaways'], a['turnovers'], a['completion_rate']) == (1, 1, 1, 0)
    assert (mine['throws'], mine['throwaways'], mine['turnovers']) == (1, 1, 1)
    assert len(log) == 1
    assert (team['throws'], team['turnovers']) == (2, 1)
    assert team['completion_rate'] == pytest.approx(50)
    assert metrics['completion_rate'] == pytest.approx(50)
    assert metrics['throws_per_point'] == pytest.approx(2)


# --- completion, catching and drops -----------------------------------------

def test_team_completion_counts_a_drop_as_an_incomplete_pass(app):
    """1. O point: A picks up, A to B, B to C... C drops it, they score.
    2. O point: A picks up, A to B, B to C, C to D who scores.

    Passes thrown: A-B, B-C (dropped); A-B, B-C, C-D           = 5
    Caught: 4. Thrown away: none. Dropped: 1 (C, point 1).
    Team completion = 4 caught / 5 passes = 80%.
    Throwing completion (a drop is the receiver's turnover, so B's pass to C
    in point 1 isn't B's incomplete throw) = 4 / 4 = 100%.
    Catch rate = 4 caught / (4 caught + 1 dropped) = 80%; drop rate 20%.
    (Before the fix the team showed 100% completion, and its catch rate
    counted the two pickups as catches: 6 / 7 = 85.7%.)

    C: 1 pass caught (point 2), 1 dropped: drop rate 1 / 2 = 50%, catch rate
    50%. (Before, C's caught pass had become an assist and wasn't counted:
    1 drop out of 1 = 100%.)
    C's touches: 1 throw (the assist) + 1 drop = 2. Turnovers per 10
    touches = 10 x 1 / 2 = 5.0: throwaways 0, drops 5.0.
    """
    from app.stats import dashboard, profile, turnovers
    from app.stats.players import get_players_base_stats
    from app.stats.team import calculate_additional_team_metrics
    w = WorkedGame(app)
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 35, 18), ('drop', 'C', 50, 18),
                  ('scored_on', 'opp', 0, 18)])
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 40, 18), ('catch', 'C', 60, 18),
                  ('goal', 'D', 90, 18)])
    ctx = w.context()
    try:
        games = w.games()
        ids = {w.game_id}
        data = turnovers.ThrowingData(games)
        team = turnovers.handling_summary(data, None, ids)
        c = turnovers.handling_summary(data, w.ids['C'], ids)
        metrics = calculate_additional_team_metrics(games)
        headline = dashboard.period_numbers(data, ids, games)
        radar = profile.team_period_metrics(data, ids)
        c_stats = get_players_base_stats([w.players['C']], games)[w.ids['C']]
    finally:
        ctx.pop()
    assert (team['throws'], team['throwaways'], team['drops'], team['receptions']) == (4, 0, 1, 5)
    assert team['pass_completion_rate'] == pytest.approx(80)
    assert team['completion_rate'] == pytest.approx(100)
    assert team['drop_rate'] == pytest.approx(20)
    assert metrics['completion_rate'] == pytest.approx(80)
    assert metrics['catch_rate'] == pytest.approx(80)
    assert headline['completion'] == pytest.approx(80)
    assert radar['completion'] == pytest.approx(80)
    assert (c['receptions'], c['drops']) == (2, 1)
    assert c['drop_rate'] == pytest.approx(50)
    assert c_stats['catch_rate'] == pytest.approx(50)
    assert c['touches'] == 2
    assert c['turnovers_per_10'] == pytest.approx(5.0)
    assert (c['throwaways_per_10'], c['drops_per_10']) == (0, pytest.approx(5.0))


# --- hucks -------------------------------------------------------------------

def test_a_huck_is_long_and_upfield_on_every_page(app):
    """O point: A picks up at 20 m, A to B at 45 m (25 m upfield), B swings it
    back to C at 23 m (22 m backwards), C to D at 30 m, D to E who scores at 88 m.

    A huck is 20 m+ long and 15 m+ upfield:
        A-B: 25 m, 25 m upfield      huck
        B-C: 22 m, backwards         a swing, not a huck
        C-D: about 11 m              short
        D-E: about 58 m upfield      huck
    Team: 2 hucks in 1 point = 2.0 hucks per point; A and D 1 each, B none.
    (Before the fix hucks per point and the CSV counted any throw over 20 m,
    so B's swing made 3, while huck completion % already used this rule.)
    """
    from app.stats import turnovers
    from app.stats.players import get_players_base_stats
    from app.stats.team import calculate_additional_team_metrics
    w = WorkedGame(app)
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 45, 18), ('catch', 'C', 23, 18),
                  ('catch', 'D', 30, 10), ('goal', 'E', 88, 10)])
    ctx = w.context()
    try:
        games = w.games()
        stats = get_players_base_stats(list(w.players.values()), games)
        metrics = calculate_additional_team_metrics(games)
        team = turnovers.handling_summary(turnovers.ThrowingData(games), None, None)
    finally:
        ctx.pop()
    assert [stats[w.ids[k]]['hucks'] for k in 'ABCD'] == [1, 0, 0, 1]
    assert metrics['hucks_per_point'] == pytest.approx(2.0)
    assert team['huck_attempts'] == 2


def test_breaks_and_holds_are_ours(possession_game):
    """The possession game: points 1 (O, we scored) is our hold, points 2
    and 4 (D, we scored) our breaks, point 3 (O, they scored) their break,
    point 5 (D, they scored) their hold.

    Our holds 1, our breaks 2. (Before, the summary's breaks counted their
    break too, 3, and holds their hold, 2.) The trend line "breaks by either
    team" is 3 of 5 points = 60%; break % (D-line) 2 of 3 = 66.7%.
    """
    import json
    from app.stats.team import calculate_performance_trends, calculate_team_summary
    w = possession_game
    ctx = w.context()
    try:
        summary = calculate_team_summary(w.games())
        trends = calculate_performance_trends(w.games())
    finally:
        ctx.pop()
    assert (summary['holds'], summary['breaks']) == (1, 2)
    assert json.loads(trends['break_percentage']) == [pytest.approx(60)]
    assert json.loads(trends['d_line_efficiency']) == [pytest.approx(200 / 3)]


# --- a point with no plays ------------------------------------------------------

def test_a_point_with_no_plays_has_no_full_stats(app):
    """1. O point: A picks up, A to B, B throws it away; they score.
    2. O point, a hold taken live (no plays), where the only thing recorded
       was a substitution.

    Only point 1 has full stats, so turnovers per point = 1 / 1 = 1.0 and
    A's and B's per-point rates divide by 1 point, not 2. Point 2 still
    counts as played, and as a hold: hold % = 1 of 2 = 50%.
    (Before, the substitution made point 2 a point with full stats and no
    turns: 0.5 turnovers per point.)
    """
    from app import db
    from app.models.event import Event
    from app.models.point import Point
    from app.stats import dashboard, turnovers
    from app.stats.players import get_players_base_stats
    from app.stats.team import calculate_game_stats
    w = WorkedGame(app)
    w.point('O', [('catch', 'A', 20, 18), ('catch', 'B', 35, 18), ('throwaway', 'B', 60, 18),
                  ('scored_on', 'opp', 0, 18)])
    p2 = w.point('O', [])
    point = db.session.get(Point, p2)
    point.point_outcome, point.our_score_after, point.their_score_after = 'scored', 1, 1
    db.session.add(Event(point_id=p2, player_id=w.ids['A'], event_type='substitution',
                         team_organization_id=w.team.id))
    db.session.commit()
    ctx = w.context()
    try:
        games = w.games()
        data = turnovers.ThrowingData(games)
        headline = dashboard.period_numbers(data, {w.game_id}, games)
        game = calculate_game_stats(w.game())
        b = get_players_base_stats([w.players['B']], games)[w.ids['B']]
    finally:
        ctx.pop()
    assert headline['turnovers_per_point'] == pytest.approx(1.0)
    assert headline['hold'] == pytest.approx(50)
    assert game['analysed_points'] == 1 and game['avg_turnovers_per_point'] == pytest.approx(1.0)
    assert (b['points_played'], b['analysed_points']) == (2, 1)
    assert b['throws_per_point'] == pytest.approx(1.0)   # B's one throw, the throwaway


# --- players who only play one line ------------------------------------------------

def test_a_d_line_player_has_no_o_line_plus_minus(app):
    """Three players with 10+ full-stat points (enough to be ranked):
        X: O-line only, +/- per O-point +0.40
        Y: O-line only, +/- per O-point +0.20
        Z: D-line only, no O-line points at all
    Z has no O-line +/- (shown as a dash), and isn't a 0 in the median: the
    median of X and Y is +0.30, and Y ranks 2 of 2. (Before, Z showed
    +0.00 and the median was the middle of 0.4, 0.2 and 0 = 0.20, with Y
    2 of 3.)
    """
    from app.stats.profile import rating_comparison
    stats = {
        'X': {'analysed_points': 10, 'analysed_o_line_points': 10, 'analysed_d_line_points': 0,
              'o_line_plus_minus_per_point': 0.4},
        'Y': {'analysed_points': 10, 'analysed_o_line_points': 10, 'analysed_d_line_points': 0,
              'o_line_plus_minus_per_point': 0.2},
        'Z': {'analysed_points': 12, 'analysed_o_line_points': 0, 'analysed_d_line_points': 12,
              'o_line_plus_minus_per_point': 0, 'd_line_plus_minus_per_point': 0.25},
    }
    z = {r['key']: r for r in rating_comparison('Z', stats)['rows']}
    y = {r['key']: r for r in rating_comparison('Y', stats)['rows']}
    assert z['o_line_plus_minus_per_point']['value'] is None
    assert z['o_line_plus_minus_per_point']['rank'] is None
    assert y['o_line_plus_minus_per_point']['team_median'] == pytest.approx(0.3)
    assert (y['o_line_plus_minus_per_point']['rank'], y['o_line_plus_minus_per_point']['of']) == (2, 2)
    # And the other way round: only Z has a D-line +/-.
    assert y['d_line_plus_minus_per_point']['value'] is None
    assert z['d_line_plus_minus_per_point']['rank'] == 1


# --- Game Day ------------------------------------------------------------------

def test_game_day_completion(app):
    """Two points taken live on Game Day (no full stats).

    1. O point: A picks up, B catches, C catches and throws it away, D
       blocks, E picks up, A catches, B scores from A's assist.
    2. O point: F picks up and is stalled; they score.

    The disc was in someone's hands 6 times (catches and pickups): A twice,
    B, C, E and F once. F was stalled, so F threw nothing: throws = 6 - 1 =
    5, and 1 was thrown away (C). Completion = 4 / 5 = 80%.
    C: 1 throw, thrown away = 0%. F: no throws, so no completion (a dash).
    (Before the fix C showed 1 / (1 + 1) = 50% and F 100%, the game's team
    figure was the average of the players' percentages, (100 + 100 + 50 +
    100 + 100) / 5 = 90%, and the tournament and season pages showed
    (goals + assists) / (goals + assists + turns) = 2 / 4 = 50%.)
    """
    from app.models.point import Point
    from app.stats.players import gameday_throwing
    w = WorkedGame(app)
    ids = w.ids
    line = [ids[k] for k in 'ABCDEFG']
    for number, events, outcome in [
        (1, [('pickup', 'A'), ('catch', 'B'), ('catch', 'C'), ('throwaway', 'C'), ('block', 'D'),
             ('pickup', 'E'), ('catch', 'A'), ('assist', 'A'), ('score', 'B')], 'scored'),
        (2, [('pickup', 'F'), ('stall', 'F')], 'conceded'),
    ]:
        r = w.client.post('/gameday/api/record-point', json={
            'game_id': w.game_id, 'point_number': number, 'line_type': 'O-line',
            'gender_ratio': '4-3', 'players': line, 'outcome': outcome,
            'events': [{'type': t, 'player_id': ids[k]} for t, k in events]})
        assert r.get_json()['success'], r.get_data(as_text=True)
    ctx = w.context()
    try:
        point_ids = [p.id for p in Point.query.filter_by(game_id=w.game_id)]
        throwing = gameday_throwing(point_ids)
    finally:
        ctx.pop()
    assert throwing[None] == {'throws': 5, 'throwaways': 1, 'completion_rate': 80.0}
    assert throwing[ids['C']]['completion_rate'] == 0
    assert throwing[ids['F']] == {'throws': 0, 'throwaways': 0, 'completion_rate': None}
    assert throwing[ids['A']]['throws'] == 2
    game_page = w.client.get(f'/gameday/stats/{w.game_id}').get_data(as_text=True)
    assert '80.0%' in game_page and '90.0%' not in game_page
    tournament_page = w.client.get(f'/gameday/tournament/{w.tournament.id}/stats').get_data(as_text=True)
    assert '80.0%' in tournament_page and '50.0%' not in tournament_page
