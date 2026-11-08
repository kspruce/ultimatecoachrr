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
