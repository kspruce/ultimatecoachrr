"""One point, play by play: the events in the order they were recorded, split
into possessions, with the throws between them and the numbers a coach wants
from a single point.

Positions are saved as if we attack the right-hand endzone (see
app/stats/throwing.py): x 0-100 m upfield, y 0-37 m across.

Possession follows the same rules as the stat recorder
(stats/record.html, handlePossessionChange): a throwaway, drop or stall loses
the disc, a block, forced/unforced turnover or Callahan wins it back. It is
worked out again here rather than read from Event.is_offensive so older
points recorded before that flag was reliable still replay correctly.
"""
import math

from app.stats.throwing import (
    DEPTH_LABELS, LANE_LABELS, depth_zone, is_break_throw, lane, throw_kind,
)

# Our touches: the disc is in this player's hands
TOUCHES = {'catch', 'pickup', 'assist', 'hockey_assist'}
# How we lose the disc
LOSSES = {'throwaway', 'drop', 'stall'}
# How we win it back while defending
GAINS = {'block', 'forced_turnover', 'unforced_turnover', 'callahan'}
# Not part of play
IGNORED = {'substitution'}

EVENT_LABELS = {
    'catch': 'Catch', 'pickup': 'Pickup', 'assist': 'Assist',
    'hockey_assist': 'Hockey assist', 'goal': 'Goal', 'throwaway': 'Throwaway',
    'drop': 'Drop', 'stall': 'Stall', 'block': 'Block',
    'forced_turnover': 'Forced turnover', 'unforced_turnover': 'Unforced turnover',
    'callahan': 'Callahan', 'scored_on': 'Scored on', 'shutdown': 'Shutdown',
    'turnover': 'Turnover',
}

POSSESSION_ENDINGS = {
    'goal': 'Goal', 'callahan': 'Callahan', 'scored_on': 'They scored',
    'throwaway': 'Throwaway', 'drop': 'Drop', 'stall': 'Stall',
    'block': 'Block', 'forced_turnover': 'Forced turnover',
    'unforced_turnover': 'Unforced turnover', 'turnover': 'Turnover',
}


def _has_position(event):
    return event.field_position_x is not None and event.field_position_y is not None


def _player_label(event):
    if event.is_opponent:
        return 'Opponent'
    if event.player:
        return event.player.name
    return 'Unknown'


def _geometry(x1, y1, x2, y2, force):
    """Gain, length, kind and open/break side of a throw; None for each
    when a position is missing."""
    if None in (x1, y1, x2, y2):
        return {'gain': None, 'distance': None, 'kind': None, 'break': None}
    return {'gain': round(x2 - x1, 1), 'distance': round(math.hypot(x2 - x1, y2 - y1), 1),
            'kind': throw_kind(x1, y1, x2, y2), 'break': is_break_throw(x1, y1, x2, y2, force)}


def location_label(x, y):
    """'Attacking third · Middle', in plain words, or '' without a position."""
    if x is None or y is None:
        return ''
    return f'{DEPTH_LABELS[depth_zone(x)]} · {LANE_LABELS[lane(y)]}'


def outcome_label(point):
    """Hold, break, broken or their hold, from where we started."""
    if point.point_outcome not in ('scored', 'conceded'):
        return 'In progress'
    if point.starting_position == 'offense':
        return 'Hold' if point.point_outcome == 'scored' else 'Broken'
    return 'Break' if point.point_outcome == 'scored' else 'Their hold'


def build_point_replay(point, events, with_positions_only=True):
    """Everything the point page shows about the play, from the point's
    events (any order; they're sorted by id, the order they were recorded).

    Returns a dict of plain data: 'steps' (one per event on the field, for
    the replay), 'throws', 'possessions', 'stats', 'players' (per player on
    the line) and 'story' (the scorer and assists).

    with_positions_only leaves out events without a field position, which
    can't be drawn; the stored throws (app/stats/throw_rebuild.py) keep them.
    """
    ours = point.starting_position == 'offense'
    force = point.force_direction
    steps, throws, possessions = [], [], []
    players = {}
    holder = None  # the step index of whoever has the disc, on our possessions
    possession = None

    def player_row(event):
        if not event.player_id or event.is_opponent:
            return None
        row = players.get(event.player_id)
        if row is None:
            row = players[event.player_id] = {
                'player_id': event.player_id, 'name': event.player.name if event.player else 'Unknown',
                'jersey': event.player.jersey_number if event.player else None,
                'touches': 0, 'throws': 0, 'completions': 0, 'gain': 0.0,
                'turns': 0, 'blocks': 0, 'goals': 0, 'assists': 0, 'hockey_assists': 0,
            }
        return row

    def new_possession():
        p = {'number': len(possessions) + 1, 'ours': ours, 'steps': [], 'throws': 0,
             'completions': 0, 'start_x': None, 'end_x': None, 'ended_by': None}
        possessions.append(p)
        return p

    for event in sorted(events, key=lambda e: e.id):
        kind = event.event_type
        if kind in IGNORED or (with_positions_only and not _has_position(event)):
            continue
        if possession is None:
            possession = new_possession()

        x, y = event.field_position_x, event.field_position_y
        index = len(steps)
        step = {
            'index': index, 'event_id': event.id, 'event_type': kind,
            'label': EVENT_LABELS.get(kind, kind.replace('_', ' ').capitalize()),
            'x': x, 'y': y, 'ours': ours, 'possession': possession['number'],
            'player_id': None if event.is_opponent else event.player_id,
            'player': _player_label(event),
            'jersey': event.player.jersey_number if event.player and not event.is_opponent else None,
            'opponent': bool(event.is_opponent), 'throw': None,
            'where': location_label(x, y),
        }
        steps.append(step)
        possession['steps'].append(index)
        # How far we got: only where we held the disc, not where a
        # throwaway landed or a pass was dropped
        if x is not None and (not ours or kind in TOUCHES or kind == 'goal'):
            if possession['start_x'] is None:
                possession['start_x'] = x
            possession['end_x'] = x
        row = player_row(event)

        # The throw that got the disc here, on our possessions. The first
        # touch of a possession is the pickup: nobody threw it.
        source = steps[holder] if holder is not None else None
        if ours and kind == 'throwaway' and source is None and index > 0:
            # Picked up and thrown away with no catch recorded: thrown from
            # where the disc was won back.
            source = steps[index - 1]
        if ours and source is not None and kind in TOUCHES | {'goal', 'throwaway', 'drop'}:
            complete = kind not in ('throwaway', 'drop')
            # A throwaway is the thrower's event; otherwise the event is the
            # receiver's and the thrower is whoever had the disc.
            if kind == 'throwaway':
                thrower_id, thrower, receiver_id, receiver = step['player_id'], step['player'], None, None
            else:
                thrower_id, thrower = source['player_id'], source['player']
                receiver_id, receiver = step['player_id'], step['player']
            geo = _geometry(source['x'], source['y'], x, y, force)
            throw = {
                'index': len(throws), 'from_step': source['index'], 'to_step': index,
                'throwing_event_id': event.id if kind == 'throwaway' else source['event_id'],
                'receiving_event_id': None if kind == 'throwaway' else event.id,
                'x1': source['x'], 'y1': source['y'], 'x2': x, 'y2': y,
                'thrower_id': thrower_id, 'thrower': thrower,
                'receiver_id': receiver_id, 'receiver': receiver, 'complete': complete,
                'result': kind if not complete else ('goal' if kind == 'goal' else 'complete'),
                'role': {'assist': 'assist', 'hockey_assist': 'hockey_assist'}.get(source['event_type'], 'regular'),
                # A drop is the receiver's turnover, not an incomplete
                # throw for the thrower: it's drawn but not counted.
                'counted': kind != 'drop',
                'possession': possession['number'], **geo,
            }
            throws.append(throw)
            step['throw'] = throw['index']
            if throw['counted']:
                possession['throws'] += 1
                possession['completions'] += complete
                thrower_row = players.get(thrower_id) if thrower_id else None
                if thrower_row is not None:
                    thrower_row['throws'] += 1
                    if complete:
                        thrower_row['completions'] += 1
                        thrower_row['gain'] += geo['gain'] or 0

        # Who has the disc now, and the player's numbers
        if row is not None:
            if kind in TOUCHES or kind == 'goal':
                row['touches'] += 1
            if kind == 'goal':
                row['goals'] += 1
            elif kind == 'assist':
                row['assists'] += 1
            elif kind == 'hockey_assist':
                row['hockey_assists'] += 1
            elif kind in LOSSES and ours:
                row['turns'] += 1
            elif kind in ('block', 'forced_turnover', 'callahan') and not ours:
                row['blocks'] += 1
                if kind == 'callahan':
                    row['goals'] += 1
        holder = index if ours and kind in TOUCHES else None

        # Does the disc change hands?
        lost = ours and (kind in LOSSES or kind == 'turnover')
        won = not ours and (kind in GAINS or kind == 'turnover')
        if kind in ('goal', 'callahan', 'scored_on') or lost or won:
            possession['ended_by'] = POSSESSION_ENDINGS.get(kind, step['label'])
            possession = None
            if lost or won:
                ours = not ours
            holder = None

    for p in possessions:
        p['gain'] = round(p['end_x'] - p['start_x'], 1) if p['ours'] and p['start_x'] is not None else None
        p['first_step'] = p['steps'][0] if p['steps'] else None
        p['last_step'] = p['steps'][-1] if p['steps'] else None

    counted = [t for t in throws if t['counted']]
    completions = [t for t in counted if t['complete']]
    kinds = {}
    for t in completions:
        if t['kind']:
            kinds[t['kind']] = kinds.get(t['kind'], 0) + 1
    stats = {
        'possessions': len(possessions),
        'our_possessions': sum(1 for p in possessions if p['ours']),
        'throws': len(counted),
        'completions': len(completions),
        'completion_pct': round(100 * len(completions) / len(counted)) if counted else None,
        'turns': sum(1 for s in steps if s['ours'] and s['event_type'] in LOSSES | {'turnover'}),
        'blocks': sum(1 for s in steps if not s['ours'] and s['event_type'] in GAINS),
        'gain': round(sum(t['gain'] or 0 for t in completions), 1),
        'longest': max((t['distance'] for t in completions if t['distance'] is not None), default=None),
        'breaks': sum(1 for t in completions if t['break']),
        'hucks': kinds.get('huck', 0),
        'dumps': kinds.get('dump_swing', 0),
    }

    story = {'scorer': None, 'assist': None, 'hockey_assist': None, 'callahan': None}
    for s in steps:
        if s['event_type'] == 'goal':
            story['scorer'] = s['player']
        elif s['event_type'] == 'assist':
            story['assist'] = s['player']
        elif s['event_type'] == 'hockey_assist':
            story['hockey_assist'] = s['player']
        elif s['event_type'] == 'callahan':
            story['callahan'] = s['player']

    for row in players.values():
        row['gain'] = round(row['gain'], 1)

    return {'steps': steps, 'throws': throws, 'possessions': possessions,
            'stats': stats, 'players': players, 'story': story}
