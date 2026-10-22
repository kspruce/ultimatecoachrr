"""Where turnovers happen, as rates rather than counts, so a player can see
what to work on: completion by throw type, open/break side, field zone and
game situation, compared with the team, over time, and against the
player's own earlier games.

Everything is built from one load of the team's throws and events
(ThrowingData), then sliced in Python per player, game or period.
"""
from collections import defaultdict

from app.models.point import LineUp
from app.models.throws import Throw
from app.utils.media_embed import youtube_id
from app.utils.team_filter import get_current_team_id

from app.stats.loaders import preload_game_points, game_points
from app.stats.throwing import (DEPTH_LABELS, DEPTH_ZONES, LANE_LABELS, LANES, THROW_KIND_LABELS,
                                THROW_KINDS, depth_zone, lane, throw_kind)

# A bucket needs this many throws before we say anything about it.
MIN_ATTEMPTS = 8
# ...and a player needs this many touches for the turnover leaderboard.
MIN_TOUCHES = 20
ROLLING_WINDOW = 3

OUR_TURNOVERS = ('throwaway', 'drop', 'stall')
WE_REGAIN = ('block', 'forced_turnover', 'unforced_turnover', 'callahan')

# (key, title, [(value, label), ...]) - the ways throws are split up.
DIMENSIONS = [
    ('kind', 'Throw type', THROW_KINDS),
    ('side', 'Open or break side', [('open', 'Open side'), ('break', 'Break side')]),
    ('depth', 'Thrown from', [(k, label) for k, label, _, _ in DEPTH_ZONES]),
    ('lane', 'Sideline or middle', [(k, label) for k, label, _, _ in LANES]),
    ('line', 'Point type', [('O-line', 'O-line points'), ('D-line', 'D-line points')]),
    ('score', 'Score', [('close', 'Close (within 2)'), ('not_close', 'Not close')]),
    ('half', 'Half', [('first', 'First half'), ('second', 'Second half')]),
]
DIMENSION_TITLES = {key: title for key, title, _ in DIMENSIONS}
VALUE_LABELS = {(key, value): label for key, _, values in DIMENSIONS for value, label in values}

# How a focus area is phrased: what the throws in that bucket are.
FOCUS_PHRASES = {
    'kind': '{label}', 'side': 'Throws to the {lower}', 'depth': 'Throws from the {lower}',
    'lane': 'Throws from the {lower}', 'line': 'Throws on {label}',
    'score': 'Throws when the score is {lower}', 'half': 'Throws in the {lower}',
}


def _second_half(point, game):
    before = (point.our_score_before or 0) + (point.their_score_before or 0)
    if game.halftime_our_score is not None and game.halftime_their_score is not None:
        return before >= game.halftime_our_score + game.halftime_their_score
    total = (game.our_score or 0) + (game.their_score or 0)
    return total > 0 and before * 2 >= total


def _point_context(point, game):
    close = abs((point.our_score_before or 0) - (point.their_score_before or 0)) <= 2
    return {
        'line': point.our_line_type,
        'score': 'close' if close else 'not_close',
        'half': 'second' if _second_half(point, game) else 'first',
    }


def _rate(part, whole):
    return 100.0 * part / whole if whole else None


class ThrowingData:
    """The team's throws and turnover-related events for a set of games."""

    def __init__(self, games):
        self.games = sorted([g for g in games or [] if g is not None],
                            key=lambda g: (str(g.date or ''), g.id))
        preload_game_points(self.games)
        self.points = {}
        self.game_of_point = {}
        context = {}
        for game in self.games:
            for point in game_points(game):
                self.points[point.id] = point
                self.game_of_point[point.id] = game
                context[point.id] = _point_context(point, game)

        # The points and games each player was on a line in
        self.points_played = defaultdict(set)
        self.games_played = defaultdict(set)
        if self.points:
            for player_id, point_id in LineUp.query.with_entities(LineUp.player_id, LineUp.point_id).filter(
                    LineUp.point_id.in_(list(self.points))):
                self.points_played[player_id].add(point_id)
                self.games_played[player_id].add(self.game_of_point[point_id].id)

        self.throws = []
        if self.points:
            rows = Throw.query.filter(
                Throw.point_id.in_(list(self.points)),
                Throw.team_organization_id == get_current_team_id(),
            ).order_by(Throw.id).all()
            for t in rows:
                self.throws.append({
                    'id': t.id, 'point_id': t.point_id, 'game_id': self.game_of_point[t.point_id].id,
                    'thrower_id': t.thrower_id, 'receiver_id': t.receiver_id,
                    'turnover': t.throw_type == 'throwaway',
                    'kind': throw_kind(t.x_start, t.y_start, t.x_end, t.y_end),
                    'side': None if t.break_throw is None else ('break' if t.break_throw else 'open'),
                    'depth': depth_zone(t.x_start), 'lane': lane(t.y_start),
                    'x_start': t.x_start, 'y_start': t.y_start, 'x_end': t.x_end, 'y_end': t.y_end,
                    'throwing_event_id': t.throwing_event_id,
                    **context[t.point_id],
                })

        # Per point, the events in recorded order (possession analysis and
        # the turnover log need the order; drops/stalls/goals give touches).
        self.events_by_point = {
            pid: sorted(point.events, key=lambda e: e.id) for pid, point in self.points.items()
        }
        # Points with full stats (not just taken live on Game Day)
        self.analysed = {pid for pid, events in self.events_by_point.items() if events}

    # --- slicing ---------------------------------------------------------

    def throws_for(self, player_id=None, game_ids=None):
        return [t for t in self.throws
                if (player_id is None or t['thrower_id'] == player_id)
                and (game_ids is None or t['game_id'] in game_ids)]

    def events_for(self, player_id=None, game_ids=None, types=None):
        out = []
        for pid, events in self.events_by_point.items():
            if game_ids is not None and self.game_of_point[pid].id not in game_ids:
                continue
            for e in events:
                if e.is_opponent or (player_id is not None and e.player_id != player_id):
                    continue
                if types is None or e.event_type in types:
                    out.append(e)
        return out


# --- building blocks ---------------------------------------------------------

def bucket_stats(throws, key):
    """{value: {attempts, turnovers, completion_rate}} for one dimension."""
    out = defaultdict(lambda: {'attempts': 0, 'turnovers': 0})
    for t in throws:
        value = t.get(key)
        if value is None:
            continue
        out[value]['attempts'] += 1
        out[value]['turnovers'] += t['turnover']
    for b in out.values():
        b['completion_rate'] = _rate(b['attempts'] - b['turnovers'], b['attempts'])
    return dict(out)


def handling_summary(data, player_id=None, game_ids=None):
    """Throws, touches and turnovers for a player (or the whole team)."""
    throws = data.throws_for(player_id, game_ids)
    counts = defaultdict(int)
    for e in data.events_for(player_id, game_ids, types=('drop', 'stall', 'goal', 'catch')):
        if e.is_offensive is not False:
            counts[e.event_type] += 1
    throwaways = sum(t['turnover'] for t in throws)
    # Each possession a player has ends in a throw, a stall or a goal
    # caught; a drop is a touch that never became a possession.
    touches = len(throws) + counts['stall'] + counts['goal'] + counts['drop']
    turnovers = throwaways + counts['drop'] + counts['stall']
    hucks = [t for t in throws if t['kind'] == 'huck']
    breaks = [t for t in throws if t['side'] == 'break']
    sided = [t for t in throws if t['side'] is not None]
    receptions = counts['catch'] + counts['goal'] + counts['drop']
    return {
        'throws': len(throws), 'throwaways': throwaways, 'drops': counts['drop'],
        'stalls': counts['stall'], 'touches': touches, 'turnovers': turnovers,
        'completion_rate': _rate(len(throws) - throwaways, len(throws)),
        'turnovers_per_10': 10.0 * turnovers / touches if touches else None,
        'huck_attempts': len(hucks),
        'huck_completion_rate': _rate(sum(not t['turnover'] for t in hucks), len(hucks)),
        'break_attempts': len(breaks),
        'break_completion_rate': _rate(sum(not t['turnover'] for t in breaks), len(breaks)),
        'break_share': _rate(len(breaks), len(sided)),
        'receptions': receptions,
        'drop_rate': _rate(counts['drop'], receptions),
    }


def breakdown(data, player_id=None, game_ids=None):
    """Each dimension's buckets for the player, side by side with the team."""
    mine = data.throws_for(player_id, game_ids)
    team = data.throws_for(None, game_ids)
    total_turnovers = sum(t['turnover'] for t in mine)
    sections = []
    for key, title, values in DIMENSIONS:
        player_buckets = bucket_stats(mine, key)
        team_buckets = bucket_stats(team, key)
        rows = []
        for value, label in values:
            p = player_buckets.get(value, {'attempts': 0, 'turnovers': 0, 'completion_rate': None})
            t = team_buckets.get(value, {'attempts': 0, 'turnovers': 0, 'completion_rate': None})
            rows.append({
                'value': value, 'label': label,
                'attempts': p['attempts'], 'turnovers': p['turnovers'],
                'completion_rate': p['completion_rate'],
                'team_completion_rate': t['completion_rate'],
                'turnover_share': _rate(p['turnovers'], total_turnovers),
                'enough': p['attempts'] >= MIN_ATTEMPTS,
            })
        if any(r['attempts'] for r in rows):
            sections.append({'key': key, 'title': title, 'rows': rows})
    return sections


def zone_grid(data, player_id=None, game_ids=None):
    """Completion by where the throw was made: lanes (rows) x depth (cols)."""
    mine = data.throws_for(player_id, game_ids)
    team = data.throws_for(None, game_ids)

    def cells(throws):
        out = defaultdict(lambda: [0, 0])
        for t in throws:
            if t['depth'] and t['lane']:
                out[(t['lane'], t['depth'])][0] += 1
                out[(t['lane'], t['depth'])][1] += t['turnover']
        return out

    mine_cells, team_cells = cells(mine), cells(team)
    rows = []
    for lane_key, lane_label, _, _ in LANES:
        row = {'label': lane_label, 'cells': []}
        for depth_key, depth_label, _, _ in DEPTH_ZONES:
            attempts, turnovers = mine_cells[(lane_key, depth_key)]
            team_attempts, team_turnovers = team_cells[(lane_key, depth_key)]
            rate = _rate(attempts - turnovers, attempts)
            team_rate = _rate(team_attempts - team_turnovers, team_attempts)
            row['cells'].append({
                'attempts': attempts, 'turnovers': turnovers, 'completion_rate': rate,
                'team_completion_rate': team_rate,
                # How much worse than the team here, in percentage points
                'vs_team': (rate - team_rate) if rate is not None and team_rate is not None else None,
            })
        rows.append(row)
    return {'columns': [label for _, label, _, _ in DEPTH_ZONES], 'rows': rows}


# --- focus areas -------------------------------------------------------------

def _focus_text(key, value):
    label = VALUE_LABELS[(key, value)]
    return FOCUS_PHRASES[key].format(label=label, lower=label[0].lower() + label[1:])


def focus_areas(data, player_id, game_ids=None, limit=3):
    """The player's weakest and strongest areas compared to the team.

    Ranked by extra turnovers: throws x (team completion - player
    completion), so a big gap on a handful of throws doesn't outrank a
    smaller gap on a lot of them."""
    mine = data.throws_for(player_id, game_ids)
    team = data.throws_for(None, game_ids)
    weak, strong = [], []
    for key, _, values in DIMENSIONS:
        player_buckets = bucket_stats(mine, key)
        team_buckets = bucket_stats(team, key)
        for value, _ in values:
            p, t = player_buckets.get(value), team_buckets.get(value)
            if not p or not t or p['attempts'] < MIN_ATTEMPTS:
                continue
            gap = p['completion_rate'] - t['completion_rate']
            extra = -gap / 100.0 * p['attempts']
            item = {
                'key': f'{key}:{value}', 'dimension': key, 'value': value,
                'text': _focus_text(key, value),
                'attempts': p['attempts'], 'turnovers': p['turnovers'],
                'completion_rate': p['completion_rate'],
                'team_completion_rate': t['completion_rate'],
                'gap': gap, 'extra_turnovers': extra,
            }
            if gap <= -5 and extra >= 1:
                weak.append(item)
            elif gap >= 5 and -extra >= 1:
                strong.append(item)

    # Catching and holding on to it are focus areas too.
    me, us = handling_summary(data, player_id, game_ids), handling_summary(data, None, game_ids)
    if me['receptions'] >= MIN_ATTEMPTS and me['drop_rate'] is not None and us['drop_rate'] is not None:
        gap = us['drop_rate'] - me['drop_rate']  # catch rate gap
        extra = -gap / 100.0 * me['receptions']
        if gap <= -5 and extra >= 1:
            weak.append({'key': 'catching', 'dimension': 'catching', 'value': 'drops',
                         'text': 'Catching', 'attempts': me['receptions'], 'turnovers': me['drops'],
                         'completion_rate': 100 - me['drop_rate'],
                         'team_completion_rate': 100 - us['drop_rate'],
                         'gap': gap, 'extra_turnovers': extra})
    if me['stalls'] >= 2:
        weak.append({'key': 'stalls', 'dimension': 'stalls', 'value': 'stalls',
                     'text': 'Getting stalled', 'attempts': me['touches'], 'turnovers': me['stalls'],
                     'completion_rate': None, 'team_completion_rate': None, 'gap': None,
                     'extra_turnovers': float(me['stalls'])})

    weak.sort(key=lambda i: -i['extra_turnovers'])
    strong.sort(key=lambda i: i['extra_turnovers'])
    return {'weak': _distinct(weak)[:limit], 'strong': _distinct(strong)[:2],
            'min_attempts': MIN_ATTEMPTS, 'throws': len(mine)}


def _distinct(items):
    """One item per dimension, so 'hucks' and 'own third' don't both
    crowd out everything else when they're the same throws."""
    seen, out = set(), []
    for item in items:
        if item['dimension'] not in seen:
            seen.add(item['dimension'])
            out.append(item)
    return out


# --- over time ---------------------------------------------------------------

def _rolling(values, window=ROLLING_WINDOW):
    out = []
    for i in range(len(values)):
        recent = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(round(sum(recent) / len(recent), 1) if recent else None)
    return out


def game_trends(data, player_id=None, game_ids=None):
    """Per game the player (or team) played: turnovers per 10 touches,
    completion, huck completion and break-side share, with rolling averages."""
    played = (data.games_played[player_id] if player_id is not None
              else {g.id for g in data.games})
    if game_ids is not None:
        played = played & set(game_ids)
    rows = []
    for game in data.games:
        if game.id not in played:
            continue
        s = handling_summary(data, player_id, {game.id})
        if not s['touches']:
            continue
        rows.append({
            'label': f"{game.date.strftime('%d %b') if game.date else '?'} vs {game.opponent}",
            'turnovers_per_10': round(s['turnovers_per_10'], 1) if s['turnovers_per_10'] is not None else None,
            'completion_rate': round(s['completion_rate'], 1) if s['completion_rate'] is not None else None,
            'huck_completion_rate': (round(s['huck_completion_rate'], 1)
                                     if s['huck_completion_rate'] is not None else None),
            'break_share': round(s['break_share'], 1) if s['break_share'] is not None else None,
            'hucks': s['huck_attempts'],
        })
    metrics = ['turnovers_per_10', 'completion_rate', 'huck_completion_rate', 'break_share', 'hucks']
    return {
        'labels': [r['label'] for r in rows],
        **{m: [r[m] for r in rows] for m in metrics},
        **{f'{m}_rolling': _rolling([r[m] for r in rows]) for m in metrics},
        'window': ROLLING_WINDOW,
    }


COMPARED_METRICS = [
    # key, label, higher is better, minimum sample key
    ('completion_rate', 'Completion %', True, 'throws'),
    ('turnovers_per_10', 'Turnovers per 10 touches', False, 'touches'),
    ('huck_completion_rate', 'Huck completion %', True, 'huck_attempts'),
    ('break_completion_rate', 'Break-side completion %', True, 'break_attempts'),
    ('drop_rate', 'Drop %', False, 'receptions'),
]


def compare_periods(data, player_id, current_ids, baseline_ids, current_label, baseline_label):
    """The player's current period against their own baseline."""
    if not current_ids or not baseline_ids:
        return None
    now = handling_summary(data, player_id, current_ids)
    before = handling_summary(data, player_id, baseline_ids)
    if not now['touches'] or not before['touches']:
        return None
    rows = []
    for key, label, higher_better, sample in COMPARED_METRICS:
        a, b = now[key], before[key]
        if a is None or b is None or now[sample] < 3 or before[sample] < 3:
            continue
        delta = a - b
        # A change smaller than this is noise, not a trend.
        threshold = 0.5 if key == 'turnovers_per_10' else 3
        if abs(delta) < threshold:
            verdict = 'same'
        else:
            verdict = 'better' if (delta > 0) == higher_better else 'worse'
        rows.append({'label': label, 'current': a, 'baseline': b, 'delta': delta,
                     'verdict': verdict, 'current_n': now[sample], 'baseline_n': before[sample]})
    return {'current_label': current_label, 'baseline_label': baseline_label, 'rows': rows}


def period_ids(all_games, tournament_id=None, game_id=None, player_games=None):
    """Which games are 'now' and which are the baseline before them.

    A selected game or tournament is compared with everything before it;
    with no filter, the latest tournament the player played in is compared
    with everything before that."""
    dated = [g for g in all_games if g.date]
    if game_id:
        current = [g for g in all_games if g.id == game_id]
        if not current or not current[0].date:
            return None
        start = current[0].date
        label = f'vs {current[0].opponent}'
    else:
        tournaments = {}
        for g in all_games:
            if g.tournament_id and g.tournament and (player_games is None or g.id in player_games):
                tournaments[g.tournament_id] = g.tournament
        if tournament_id:
            tournament = tournaments.get(tournament_id)
        else:
            ordered = sorted(tournaments.values(), key=lambda t: str(t.start_date or ''))
            tournament = ordered[-1] if ordered else None
        if not tournament:
            return None
        current = [g for g in all_games if g.tournament_id == tournament.id]
        starts = [g.date for g in current if g.date]
        if not starts:
            return None
        start = min(starts)
        label = tournament.name
    baseline = [g for g in dated if g.date < start and g not in current]
    if not baseline:
        return None
    return {'current': {g.id for g in current}, 'baseline': {g.id for g in baseline},
            'current_label': label, 'baseline_label': 'earlier games'}


def repeat_focus(data, player_id, all_games, tournaments=3):
    """If the same thing has been the top focus area in each of the
    player's last few tournaments, it isn't getting fixed: say so."""
    by_tournament = defaultdict(set)
    starts = {}
    for g in all_games:
        if g.tournament_id and g.tournament:
            by_tournament[g.tournament_id].add(g.id)
            starts[g.tournament_id] = (str(g.tournament.start_date or ''), g.tournament.name)
    tops = []
    for tid in sorted(by_tournament, key=lambda t: starts[t]):
        weak = focus_areas(data, player_id, by_tournament[tid], limit=1)['weak']
        if data.throws_for(player_id, by_tournament[tid]):
            tops.append((starts[tid][1], weak[0] if weak else None))
    recent = tops[-tournaments:]
    if len(recent) < tournaments or any(item is None for _, item in recent):
        return None
    if len({item['key'] for _, item in recent}) == 1:
        return {'text': recent[-1][1]['text'], 'tournaments': [name for name, _ in recent]}
    return None


# --- turnover log, map and clips ---------------------------------------------

def _video_link(game, seconds):
    if not game.youtube_link or seconds is None:
        return None
    vid = youtube_id(game.youtube_link)
    return f'https://www.youtube.com/watch?v={vid}&t={int(seconds)}s' if vid else None


def turnover_log(data, player_id, game_ids=None):
    """Each of the player's turnovers, with where it went and a link to
    the video or clips of that point when there are any."""
    throw_by_event = {t['throwing_event_id']: t for t in data.throws if t['turnover']}
    out = []
    for e in data.events_for(player_id, game_ids, types=OUR_TURNOVERS):
        if e.is_offensive is False:
            continue
        point = data.points[e.point_id]
        game = data.game_of_point[e.point_id]
        throw = throw_by_event.get(e.id)
        seconds = point.timestamp_in_video
        out.append({
            'type': e.event_type,
            'game': game, 'point': point,
            'score': f'{point.our_score_before or 0}-{point.their_score_before or 0}',
            'kind': THROW_KIND_LABELS.get(throw['kind']) if throw else None,
            'side': throw['side'] if throw else None,
            'zone': (f"{LANE_LABELS.get(lane(e.field_position_y), '')}, "
                     f"{DEPTH_LABELS.get(depth_zone(e.field_position_x), '')}"),
            'x_start': throw['x_start'] if throw else None,
            'y_start': throw['y_start'] if throw else None,
            'x_end': e.field_position_x, 'y_end': e.field_position_y,
            'video_url': _video_link(game, seconds),
            'has_clips': bool(point.clips),
        })
    out.sort(key=lambda r: (str(r['game'].date or ''), r['game'].id, r['point'].point_number))
    return out


# --- team ----------------------------------------------------------------------

def turnover_leaderboard(data, players, game_ids=None):
    """Turnovers per 10 touches for everyone with enough touches, lowest first."""
    rows = []
    for player in players:
        s = handling_summary(data, player.id, game_ids)
        if s['touches'] >= MIN_TOUCHES:
            rows.append({'player': player, **s})
    rows.sort(key=lambda r: r['turnovers_per_10'])
    return rows


def turnover_cost(data, game_ids=None):
    """After we turn it over, how often do they score before we get it back?
    Split by where they pick it up (where the turnover was marked)."""
    zones = {key: {'label': label, 'turnovers': 0, 'conceded': 0} for key, label, _, _ in DEPTH_ZONES}
    for pid, events in data.events_by_point.items():
        if game_ids is not None and data.game_of_point[pid].id not in game_ids:
            continue
        for i, e in enumerate(events):
            if e.event_type not in OUR_TURNOVERS or e.is_offensive is False:
                continue
            zone = depth_zone(e.field_position_x)
            if zone is None:
                continue
            outcome = None
            for later in events[i + 1:]:
                if later.event_type == 'scored_on':
                    outcome = 'conceded'
                    break
                if later.event_type in WE_REGAIN or later.event_type in ('catch', 'goal'):
                    outcome = 'recovered'
                    break
            zones[zone]['turnovers'] += 1
            zones[zone]['conceded'] += outcome == 'conceded'
    rows = []
    for key, _, _, _ in DEPTH_ZONES:
        z = zones[key]
        rows.append({**z, 'conceded_rate': _rate(z['conceded'], z['turnovers'])})
    total = sum(z['turnovers'] for z in rows)
    conceded = sum(z['conceded'] for z in rows)
    return {'rows': rows, 'turnovers': total, 'conceded': conceded,
            'conceded_rate': _rate(conceded, total)}


def practice_focus(data, current_ids=None, baseline_ids=None):
    """What the team should work on: the buckets that slipped most since
    the baseline, or (without one) where turnovers come from out of
    proportion to how often the throw is made."""
    current = data.throws_for(None, current_ids)
    if not current:
        return []
    items = []
    if baseline_ids:
        before = data.throws_for(None, baseline_ids)
        for key, _, values in DIMENSIONS:
            now_b, then_b = bucket_stats(current, key), bucket_stats(before, key)
            for value, _ in values:
                a, b = now_b.get(value), then_b.get(value)
                if not a or not b or a['attempts'] < MIN_ATTEMPTS or b['attempts'] < MIN_ATTEMPTS:
                    continue
                drop = b['completion_rate'] - a['completion_rate']
                if drop >= 5:
                    items.append({'dimension': key, 'text': _focus_text(key, value),
                                  'detail': f"{a['completion_rate']:.0f}% now vs {b['completion_rate']:.0f}% before",
                                  'attempts': a['attempts'], 'score': drop / 100 * a['attempts']})
    if not items:
        total = len(current)
        total_turnovers = sum(t['turnover'] for t in current)
        if not total_turnovers:
            return []
        for key, _, values in DIMENSIONS:
            if key in ('line', 'score', 'half'):
                continue  # situations, not something you drill
            buckets = bucket_stats(current, key)
            for value, _ in values:
                b = buckets.get(value)
                if not b or b['attempts'] < MIN_ATTEMPTS:
                    continue
                share_throws = 100 * b['attempts'] / total
                share_turnovers = 100 * b['turnovers'] / total_turnovers
                if share_turnovers - share_throws >= 5:
                    items.append({'dimension': key, 'text': _focus_text(key, value),
                                  'detail': f'{share_throws:.0f}% of throws but {share_turnovers:.0f}% of turnovers',
                                  'attempts': b['attempts'],
                                  'score': (share_turnovers - share_throws) / 100 * total_turnovers})
    items.sort(key=lambda i: -i['score'])
    return _distinct(items)[:3]


def direction_split(data, player_id, game_ids=None):
    """Which way the player throws: right (a right-hander's forehand side)
    or left (backhand side), and upfield or back, with completion each way."""
    groups = {key: [0, 0] for key in ('right', 'left', 'forward', 'back')}
    for t in data.throws_for(player_id, game_ids):
        if None in (t['x_start'], t['y_start'], t['x_end'], t['y_end']):
            continue
        dx, dy = t['x_end'] - t['x_start'], t['y_end'] - t['y_start']
        keys = ['forward' if dx > 0 else 'back']
        if abs(dy) >= 1:
            keys.append('right' if dy > 0 else 'left')
        for key in keys:
            groups[key][0] += 1
            groups[key][1] += not t['turnover']
    out = {}
    for pair in (('right', 'left'), ('forward', 'back')):
        total = sum(groups[k][0] for k in pair)
        for key in pair:
            n, completed = groups[key]
            out[key] = {'throws': n, 'share': _rate(n, total), 'completion_rate': _rate(completed, n)}
    return out
