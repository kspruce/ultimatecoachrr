"""The team stats the season plan measures improvement with ("Measuring
improvement" in the 2027/28 season plan): base metrics per point, team
completion, breaks thrown and offensive yardage. Each player's own measures
(turnovers per touch, completed breaks, yardage) are in
app/stats/players.py.

Base metrics follow the "four metrics" team analysis (Ultiworld Tuesday
Tips, Spin Ultimate, 2016; the season plan cites HN Coach Corner, Base
Metric Analysis). They need only four things per point: the score, whether
we started on O or D, blocks and turnovers. So they use every point that
ended in a goal: its full stats where it has them, its Game Day record
where it was only taken live.

- Had the disc: an O point (we received the pull), or a D point where we
  won the disc back. On a Game Day-only D point, that's a goal, a block or
  Callahan, or one of our turnovers (we must have had it to turn it over).
- No-turn goal: a point we scored without a turnover of ours.
- Conversion rate: goals / points we had the disc.
- Perfect conversion rate: no-turn goals / points we had the disc.
- Recovery rate: goals scored after turning it over / (points we had the
  disc - no-turn goals): once we've turned it over, how often we still score.
- Successful-defence rate: D points where we got the disc / D points.
- Turnovers per point we had the disc.
"""
from app.models.gameday import GameDayEvent
from app.stats.formulas import OUR_TURNS, REGAINS, get_point_starting_possession, point_has_result, point_we_scored
from app.stats import turnovers as turnover_stats
from app.utils.team_filter import get_current_team_id

GAMEDAY_TURNS = ('throwaway', 'drop', 'stall')
GAMEDAY_REGAINS = ('block', 'callahan')


def _rate(part, whole):
    return 100.0 * part / whole if whole else None


def point_summaries(data, game_ids):
    """One row per point that ended in a goal: O or D start, scored, our
    turnovers, did we have the disc, and where the numbers came from."""
    points = [p for pid, p in data.points.items()
              if data.game_of_point[pid].id in game_ids and point_has_result(p)]
    gameday_only = [p.id for p in points if p.id not in data.analysed]
    gameday = {}
    if gameday_only:
        for point_id, kind in (GameDayEvent.query.with_entities(GameDayEvent.point_id, GameDayEvent.event_type)
                               .filter(GameDayEvent.point_id.in_(gameday_only),
                                       GameDayEvent.team_organization_id == get_current_team_id())):
            gameday.setdefault(point_id, []).append(kind)
    rows = []
    for p in points:
        offence = get_point_starting_possession(p) == 'offence'
        scored = point_we_scored(p)
        if p.id in data.analysed:
            types = [e.event_type for e in data.events_by_point[p.id]]
            turns = sum(1 for t in types if t in OUR_TURNS)
            regained = any(t in REGAINS for t in types)
            source = 'full'
        else:
            types = gameday.get(p.id, [])
            turns = sum(1 for t in types if t in GAMEDAY_TURNS)
            regained = scored or turns > 0 or any(t in GAMEDAY_REGAINS for t in types)
            source = 'gameday'
        rows.append({'point': p, 'offence': offence, 'scored': scored, 'turns': turns,
                     'had_disc': offence or regained, 'source': source})
    return rows


def base_metrics(rows):
    """The four-metric numbers for a list of point_summaries rows."""
    had = [r for r in rows if r['had_disc']]
    goals = sum(r['scored'] for r in rows)
    no_turn = sum(1 for r in rows if r['scored'] and r['turns'] == 0)
    with_turns = sum(1 for r in rows if r['scored'] and r['turns'] > 0)
    turns = sum(r['turns'] for r in rows)
    return {
        'points': len(rows),
        'had_disc': len(had),
        'goals': goals,
        'no_turn_goals': no_turn,
        'goals_after_a_turn': with_turns,
        'turnovers': turns,
        'conversion_rate': _rate(goals, len(had)),
        'perfect_conversion_rate': _rate(no_turn, len(had)),
        'recovery_rate': _rate(with_turns, len(had) - no_turn),
        'turnovers_per_had_disc_point': turns / len(had) if had else None,
    }


def team_measures(data, game_ids):
    """Every team number the season plan uses, for these games.
    data is a turnovers.ThrowingData holding (at least) these games."""
    rows = point_summaries(data, game_ids)
    o_rows = [r for r in rows if r['offence']]
    d_rows = [r for r in rows if not r['offence']]
    o, d, total = base_metrics(o_rows), base_metrics(d_rows), base_metrics(rows)
    d['successful_defence_rate'] = _rate(d['had_disc'], d['points'])
    d['breaks'] = d['goals']
    o['holds'] = o['goals']

    handling = turnover_stats.handling_summary(data, None, game_ids)
    analysed = [pid for pid in data.analysed if data.game_of_point[pid].id in game_ids]
    throws = data.throws_for(None, game_ids)
    completed = [t for t in throws if not t['turnover']]
    breaks = [t for t in throws if t['side'] == 'break']
    yards = sum(t['x_end'] - t['x_start'] for t in completed
                if t['x_start'] is not None and t['x_end'] is not None)
    return {
        'all': total, 'o': o, 'd': d,
        'full_points': len(analysed),
        'gameday_points': sum(1 for r in rows if r['source'] == 'gameday'),
        # From points with full stats
        'turnovers_per_point': handling['turnovers'] / len(analysed) if analysed else None,
        # Both completions: the team's passes caught (a drop is an
        # incomplete pass) and throwing completion (a drop is the
        # receiver's turnover, not an incomplete throw)
        'completion_rate': handling['pass_completion_rate'],
        'throwing_completion_rate': handling['completion_rate'],
        'break_attempts': len(breaks),
        'completed_breaks': sum(1 for t in breaks if not t['turnover']),
        'break_completion_rate': handling['break_completion_rate'],
        'sided_throws': sum(1 for t in throws if t['side'] is not None),
        'yards': yards,
        'yards_per_point': yards / len(analysed) if analysed else None,
    }
