"""Pure stat formulas: no database access."""



# Player ratings: goal equivalents, EPM, PER and Eff
#
# The approach follows Paul Würtztack's Better Box Score Metrics (BBSM) on
# Ultiworld: a turn's cost (and a block's value) is set by how often
# possessions end in a goal in the games being looked at, rather than being
# fixed. /stats/ratings explains it all for coaches and players; keep that
# page (templates/stats/ratings.html) in step with anything changed here.

# Used when no recorded points have a result yet (club Nationals runs
# about 0.6).
DEFAULT_SE = 0.6
# PER starts every player at the team's rate as if they had already played
# this many points, so a few good or bad points don't top or sink the table.
PER_PRIOR_POINTS = 10
# PER is goal equivalents per this many points played.
PER_SCALE = 10

TURNOVER_EVENTS = {'throwaway', 'drop', 'stall'}
# Every recorded event where the disc changes hands, by either team: used to
# count turns for scoring efficiency.
POSSESSION_CHANGES = ('throwaway', 'drop', 'stall', 'block',
                      'forced_turnover', 'unforced_turnover', 'callahan')


OUR_TURNS = ('throwaway', 'drop', 'stall')
REGAINS = ('block', 'forced_turnover', 'unforced_turnover', 'callahan')


def possession_gap(started_on_offence, we_scored, event_types):
    """Why a finished point's recorded possession changes can't be right,
    or None if they add up.

    Possession alternates, so the number of times we got the disc back
    (regains) less the number of times we gave it away (our turns) is fixed
    by how the point started and who scored: 0 for a hold, 1 for a break,
    -1 for a broken O point and 0 for a D point they scored. Anything else
    means a change of possession wasn't recorded (or one too many was)."""
    our_turns = sum(1 for t in event_types if t in OUR_TURNS)
    regains = sum(1 for t in event_types if t in REGAINS)
    expected = (0 if we_scored else -1) if started_on_offence else (1 if we_scored else 0)
    if regains - our_turns == expected:
        return None
    if not started_on_offence and we_scored and regains == 0:
        return 'We scored on a D point, but no block or turnover by them was recorded'
    if started_on_offence and not we_scored and our_turns == 0:
        return 'They scored on our O point, but none of our turns was recorded'
    start = 'O' if started_on_offence else 'D'
    result = 'we scored' if we_scored else 'they scored'
    return (f"Possession changes don't add up: {start} point, {result}, "
            f"{our_turns} of our turn{'s' if our_turns != 1 else ''} and "
            f"{regains} regain{'s' if regains != 1 else ''} recorded")


def scoring_efficiency(goals, turns):
    """SE: the share of possessions (both teams') that end in a goal,
    goals / (goals + turns). DEFAULT_SE when there's nothing to go on."""
    if goals + turns <= 0:
        return DEFAULT_SE
    return goals / (goals + turns)


def ge_coefficients(se):
    """What one goal, assist, block and turn are worth, in goal
    equivalents, at scoring efficiency se (BBSM's EPM coefficients).

    A turn costs se and a block earns se: the disc changing hands is worth
    the chance of scoring with it. Goals and assists share out the rest, so
    a team's goals and assists less its turns add up to its goals:
    G + A = 2 - se per goal, and turns cost (1 - se) per goal."""
    return {
        'goal': 0.86 - 0.43 * se,
        'assist': 1.14 - 0.57 * se,
        'block': se,
        'turn': se,
    }


def _turns(stats):
    if 'turnovers' in stats:
        return stats['turnovers']
    return stats.get('throwaways', 0) + stats.get('drops', 0) + stats.get('stalls', 0)


def goal_equivalents(stats, se):
    """A player's goals, assists, blocks and turns in goal equivalents.
    A Callahan counts as a block and a goal. Returns the plus side (gab),
    the turn cost (turns, positive) and the net (total, which is EPM)."""
    c = ge_coefficients(se)
    callahans = stats.get('callahans', 0)
    gab = (c['goal'] * (stats.get('goals', 0) + callahans)
           + c['assist'] * stats.get('assists', 0)
           + c['block'] * (stats.get('blocks', 0) + callahans))
    turns = c['turn'] * _turns(stats)
    return {'gab': gab, 'turns': turns, 'total': gab - turns}


def _analysed_points(stats):
    """Points with full stats (falls back to points_played for stats
    built without the split)."""
    return stats.get('analysed_points', stats['points_played'])


def _se(team_avgs):
    return team_avgs.get('se', DEFAULT_SE)


def calculate_per(stats, team_avgs):
    """Player Efficiency Rating: goal equivalents per PER_SCALE points
    played, starting from the team's rate over PER_PRIOR_POINTS points.

    team_avgs comes from app.stats.team.calculate_team_averages for the same
    set of games (it holds the SE and the team's goal equivalents per
    point). A player with no recorded points has no PER (0)."""
    points = _analysed_points(stats)
    if points == 0:
        return 0
    ge = goal_equivalents(stats, _se(team_avgs))['total']
    team_rate = team_avgs.get('avg_ge_per_point', 0)
    return PER_SCALE * (ge + PER_PRIOR_POINTS * team_rate) / (points + PER_PRIOR_POINTS)


def calculate_eff(stats, team_avgs):
    """Eff, between 0 and 1: the share of a player's goal equivalents they
    didn't give back in turns, gab / (gab + turns + prior). The prior is
    the team's average turns per player in goal equivalents, so a player
    with a few plays and no turns doesn't top the list."""
    ge = goal_equivalents(stats, _se(team_avgs))
    denominator = ge['gab'] + ge['turns'] + team_avgs.get('eff_prior', 0)
    if ge['gab'] <= 0 or denominator <= 0:
        return 0
    return ge['gab'] / denominator


def apply_ratings(stats, team_avgs):
    """Fill in a player's ratings: per, eff, epm (net goal equivalents) and
    the goal-equivalent split behind them. Returns stats."""
    ge = goal_equivalents(stats, _se(team_avgs))
    stats['ge_plus'] = ge['gab']
    stats['ge_turns'] = ge['turns']
    stats['epm'] = ge['total']
    stats['per'] = calculate_per(stats, team_avgs)
    stats['eff'] = calculate_eff(stats, team_avgs)
    return stats


# Fewer O- (or D-) line points than this and a player's line conversion is
# too noisy to rank them for the optimal line (1 point, 100% isn't the best)
MIN_LINE_POINTS = 5


def calculate_optimized_line_efficiency(players, player_stats, is_offensive=True, min_points=MIN_LINE_POINTS):
    """Players ranked by line conversion (share of their O-line points we
    held, or D-line points we broke), for the games player_stats covers,
    among those with min_points+ points on that line.
    Returns [(player, fraction 0-1), ...], best first."""
    line = 'o_line' if is_offensive else 'd_line'
    player_efficiency = {}
    for player in players:
        stats = player_stats.get(player.id)
        if stats and stats.get(f'{line}_points_played', 0) >= max(1, min_points):
            player_efficiency[player] = (stats[f'{line}_points_scored']
                                         / stats[f'{line}_points_played'])
    return sorted(player_efficiency.items(), key=lambda x: x[1], reverse=True)

# --- Core Statistical Calculation Functions ---
def convert_booleans_for_js(obj):
    """Convert Python booleans to JavaScript-compatible strings"""
    if isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, dict):
        return {k: convert_booleans_for_js(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_booleans_for_js(i) for i in obj]
    return obj

def point_we_scored(point) -> bool:
    """
    Robust 'did we score?' check across schemas.

    Current DB schema (Point model):
      - point.point_outcome == 'scored' / 'conceded'  :contentReference[oaicite:2]{index=2}
    Legacy / alternate schemas may use:
      - point.outcome text ("Goal For Home")
      - point.we_scored boolean/property
    """
    # 1) Current schema
    po = getattr(point, 'point_outcome', None)
    if isinstance(po, str) and po.strip().lower() in ('scored', 'score', 'won'):
        return True
    if isinstance(po, str) and po.strip().lower() in ('conceded', 'concede', 'lost'):
        return False

    # 2) Legacy text outcome
    outcome = getattr(point, 'outcome', None)
    if isinstance(outcome, str) and outcome.strip():
        s = outcome.strip().lower()
        if 'goal for home' in s or 'home scored' in s:
            return True
        if 'goal against home' in s or 'away scored' in s:
            return False

    # 3) Fallback to property/boolean if present
    ws = getattr(point, 'we_scored', None)
    if isinstance(ws, bool):
        return ws

    return False

def get_point_starting_possession(point):
    """
    Returns 'offence' or 'defence' for whether WE start with the disc.

    Priority:
      1) point.starting_possession (what your UI saves)
      2) point.starting_position (legacy)
      3) fallback to our_line_type
    """
    # 1) What input_stats.html saves
    sp = getattr(point, 'starting_possession', None)
    if isinstance(sp, str) and sp.strip().lower() in ('offence', 'offense', 'defence', 'defense'):
        sp = sp.strip().lower()
        return 'offence' if sp in ('offence', 'offense') else 'defence'

    # 2) Legacy field name
    sp = getattr(point, 'starting_position', None)
    if isinstance(sp, str) and sp.strip().lower() in ('offence', 'offense', 'defence', 'defense'):
        sp = sp.strip().lower()
        return 'offence' if sp in ('offence', 'offense') else 'defence'

    # 3) Fallback assumption
    return 'offence' if getattr(point, 'our_line_type', None) == 'O-line' else 'defence'

# Helper function to convert games to a tuple of IDs for caching
def games_to_tuple(games):
    """Convert games to a tuple of IDs for use as cache key"""
    if not games:
        return None
    if isinstance(games, list):
        return tuple(sorted([g.id for g in games]))
    return (games.id,)
