"""What the stats dashboard shows: the team's headline numbers against the
period before, the player table (totals or per point, shaded by
percentile among teammates), leaders, line usage, where we score and turn
it over, and the throwing pairs that connect most."""
from collections import defaultdict
from statistics import median

from app.stats import turnovers
from app.stats.formulas import point_we_scored
from app.stats.profile import MIN_RATED_POINTS, percentile
from app.stats.throwing import DEPTH_ZONES

FIELD_LENGTH, FIELD_WIDTH = 100, 37
GRID_COLS, GRID_ROWS = 10, 5   # 10 m x 7.4 m cells


def _rate(part, whole):
    return 100.0 * part / whole if whole else None


# --- headline ----------------------------------------------------------------

def period_numbers(data, game_ids, games):
    """The headline numbers for one set of games."""
    points = [p for pid, p in data.points.items() if data.game_of_point[pid].id in game_ids]
    o_points = [p for p in points if p.our_line_type == 'O-line']
    d_points = [p for p in points if p.our_line_type == 'D-line']
    analysed_o = [p for p in o_points if p.id in data.analysed]
    # A clean hold: an O-line point we scored without turning it over
    clean = 0
    for p in analysed_o:
        if point_we_scored(p) and not any(
                e.event_type in turnovers.OUR_TURNOVERS and not e.is_opponent
                for e in data.events_by_point.get(p.id, [])):
            clean += 1
    handling = turnovers.handling_summary(data, None, game_ids)
    analysed = sum(1 for p in points if p.id in data.analysed)
    return {
        'wins': sum(1 for g in games if g.is_win),
        'losses': sum(1 for g in games if g.is_loss),
        'ties': sum(1 for g in games if g.is_tie),
        'hold': _rate(sum(1 for p in o_points if point_we_scored(p)), len(o_points)),
        'break': _rate(sum(1 for p in d_points if point_we_scored(p)), len(d_points)),
        'clean_hold': _rate(clean, len(analysed_o)),
        'completion': handling['completion_rate'],
        'turnovers_per_point': handling['turnovers'] / analysed if analysed else None,
    }


HEADLINE = [
    {'key': 'hold', 'label': 'Hold %', 'fmt': 'pct', 'help': 'O-line points we scored'},
    {'key': 'break', 'label': 'Break %', 'fmt': 'pct', 'help': 'D-line points we scored'},
    {'key': 'clean_hold', 'label': 'Clean holds', 'fmt': 'pct', 'help': 'O-line points scored without a turnover (full-stat points)'},
    {'key': 'completion', 'label': 'Completion', 'fmt': 'pct', 'help': 'Throws completed (full-stat points)'},
    {'key': 'turnovers_per_point', 'label': 'Turnovers / point', 'fmt': 'dec2', 'lower_better': True,
     'help': 'Throwaways, drops and stalls per point with full stats'},
]


def headline(data, games, prev_games, prev_label):
    """The headline tiles, each with the change from the period before."""
    now = period_numbers(data, {g.id for g in games}, games)
    prev = period_numbers(data, {g.id for g in prev_games}, prev_games) if prev_games else None
    tiles = []
    for h in HEADLINE:
        value = now[h['key']]
        before = prev[h['key']] if prev else None
        change = value - before if value is not None and before is not None else None
        better = None
        if change:
            better = (change < 0) if h.get('lower_better') else (change > 0)
        tiles.append({**h, 'value': value, 'previous': before, 'change': change, 'better': better})
    return {'record': now, 'tiles': tiles, 'prev_label': prev_label if prev else None,
            'prev_record': prev}


def coverage(data, games):
    """How many points have full stats rather than just the Game Day record."""
    game_ids = {g.id for g in games}
    points = [pid for pid in data.points if data.game_of_point[pid].id in game_ids]
    return {'total': len(points), 'analysed': sum(1 for pid in points if pid in data.analysed)}


# --- the player table ----------------------------------------------------------

# Each column: the value in totals mode and per-point mode (the same for
# rates), how it's shown, and whether it's shaded by percentile.
COLUMNS = [
    {'key': 'games', 'label': 'GP', 'group': 'usage', 'help': 'Games played', 'fmt': 'int', 'rate_fmt': 'int'},
    {'key': 'points', 'label': 'Pts', 'group': 'usage', 'help': 'Points played (every point)', 'fmt': 'int', 'rate_fmt': 'int'},
    {'key': 'full', 'label': 'Full', 'group': 'usage', 'help': 'Points with full stats: what every other column counts', 'fmt': 'int', 'rate_fmt': 'int'},
    {'key': 'ppg', 'label': 'Pts/G', 'group': 'usage', 'help': 'Points played per game', 'fmt': 'dec1', 'rate_fmt': 'dec1'},
    {'key': 'o_share', 'label': 'O %', 'group': 'usage', 'help': 'Share of their points played on O-line', 'fmt': 'pct', 'rate_fmt': 'pct'},
    {'key': 'goals', 'label': 'G', 'group': 'offence', 'help': 'Goals (per point: per full-stat point)', 'fmt': 'int', 'rate_fmt': 'dec2', 'shade': True},
    {'key': 'assists', 'label': 'A', 'group': 'offence', 'help': 'Assists', 'fmt': 'int', 'rate_fmt': 'dec2', 'shade': True},
    {'key': 'hockey', 'label': 'HA', 'group': 'offence', 'help': 'Hockey assists', 'fmt': 'int', 'rate_fmt': 'dec2', 'shade': True},
    {'key': 'completion', 'label': 'Cmp %', 'group': 'offence', 'help': 'Completion rate (completions / throws)', 'fmt': 'pct', 'rate_fmt': 'pct', 'shade': True},
    {'key': 'huck', 'label': 'Huck %', 'group': 'offence', 'help': 'Huck completion rate', 'fmt': 'pct', 'rate_fmt': 'pct', 'shade': True},
    {'key': 'turnovers', 'label': 'TO', 'group': 'offence', 'fmt': 'int', 'rate_fmt': 'dec1', 'shade': True, 'lower_better': True,
     'help': 'Turnovers: throwaways, drops and stalls (per point mode: per 10 touches)'},
    {'key': 'blocks', 'label': 'Blk', 'group': 'defence', 'help': 'Blocks (per point mode: blocks on D-line points per D-point)', 'fmt': 'int', 'rate_fmt': 'dec2', 'shade': True},
    {'key': 'takeaways', 'label': 'Take', 'group': 'defence', 'help': 'Takeaways: blocks, forced turnovers and Callahans (per point mode: on D-line points per D-point)', 'fmt': 'int', 'rate_fmt': 'dec2', 'shade': True},
    {'key': 'pulls', 'label': 'Pulls', 'group': 'defence', 'help': 'Pulls (per point mode: share landing in)', 'fmt': 'int', 'rate_fmt': 'pct'},
    {'key': 'plus_minus', 'label': '+/-', 'group': 'ratings', 'help': 'Goals + assists + blocks - turnovers (per point mode: per full-stat point)', 'fmt': 'signed0', 'rate_fmt': 'signed2', 'shade': True},
    {'key': 'per', 'label': 'PER', 'group': 'ratings', 'help': 'Player Efficiency Rating: goal equivalents per 10 points played', 'fmt': 'dec1', 'rate_fmt': 'dec1', 'shade': True},
    {'key': 'epm', 'label': 'EPM', 'group': 'ratings', 'help': 'EDGE Plus/Minus: total goal equivalents', 'fmt': 'signed2', 'rate_fmt': 'signed2', 'shade': True},
    {'key': 'eff', 'label': 'Eff', 'group': 'ratings', 'help': 'Share of goal equivalents not given back in turns (0 to 1)', 'fmt': 'dec3', 'rate_fmt': 'dec3', 'shade': True},
]
GROUPS = [('usage', 'Usage'), ('offence', 'Offence'), ('defence', 'Defence'), ('ratings', 'Ratings')]


def _values(s, handling):
    """{column: (total, per point)} for one player."""
    full = s.get('analysed_points', 0)
    points = s.get('points_played', 0)
    games = s.get('games_played', 0)
    pulls = s.get('pulls') or {}
    takeaways = s.get('blocks', 0) + s.get('forced_turnovers', 0) + s.get('callahans', 0)
    completion = s['completion_rate'] if s.get('throws') else None
    per_point = (lambda v: v / full) if full else (lambda v: None)
    rated = full > 0
    return {
        'games': (games, games),
        'points': (points, points),
        'full': (full, full),
        'ppg': (points / games if games else None,) * 2,
        'o_share': (_rate(s.get('o_line_points_played', 0), points),) * 2,
        'goals': (s.get('goals', 0), per_point(s.get('goals', 0))),
        'assists': (s.get('assists', 0), per_point(s.get('assists', 0))),
        'hockey': (s.get('hockey_assists', 0), per_point(s.get('hockey_assists', 0))),
        'completion': (completion, completion),
        'huck': (handling['huck_completion_rate'],) * 2,
        'turnovers': (s.get('turnovers', 0), handling['turnovers_per_10']),
        'blocks': (s.get('blocks', 0), s.get('blocks_per_d_point') if s.get('analysed_d_line_points') else None),
        'takeaways': (takeaways, s.get('takeaways_per_d_point') if s.get('analysed_d_line_points') else None),
        'pulls': (pulls.get('pulls', 0), pulls.get('in_rate')),
        'plus_minus': (s.get('plus_minus', 0), per_point(s.get('plus_minus', 0))),
        'per': ((s.get('per') if rated else None),) * 2,
        'epm': ((s.get('epm') if rated else None),) * 2,
        'eff': ((s.get('eff') if rated else None),) * 2,
    }


def player_table(players, stats_by_player, data, game_ids, min_points=MIN_RATED_POINTS):
    """Rows for every player with points, each cell with its total and
    per-point value and their percentiles among the players with
    min_points+ full-stat points; and the median of those players."""
    rows = []
    for player in players:
        s = stats_by_player.get(player.id)
        if not s or not s.get('points_played'):
            continue
        handling = turnovers.handling_summary(data, player.id, game_ids)
        rows.append({'player': player, 'stats': s, 'values': _values(s, handling),
                     'qualified': s.get('analysed_points', 0) >= min_points})
    qualified = [r for r in rows if r['qualified']]
    medians = {}
    for col in COLUMNS:
        key = col['key']
        for mode in (0, 1):
            peers = [r['values'][key][mode] for r in qualified if r['values'][key][mode] is not None]
            medians[(key, mode)] = median(peers) if peers else None
            if not col.get('shade') or len(peers) < 3:
                continue
            for r in rows:
                value = r['values'][key][mode]
                if r['qualified'] and value is not None:
                    r.setdefault('pct', {})[(key, mode)] = round(
                        percentile(value, peers, col.get('lower_better')))
    rows.sort(key=lambda r: (not r['qualified'], -(r['values']['per'][0] or 0)))
    return {'rows': rows, 'columns': COLUMNS, 'groups': GROUPS,
            'median': medians, 'min_points': min_points, 'qualified': len(qualified)}


def leaders(table, data, game_ids, limit=3):
    """The top few for goals, assists, blocks, ball security and PER."""
    rows = table['rows']

    def top(key, mode=0, lower=False, only=None):
        pool = [r for r in rows if r['values'][key][mode] is not None and (only is None or only(r))]
        pool.sort(key=lambda r: r['values'][key][mode], reverse=not lower)
        return [{'player': r['player'], 'value': r['values'][key][mode]} for r in pool[:limit]
                if lower or r['values'][key][mode] > 0]

    touches = {r['player'].id: turnovers.handling_summary(data, r['player'].id, game_ids)['touches'] for r in rows}
    return [
        {'label': 'Goals', 'fmt': 'int', 'rows': top('goals')},
        {'label': 'Assists', 'fmt': 'int', 'rows': top('assists')},
        {'label': 'Blocks', 'fmt': 'int', 'rows': top('blocks')},
        {'label': 'Ball security', 'fmt': 'dec1', 'unit': 'TOs / 10 touches',
         'help': f'Fewest turnovers per 10 touches, with {turnovers.MIN_TOUCHES}+ touches',
         'rows': top('turnovers', 1, lower=True, only=lambda r: touches[r['player'].id] >= turnovers.MIN_TOUCHES)},
        {'label': 'PER', 'fmt': 'dec1', 'help': f'With {table["min_points"]}+ full-stat points',
         'rows': top('per', only=lambda r: r['qualified'])},
    ]


def line_usage(table):
    """Points played by gender, and how they split between O and D."""
    groups = defaultdict(lambda: {'players': 0, 'points': 0, 'o': 0, 'd': 0})
    for r in table['rows']:
        g = {'female': 'Women', 'male': 'Men'}.get(r['player'].gender, 'Not recorded')
        s = r['stats']
        groups[g]['players'] += 1
        groups[g]['points'] += s.get('points_played', 0)
        groups[g]['o'] += s.get('o_line_points_played', 0)
        groups[g]['d'] += s.get('d_line_points_played', 0)
    total = sum(g['points'] for g in groups.values())
    out = []
    for name in ('Women', 'Men', 'Not recorded'):
        if name in groups:
            g = groups[name]
            out.append({'label': name, **g, 'share': _rate(g['points'], total),
                        'o_share': _rate(g['o'], g['o'] + g['d']),
                        'per_player': g['points'] / g['players'] if g['players'] else 0})
    return out


# --- the field -------------------------------------------------------------------

def _grid(points):
    """Counts in a GRID_COLS x GRID_ROWS grid over the field, attacking right."""
    counts = defaultdict(int)
    for x, y in points:
        if x is None or y is None:
            continue
        col = min(GRID_COLS - 1, max(0, int(x / FIELD_LENGTH * GRID_COLS)))
        row = min(GRID_ROWS - 1, max(0, int(y / FIELD_WIDTH * GRID_ROWS)))
        counts[(col, row)] += 1
    top = max(counts.values()) if counts else 0
    w, h = FIELD_LENGTH / GRID_COLS, FIELD_WIDTH / GRID_ROWS
    return {
        'total': sum(counts.values()),
        'cells': [{'x': c * w, 'y': r * h, 'w': w, 'h': h, 'count': n, 'strength': n / top}
                  for (c, r), n in sorted(counts.items())],
    }


def field_maps(data, game_ids):
    """Where we score from (assists thrown and goals caught), where we turn
    it over, and how much we use the break side up the field."""
    throws = data.throws_for(None, game_ids)
    assists = [t for t in throws if t['assist']]
    log = turnovers.turnover_log(data, None, game_ids)
    # A throwaway happens where it was thrown; a drop or stall where it was
    turnover_spots = [(t['x_start'], t['y_start']) if t['type'] == 'throwaway' and t['x_start'] is not None
                      else (t['x_end'], t['y_end']) for t in log]
    sides = []
    for key, label, _, _ in DEPTH_ZONES:
        zone = [t for t in throws if t['depth'] == key and t['side']]
        open_ = [t for t in zone if t['side'] == 'open']
        brk = [t for t in zone if t['side'] == 'break']
        sides.append({
            'label': label, 'throws': len(zone),
            'break_share': _rate(len(brk), len(zone)),
            'open_completion': _rate(sum(not t['turnover'] for t in open_), len(open_)),
            'break_completion': _rate(sum(not t['turnover'] for t in brk), len(brk)),
            'open': len(open_), 'break': len(brk),
        })
    sided = [t for t in throws if t['side']]
    open_all = [t for t in sided if t['side'] == 'open']
    brk_all = [t for t in sided if t['side'] == 'break']
    return {
        'scoring': {**_grid((t['x_start'], t['y_start']) for t in assists),
                    'goals': [{'x': t['x_end'], 'y': t['y_end']} for t in assists if t['x_end'] is not None]},
        'turnovers': {**_grid(turnover_spots),
                      'by_type': {k: sum(1 for t in log if t['type'] == k) for k in ('throwaway', 'drop', 'stall')}},
        'sides': {
            'zones': sides,
            'throws': len(sided),
            'break_share': _rate(len(brk_all), len(sided)),
            'open_completion': _rate(sum(not t['turnover'] for t in open_all), len(open_all)),
            'break_completion': _rate(sum(not t['turnover'] for t in brk_all), len(brk_all)),
        },
    }


def throwing_pairs(data, game_ids, players_by_id, limit=10):
    """The thrower -> receiver pairs with the most completions."""
    pairs = defaultdict(lambda: {'completions': 0, 'assists': 0})
    from_thrower = defaultdict(int)
    for t in data.throws_for(None, game_ids):
        if t['turnover'] or not t['receiver_id'] or not t['thrower_id']:
            continue
        pair = pairs[(t['thrower_id'], t['receiver_id'])]
        pair['completions'] += 1
        pair['assists'] += t['assist']
        from_thrower[t['thrower_id']] += 1
    ranked = sorted(pairs.items(), key=lambda kv: (-kv[1]['completions'], -kv[1]['assists']))
    out = []
    for (thrower, receiver), p in ranked:
        if thrower not in players_by_id or receiver not in players_by_id:
            continue
        out.append({'thrower': players_by_id[thrower], 'receiver': players_by_id[receiver], **p,
                    'share': _rate(p['completions'], from_thrower[thrower])})
        if len(out) == limit:
            break
    return out
