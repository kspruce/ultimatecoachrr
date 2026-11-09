"""A player's radar profile: each axis as a percentile among teammates.

Each axis is a rate from get_players_base_stats (plus ball security from
turnovers.handling_summary), ranked against every teammate who played in
the same games with enough of a sample on that axis. 50 is the median
teammate, so the radar needs no made-up "elite" targets and nothing is
clipped at the edge.
"""
from statistics import median

from app.stats import turnovers

# Fewer qualifying teammates than this and an axis has no percentile
MIN_PEERS = 3

# key: the value in the player's metrics; sample: the count it rests on,
# min: the sample a player needs to be ranked (and not shown as low sample).
# lower_better axes are ranked the other way round, so bigger is always better.
RADAR_AXES = {
    'offence': [
        {'key': 'completion_rate', 'label': 'Completion', 'fmt': 'pct', 'sample': 'throws', 'min': 20, 'unit': 'throws'},
        {'key': 'goals_per_point', 'label': 'Goals / pt', 'fmt': 'rate', 'sample': 'analysed_points', 'min': 10, 'unit': 'points'},
        {'key': 'assists_per_point', 'label': 'Assists / pt', 'fmt': 'rate', 'sample': 'analysed_points', 'min': 10, 'unit': 'points'},
        {'key': 'hockey_assists_per_point', 'label': 'Hockey assists / pt', 'fmt': 'rate', 'sample': 'analysed_points', 'min': 10, 'unit': 'points'},
        {'key': 'huck_completion_rate', 'label': 'Huck completion', 'fmt': 'pct', 'sample': 'huck_attempts', 'min': 5, 'unit': 'hucks'},
        {'key': 'turnovers_per_10', 'label': 'Turnovers / 10 touches', 'short': 'Ball security', 'fmt': 'per10', 'sample': 'touches', 'min': 20, 'unit': 'touches',
         'lower_better': True, 'help': 'Throwaways, drops and stalls per 10 touches. Fewer ranks higher, so the radar axis is ball security.'},
    ],
    'defence': [
        {'key': 'blocks_per_d_point', 'label': 'Blocks / D-pt', 'fmt': 'rate', 'sample': 'analysed_d_line_points', 'min': 10, 'unit': 'D-points'},
        {'key': 'takeaways_per_d_point', 'label': 'Takeaways / D-pt', 'fmt': 'rate', 'sample': 'analysed_d_line_points', 'min': 10, 'unit': 'D-points',
         'help': 'Blocks, forced turnovers and Callahans on D-line points'},
        {'key': 'd_line_plus_minus_per_point', 'label': 'D-line +/- per pt', 'fmt': 'signed', 'sample': 'analysed_d_line_points', 'min': 10, 'unit': 'D-points',
         'help': 'Goals, assists and blocks less turnovers, per D-line point'},
        {'key': 'pull_in_rate', 'label': 'Pulls in', 'fmt': 'pct', 'sample': 'pulls', 'min': 5, 'unit': 'pulls'},
        {'key': 'avg_hang_time', 'label': 'Pull hang time', 'fmt': 'secs', 'sample': 'timed_pulls', 'min': 3, 'unit': 'timed pulls'},
    ],
}


def player_metrics(stats, handling):
    """The values and samples the radar axes read, for one player."""
    pulls = stats.get('pulls') or {}
    return {
        **{k: stats.get(k, 0) for k in (
            'completion_rate', 'goals_per_point', 'assists_per_point', 'hockey_assists_per_point',
            'blocks_per_d_point', 'takeaways_per_d_point', 'd_line_plus_minus_per_point',
            'throws', 'analysed_points', 'analysed_d_line_points')},
        'huck_completion_rate': handling['huck_completion_rate'],
        'huck_attempts': handling['huck_attempts'],
        'turnovers_per_10': handling['turnovers_per_10'],
        'touches': handling['touches'],
        'pull_in_rate': pulls.get('in_rate'),
        'pulls': pulls.get('pulls', 0),
        'avg_hang_time': pulls.get('avg_hang_time'),
        'timed_pulls': pulls.get('timed', 0),
    }


def percentile(value, peers, lower_better=False):
    """Where value sits among peers, 0-100 (ties count half)."""
    if lower_better:
        below = sum(p > value for p in peers)
    else:
        below = sum(p < value for p in peers)
    equal = sum(p == value for p in peers)
    return 100.0 * (below + 0.5 * equal) / len(peers)


def radar_profile(player_id, stats_by_player, throwing, game_ids):
    """Each radar's axes for player_id, ranked against the other players in
    stats_by_player (everyone who played in these games)."""
    metrics = {
        pid: player_metrics(stats, turnovers.handling_summary(throwing, pid, game_ids))
        for pid, stats in stats_by_player.items()
    }
    mine = metrics[player_id]
    profile = {}
    for side, axes in RADAR_AXES.items():
        rows = []
        for axis in axes:
            key, sample_key, need = axis['key'], axis['sample'], axis['min']
            peers = [m[key] for m in metrics.values()
                     if m[key] is not None and (m[sample_key] or 0) >= need]
            value, sample = mine[key], mine[sample_key] or 0
            if not sample:
                value = None  # nothing recorded: a 0 here would mean no data, not a bad rate
            enough = value is not None and sample >= need
            # A small sample is still ranked, but flagged as low sample
            ranked = value is not None and len(peers) >= MIN_PEERS
            rows.append({
                **axis,
                'value': value,
                'team_median': median(peers) if peers else None,
                'percentile': round(percentile(value, peers, axis.get('lower_better'))) if ranked else None,
                'sample_size': sample,
                'enough': enough,
                'peers': len(peers),
            })
        profile[side] = rows
    return profile


# The ratings on the PER card, compared with teammates who played enough
RATINGS = [
    {'key': 'per', 'label': 'PER', 'fmt': '%.1f'},
    {'key': 'epm', 'label': 'EPM', 'fmt': '%+.2f'},
    {'key': 'eff', 'label': 'Eff', 'fmt': '%.3f'},
    {'key': 'o_line_plus_minus_per_point', 'label': 'O-line +/- per point', 'fmt': '%+.2f'},
    {'key': 'd_line_plus_minus_per_point', 'label': 'D-line +/- per point', 'fmt': '%+.2f'},
]
MIN_RATED_POINTS = 10


def rating_comparison(player_id, stats_by_player):
    """Each rating with the median teammate's and the player's rank (1 is
    best) among teammates with MIN_RATED_POINTS+ points with full stats.
    stats_by_player must already have apply_ratings run on it."""
    rated = [s for s in stats_by_player.values() if s.get('analysed_points', 0) >= MIN_RATED_POINTS]
    mine = stats_by_player[player_id]
    qualifies = mine.get('analysed_points', 0) >= MIN_RATED_POINTS
    rows = []
    for r in RATINGS:
        values = [s.get(r['key'], 0) or 0 for s in rated]
        value = mine.get(r['key'], 0) or 0
        rows.append({
            **r,
            'value': value,
            'team_median': median(values) if values else None,
            'rank': 1 + sum(v > value for v in values) if qualifies and values else None,
            'of': len(values),
        })
    return {'rows': rows, 'min_points': MIN_RATED_POINTS, 'qualifies': qualifies}


# --- the team's radars: this period against the team's own history ----------

TEAM_AXES = {
    'offence': [
        {'key': 'hold', 'label': 'Hold %', 'fmt': 'pct', 'help': 'O-line points we scored'},
        {'key': 'completion', 'label': 'Completion', 'fmt': 'pct'},
        {'key': 'huck_completion', 'label': 'Huck completion', 'fmt': 'pct'},
        {'key': 'break_completion', 'label': 'Break-side completion', 'fmt': 'pct'},
        {'key': 'turnovers_per_o_point', 'label': 'Turnovers / O-pt', 'short': 'Ball security', 'fmt': 'rate',
         'lower_better': True, 'help': 'Our turnovers per O-line point (full stats). Fewer ranks higher.'},
    ],
    'defence': [
        {'key': 'break', 'label': 'Break %', 'fmt': 'pct', 'help': 'D-line points we scored'},
        {'key': 'blocks_per_d_point', 'label': 'Blocks / D-pt', 'fmt': 'rate'},
        {'key': 'takeaways_per_d_point', 'label': 'Takeaways / D-pt', 'fmt': 'rate',
         'help': 'Blocks, forced turnovers and Callahans on D-line points'},
        {'key': 'regain_rate', 'label': 'Got the disc', 'fmt': 'pct',
         'help': 'D-line points where we got the disc back (any turnover by them)'},
        {'key': 'regain_conversion', 'label': 'Scored after getting it', 'short': 'Conversion', 'fmt': 'pct',
         'help': 'Of the D-line points where we got the disc, the share we scored'},
    ],
}
# Fewer periods of history than this and percentiles mean little
MIN_HISTORY = 3


def team_period_metrics(data, game_ids):
    """The team radar values for one set of games (from turnovers.ThrowingData)."""
    from app.stats.formulas import point_we_scored

    def rate(part, whole):
        return 100.0 * part / whole if whole else None

    points = [p for pid, p in data.points.items() if data.game_of_point[pid].id in game_ids]
    o_points = [p for p in points if p.our_line_type == 'O-line']
    d_points = [p for p in points if p.our_line_type == 'D-line']
    o_full = [p for p in o_points if p.id in data.analysed]
    d_full = [p for p in d_points if p.id in data.analysed]
    events = data.events_by_point
    our_turnovers = sum(1 for p in o_full for e in events.get(p.id, [])
                        if e.event_type in turnovers.OUR_TURNOVERS and not e.is_opponent and e.is_offensive is not False)
    blocks = takeaways = regained = regained_scored = 0
    for p in d_full:
        evs = events.get(p.id, [])
        blocks += sum(1 for e in evs if e.event_type == 'block' and not e.is_opponent)
        takeaways += sum(1 for e in evs if e.event_type in ('block', 'forced_turnover', 'callahan') and not e.is_opponent)
        if any(e.event_type in turnovers.WE_REGAIN for e in evs):
            regained += 1
            regained_scored += point_we_scored(p)
    h = turnovers.handling_summary(data, None, game_ids)
    return {
        'hold': rate(sum(1 for p in o_points if point_we_scored(p)), len(o_points)),
        'break': rate(sum(1 for p in d_points if point_we_scored(p)), len(d_points)),
        'completion': h['completion_rate'],
        'huck_completion': h['huck_completion_rate'],
        'break_completion': h['break_completion_rate'],
        'turnovers_per_o_point': our_turnovers / len(o_full) if o_full else None,
        'blocks_per_d_point': blocks / len(d_full) if d_full else None,
        'takeaways_per_d_point': takeaways / len(d_full) if d_full else None,
        'regain_rate': rate(regained, len(d_full)),
        'regain_conversion': rate(regained_scored, regained),
    }


def team_profile(data, game_ids, prev_ids, all_games):
    """Each team radar axis for these games (and the period before) as a
    percentile among the team's tournaments with full stats, or its games
    when there are fewer than MIN_HISTORY tournaments."""
    by_tournament = {}
    for g in all_games:
        if g.tournament_id is not None:
            by_tournament.setdefault(g.tournament_id, set()).add(g.id)
    analysed_games = {data.game_of_point[pid].id for pid in data.analysed}
    periods = [ids for ids in by_tournament.values() if ids & analysed_games]
    unit = 'tournaments'
    if len(periods) < MIN_HISTORY:
        periods = [{gid} for gid in analysed_games]
        unit = 'games'
    history = [team_period_metrics(data, ids) for ids in periods]
    now = team_period_metrics(data, game_ids)
    before = team_period_metrics(data, prev_ids) if prev_ids else None
    out = {'unit': unit, 'periods': len(history), 'enough': len(history) >= MIN_HISTORY}
    for side, axes in TEAM_AXES.items():
        rows = []
        for axis in axes:
            key = axis['key']
            past = [m[key] for m in history if m[key] is not None]
            ranked = len(past) >= MIN_HISTORY

            def pct(v):
                return round(percentile(v, past, axis.get('lower_better'))) if ranked and v is not None else None
            rows.append({
                **axis,
                'value': now[key], 'percentile': pct(now[key]),
                'previous': before[key] if before else None,
                'previous_percentile': pct(before[key]) if before else None,
                'history_median': median(past) if past else None,
                'best': (min(past) if axis.get('lower_better') else max(past)) if past else None,
            })
        out[side] = rows
    return out
