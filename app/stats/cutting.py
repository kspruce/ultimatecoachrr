"""Cutting, mostly worked out from what's already recorded.

Every completed throw to a player is a cut that worked: where they caught
it, and the throw, say whether it was deep or under and to the open or
break side. The one thing the events can't tell us is a cutter who got
open and wasn't thrown to, so that's all the stat-taker has to tap
(CuttingSkill rows with outcome *_looked_off; 'unspecified' type when it
was logged with the one-tap button rather than the detailed cut log).
"""
from app.models.cutting_skill import CuttingSkill
from app.utils.team_filter import get_current_team_id

CUT_TYPES = [('open_deep', 'Open Deep'), ('break_deep', 'Break Deep'),
             ('open_under', 'Open Under'), ('break_under', 'Break Under')]
LOOKED_OFF = ('open_looked_off', 'guarded_looked_off')


def _rate(part, whole):
    return 100.0 * part / whole if whole else None


def derived_cuts(data, player_id=None, game_ids=None):
    """Completed throws that gained ground, as cuts. Dumps and swings are
    resets, not cuts, so they're left out."""
    cuts = []
    for t in data.throws:
        if t['turnover'] or t['receiver_id'] is None or t['kind'] in (None, 'dump_swing'):
            continue
        if player_id is not None and t['receiver_id'] != player_id:
            continue
        if game_ids is not None and t['game_id'] not in game_ids:
            continue
        depth = 'deep' if t['kind'] in ('mid', 'huck') else 'under'
        cuts.append({
            'player_id': t['receiver_id'], 'point_id': t['point_id'], 'depth': depth,
            'side': t['side'],
            'cutting_type': f"{t['side']}_{depth}" if t['side'] else None,
            'outcome': 'thrown_to',
            'field_position_x': t['x_end'], 'field_position_y': t['y_end'],
        })
    return cuts


def looked_off_records(point_ids):
    """Every cutting record on these points (any player), so we know which
    points somebody was tracking cuts on."""
    if not point_ids:
        return []
    return CuttingSkill.query.filter(
        CuttingSkill.point_id.in_(list(point_ids)),
        CuttingSkill.team_organization_id == get_current_team_id(),
    ).all()


def cut_profile(data, player_id, game_ids=None):
    """How often the player gets open and gets used, by type of cut."""
    point_ids = {pid for pid, g in data.game_of_point.items() if game_ids is None or g.id in game_ids}
    records = looked_off_records(point_ids)
    tracked_points = {r.point_id for r in records}

    def profile(pid):
        cuts = derived_cuts(data, pid, game_ids)
        mine = [r for r in records if pid is None or r.player_id == pid]
        looked_off = [r for r in mine if r.outcome in LOOKED_OFF]
        open_looked_off = [r for r in looked_off if r.outcome == 'open_looked_off']
        played = (data.points_played[pid] if pid is not None
                  else {p for pts in data.points_played.values() for p in pts})
        played = {p for p in played if p in point_ids}
        # Points counts player-points for the team, so per point is per player.
        player_points = (len(played) if pid is not None
                         else sum(len({p for p in pts if p in point_ids}) for pts in data.points_played.values()))
        tracked_cuts = [c for c in cuts if c['point_id'] in tracked_points]
        tracked_open = [r for r in open_looked_off if r.point_id in tracked_points]
        by_type = {}
        for key, label in CUT_TYPES:
            thrown = sum(c['cutting_type'] == key for c in cuts)
            looked = sum(r.cutting_type == key for r in looked_off)
            by_type[key] = {'label': label, 'thrown_to': thrown, 'looked_off': looked,
                            'total': thrown + looked, 'success_rate': _rate(thrown, thrown + looked)}
        sided = [c for c in cuts if c['side']]
        return {
            'receptions': len(cuts),
            'per_point': len(cuts) / player_points if player_points else None,
            'deep_share': _rate(sum(c['depth'] == 'deep' for c in cuts), len(cuts)),
            'break_share': _rate(sum(c['side'] == 'break' for c in sided), len(sided)),
            'unknown_side': len(cuts) - len(sided),
            'open_looked_off': len(open_looked_off),
            'looked_off': len(looked_off),
            'tracked_points': len(tracked_points & played) if pid is not None else len(tracked_points),
            # Of the times they were open (on points someone tracked), how
            # often did the disc come?
            'used_rate': _rate(len(tracked_cuts), len(tracked_cuts) + len(tracked_open)),
            'by_type': by_type,
            'cuts': cuts,
        }

    mine, team = profile(player_id), profile(None)
    preferred = max(CUT_TYPES, key=lambda kv: mine['by_type'][kv[0]]['total'])
    mine['preferred_cut'] = preferred[1] if mine['by_type'][preferred[0]]['total'] else 'N/A'
    mine['team'] = {k: team[k] for k in ('per_point', 'deep_share', 'break_share', 'used_rate')}
    return mine
