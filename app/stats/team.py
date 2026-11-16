"""Team and game level stats."""
from flask import current_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.event import Event
from app.models.throws import Throw
from jinja2.utils import htmlsafe_json_dumps  # JSON that is safe inside <script>
from app.utils.team_filter import get_current_team_id

from app.stats.formulas import (OUR_TURNS, POSSESSION_CHANGES, REGAINS, get_point_starting_possession, goal_equivalents,
                                point_has_result, point_we_scored, possession_gap, scoring_efficiency)
from app.stats.players import get_players_base_stats, players_in_games
from app.stats.throwing import throw_kind
from app.stats.loaders import (game_line_points, game_points, has_plays, is_analysed, preload_game_points,
                               unthrown_throwaways)


def _point_gap(point):
    """possession_gap for a loaded point with full stats and a result."""
    return possession_gap(get_point_starting_possession(point) == 'offence',
                          point_we_scored(point), [e.event_type for e in point.events])


def _games_or_all(games):
    if games is None:
        games = Game.query.filter_by(team_organization_id=get_current_team_id()).all()
    games = games if isinstance(games, list) else [games]
    preload_game_points(games)
    return games


def find_incomplete_points(games=None):
    """Points with full stats whose possession changes can't produce the
    result (see formulas.possession_gap): something was missed while
    recording. Plain dicts, in game and point order."""
    found = []
    for game in sorted(_games_or_all(games), key=lambda g: (g.date is None, g.date, g.id)):
        for point in game_points(game):
            if is_analysed(point) and point_has_result(point):
                reason = _point_gap(point)
                if reason:
                    found.append({'point_id': point.id, 'point_number': point.point_number,
                                  'game_id': game.id, 'opponent': game.opponent,
                                  'date': game.date, 'reason': reason})
    return found


def calculate_scoring_efficiency(games=None):
    """Scoring efficiency (SE) for these games: goals / (goals + turns),
    counting both teams, from points with full stats. A goal is a point
    with a result; a turn is any recorded change of possession (ours or
    theirs). Points whose possession changes don't add up (a turn wasn't
    recorded) are left out, so they don't make turns look rarer than they
    are. None means every game the team has."""
    goals = turns = incomplete = 0
    for game in _games_or_all(games):
        for point in game_points(game):
            if not is_analysed(point):
                continue
            if point_has_result(point) and _point_gap(point):
                incomplete += 1
                continue
            goals += point_has_result(point)
            turns += sum(1 for e in point.events if e.event_type in POSSESSION_CHANGES)
    return {'se': scoring_efficiency(goals, turns), 'se_goals': goals, 'se_turns': turns,
            'se_incomplete': incomplete}


def calculate_team_averages(games=None):
    """What the player ratings are measured against, for these games: the
    scoring efficiency (SE) that prices turns, the team's goal equivalents
    per point played (where PER starts each player) and the Eff prior (the
    average player's turns in goal equivalents). See formulas.apply_ratings."""
    # Everyone who played in these games (not the active roster, which
    # ignores the season being viewed)
    players = players_in_games(games)
    player_stats = get_players_base_stats(players, games, pulls=False)  # ratings don't use pulls

    result = calculate_scoring_efficiency(games)
    se = result['se']

    ge_total = points = turns = player_count = 0
    for stats in player_stats.values():
        if stats['analysed_points'] > 0:
            player_count += 1
            points += stats['analysed_points']
            ge_total += goal_equivalents(stats, se)['total']
            turns += stats.get('turnovers', 0)

    result.update({
        'avg_ge_per_point': ge_total / points if points else 0,
        'eff_prior': se * turns / player_count if player_count else 0,
        'player_count': player_count,
    })
    return result

def calculate_game_stats(game):
    """
    Calculate per-game statistics using the SAME possession logic as team stats.
    """

    all_points = game_points(game)
    all_points = sorted(all_points, key=lambda p: p.point_number)


    stats = {
        'points_played': len(all_points),
        'o_line_points': 0,
        'd_line_points': 0,
        'o_line_conversions': 0,
        'd_line_conversions': 0,
        'turnovers': 0,
        'breaks': 0,
        'possessions': 0,
        'possessions_gained': 0,
        'clean_holds': 0,
        'clean_breaks': 0,
        # Points with full stats: possession numbers only come from these
        'analysed_points': 0,
        'analysed_o_line_points': 0,
        'analysed_d_line_points': 0,
        'scoring_possessions': 0,
        'goals': 0,
        'analysed_goals': 0,
        'unfinished_points': 0,
        # Points with full stats and a result: what clean hold / break % divide by
        'clean_hold_points': 0,
        'clean_break_points': 0,

        # REQUIRED by game_stats.html JS
        'point_flow': [],
    }


    total_possessions = 0
    d_possessions_gained = 0
    for point in all_points:
        point_events = list(point.events)

        # Determine starting possession (single source of truth)
        start_pos = get_point_starting_possession(point)
        is_o_point = start_pos == 'offence'
        is_d_point = start_pos == 'defence'

        analysed = has_plays(point_events)
        scored = point_we_scored(point)
        # Holds, breaks and conversion only count points that ended in a
        # goal: one stopped by the cap or half time was neither.
        finished = point_has_result(point)
        if not finished:
            stats['unfinished_points'] += 1
        if is_o_point and finished:
            stats['o_line_points'] += 1
            stats['clean_hold_points'] += analysed
        if is_d_point and finished:
            stats['d_line_points'] += 1
            stats['clean_break_points'] += analysed

        # Possessions and turnovers only exist for points with full stats:
        # a Game Day-only point has a line and a result but no plays.
        our_turnovers = our_possessions = None
        if analysed:
            stats['analysed_points'] += 1
            stats['analysed_o_line_points'] += is_o_point
            stats['analysed_d_line_points'] += is_d_point
            analysis = analyze_point_possessions(point, point_events)
            our_turnovers = analysis['our_turnovers']
            our_possessions = analysis['our_possessions']
            stats['turnovers'] += our_turnovers
            stats['possessions'] += our_possessions
            stats['possessions_gained'] += analysis['possessions_gained']
            total_possessions += our_possessions
            if is_d_point:
                d_possessions_gained += analysis['possessions_gained']
            if scored:
                stats['scoring_possessions'] += our_possessions
                stats['analysed_goals'] += 1

        stats['point_flow'].append({
            'point_number': getattr(point, 'point_number', len(stats['point_flow']) + 1),
            'our_score_after': getattr(point, 'our_score_after', None),
            'their_score_after': getattr(point, 'their_score_after', None),
            'scored': scored,
            'start_possession': start_pos,
            'analysed': analysed,
            'turnovers': our_turnovers,
            'possessions': our_possessions,
        })

        if scored:
            stats['goals'] += 1

            if is_o_point:
                stats['o_line_conversions'] += 1
                if analysed and our_turnovers == 0:
                    stats['clean_holds'] += 1

            if is_d_point:
                stats['d_line_conversions'] += 1
                stats['breaks'] += 1
                if analysed and our_turnovers == 0:
                    stats['clean_breaks'] += 1

    # Final derived metrics (MATCH TEAM STATS)
    stats['o_line_conversion_rate'] = (
        stats['o_line_conversions'] / stats['o_line_points'] * 100
        if stats['o_line_points'] else 0
    )

    stats['d_line_conversion_rate'] = (
        stats['d_line_conversions'] / stats['d_line_points'] * 100
        if stats['d_line_points'] else 0
    )

    stats['clean_hold_percentage'] = (
        stats['clean_holds'] / stats['clean_hold_points'] * 100
        if stats['clean_hold_points'] else 0
    )

    stats['clean_break_percentage'] = (
        stats['clean_breaks'] / stats['clean_break_points'] * 100
        if stats['clean_break_points'] else 0
    )

    stats['avg_turnovers_per_point'] = (
        stats['turnovers'] / stats['analysed_points']
        if stats['analysed_points'] else 0
    )

    # Every possession we had (points with full stats) per goal we scored
    # in those points: possessions that ended in a turn count too.
    stats['possessions_per_goal'] = (
        total_possessions / stats['analysed_goals']
        if stats['analysed_goals'] else 0
    )

    # Times we won the disc back on D-line points, per D-line point with
    # full stats (the same as the team page)
    stats['avg_possessions_gained_per_point'] = (
        d_possessions_gained / stats['analysed_d_line_points']
        if stats['analysed_d_line_points'] else 0
    )

    return stats

def calculate_performance_trends(games):
    """Calculate team performance trends over time"""
    if not games:
        return {
            'dates': [],
            'labels': [],
            'o_line_efficiency': [],
            'd_line_efficiency': [],
            'break_percentage': []
        }
    
    # Filter out games with no points
    preload_game_points(games)
    games_with_points = [game for game in games if game_points(game)]
    
    # If no games with points, return empty data
    if not games_with_points:
        return {
            'dates': [],
            'labels': [],
            'o_line_efficiency': [],
            'd_line_efficiency': [],
            'break_percentage': []
        }
    
    # Sort games by date using string representation (safest approach)
    sorted_games = sorted(games_with_points, key=lambda g: str(g.date) if g.date else "")
    
    # Calculate metrics for each game
    dates = []
    labels = []
    o_line_efficiency = []
    d_line_efficiency = []
    break_percentage = []
    
    for game in sorted_games:
        # Add date for sorting purposes
        if game.date:
            dates.append(game.date.strftime('%Y-%m-%d') if hasattr(game.date, 'strftime') else str(game.date))
        else:
            dates.append('Unknown')
        
        # Create custom label with opposition and tournament name
        # Use game.opponent instead of game.opposition_team
        opposition_name = game.opponent if hasattr(game, 'opponent') and game.opponent else "Unknown"
        tournament_name = game.tournament.name if hasattr(game, 'tournament') and game.tournament else "Unknown"
        custom_label = f"{opposition_name} ({tournament_name})"
        labels.append(custom_label)

        
        # Calculate O-line efficiency - handle both query objects and lists
        o_points = [p for p in game_line_points(game, 'O-line') if point_has_result(p)]
        
        o_points_count = len(o_points)
        o_conversions = sum(1 for p in o_points if point_we_scored(p))
        o_line_efficiency.append((o_conversions / o_points_count * 100) if o_points_count > 0 else 0)
        
        # Calculate D-line efficiency - handle both query objects and lists
        d_points = [p for p in game_line_points(game, 'D-line') if point_has_result(p)]
        
        d_points_count = len(d_points)
        d_conversions = sum(1 for p in d_points if point_we_scored(p))
        d_line_efficiency.append((d_conversions / d_points_count * 100) if d_points_count > 0 else 0)
        
        # Points broken by either team (Point.is_break: our D-line scored or
        # their D-line scored), as a share of points that ended in a goal.
        # Our own break rate is d_line_efficiency.
        all_points = [p for p in game_points(game) if point_has_result(p)]
        
        total_points = len(all_points)
        breaks = sum(1 for p in all_points if p.is_break)
        break_percentage.append((breaks / total_points * 100) if total_points > 0 else 0)
    
    return {
        'dates': htmlsafe_json_dumps(dates),
        'labels': htmlsafe_json_dumps(labels),
        'o_line_efficiency': htmlsafe_json_dumps(o_line_efficiency),
        'd_line_efficiency': htmlsafe_json_dumps(d_line_efficiency),
        'break_percentage': htmlsafe_json_dumps(break_percentage)
    }

def calculate_possession_based_team_metrics(games):
    """
    Team possession metrics using a single, consistent possession model.
    """

    if not games:
        return {
            'clean_hold_percentage': 0,
            'clean_break_percentage': 0,
            'regain_offense_count': 0,
            'avg_o_turnovers_per_point': 0,
            'avg_possessions_gained_per_point': 0,
            'possessions_per_goal': 0,
        }

    # Collect all points
    points = []
    for g in games:
        pts = game_points(g)
        points.extend(list(pts))

    if not points:
        return {
            'clean_hold_percentage': 0,
            'clean_break_percentage': 0,
            'regain_offense_count': 0,
            'avg_o_turnovers_per_point': 0,
            'avg_possessions_gained_per_point': 0,
            'possessions_per_goal': 0,
        }

    # Counters (points with full stats only: Game Day-only points have no
    # possessions recorded)
    o_points = 0
    d_points = 0

    clean_holds = 0
    clean_breaks = 0
    scored_after_turnover = 0

    o_turnovers_total = 0
    d_possessions_gained = 0

    goals_scored = 0
    total_possessions = 0
    # O / D points with a result: clean hold / break % divide by these
    clean_hold_points = clean_break_points = 0

    for point in points:
        if not is_analysed(point):
            continue  # Game Day only: no possessions recorded
        start_pos = get_point_starting_possession(point)
        is_o_point = start_pos == 'offence'
        is_d_point = start_pos == 'defence'

        finished = point_has_result(point)
        if is_o_point:
            o_points += 1
            clean_hold_points += finished
        elif is_d_point:
            d_points += 1
            clean_break_points += finished

        analysis = analyze_point_possessions(point, point.events)

        our_turnovers = analysis['our_turnovers']
        total_possessions += analysis['our_possessions']

        if is_o_point:
            o_turnovers_total += our_turnovers

        if is_d_point:
            d_possessions_gained += analysis['possessions_gained']

        if point_we_scored(point):
            goals_scored += 1

            if our_turnovers > 0:
                scored_after_turnover += 1

            if is_o_point and our_turnovers == 0:
                clean_holds += 1

            if is_d_point and our_turnovers == 0:
                clean_breaks += 1

    return {
        'clean_hold_percentage': (clean_holds / clean_hold_points * 100) if clean_hold_points else 0,
        'clean_break_percentage': (clean_breaks / clean_break_points * 100) if clean_break_points else 0,
        'regain_offense_count': scored_after_turnover,
        'avg_o_turnovers_per_point': (o_turnovers_total / o_points) if o_points else 0,
        'avg_possessions_gained_per_point': (d_possessions_gained / d_points) if d_points else 0,
        # Every possession we had per goal we scored (points with full
        # stats): possessions that ended in a turn count too
        'possessions_per_goal': (
            total_possessions / goals_scored if goals_scored else 0
        ),
    }

def calculate_team_summary(games):
    """Calculate team summary statistics"""
    summary = {
        'games_played': sum(1 for g in games if g.is_played),
        'wins': sum(1 for g in games if g.is_win),
        'losses': sum(1 for g in games if g.is_loss),
        'ties': sum(1 for g in games if g.is_tie),
        'total_points': 0,
        'o_line_points': 0,
        'o_line_conversions': 0,
        'd_line_points': 0,
        'd_line_conversions': 0,
        'breaks': 0,
        'holds': 0
    }
    
    # Safely count total points
    for game in games:
        try:
            points = game_points(game)
            summary['total_points'] += len(points)
        except Exception as e:
            current_app.logger.error(f"Error counting points for game {game.id}: {str(e)}")


    # Holds, breaks and conversion count points that ended in a goal: one
    # stopped by the cap or half time was neither held nor broken.
    for game in games:
        o_points = [p for p in game_line_points(game, 'O-line') if point_has_result(p)]
        d_points = [p for p in game_line_points(game, 'D-line') if point_has_result(p)]
        
        summary['o_line_points'] += len(o_points)
        summary['o_line_conversions'] += sum(1 for p in o_points if point_we_scored(p))
        summary['d_line_points'] += len(d_points)
        summary['d_line_conversions'] += sum(1 for p in d_points if point_we_scored(p))
        # Our breaks and holds (Point.is_break / is_hold count either team's)
        summary['breaks'] += sum(1 for p in d_points if point_we_scored(p))
        summary['holds'] += sum(1 for p in o_points if point_we_scored(p))

    summary['win_percentage'] = (
        (summary['wins'] / summary['games_played'] * 100) 
        if summary['games_played'] > 0 else 0
    )
    summary['o_line_conversion_rate'] = (
        (summary['o_line_conversions'] / summary['o_line_points'] * 100)
        if summary['o_line_points'] > 0 else 0
    )
    summary['d_line_conversion_rate'] = (
        (summary['d_line_conversions'] / summary['d_line_points'] * 100)
        if summary['d_line_points'] > 0 else 0
    )

    return summary

def analyze_point_possessions(point, events):
    """Our possessions and turnovers in one point with full stats.

    Uses the same rules as the stat recorder and formulas.possession_gap:
    a throwaway, drop or stall is our turn (they are only recorded while we
    have the disc); a block, forced or unforced turnover or Callahan wins it
    back. So the counts don't depend on the order events were saved in, or
    on Event.is_offensive (unreliable on older points).

      - our_turnovers: our throwaways, drops and stalls
      - possessions_gained: times we won the disc back from them
      - our_possessions: possessions we had: the first one if we received
        the pull, plus one for every time we won it back. A Callahan is a
        possession that ends in a goal straight away.
    """
    types = [getattr(e, 'event_type', None) for e in events or []]
    our_turnovers = sum(1 for t in types if t in OUR_TURNS)
    regains = sum(1 for t in types if t in REGAINS)
    started_on_offence = get_point_starting_possession(point) == 'offence'
    return {
        'our_turnovers': our_turnovers,
        'our_possessions': int(started_on_offence) + regains,
        'possessions_gained': regains,
    }


def calculate_additional_team_metrics(games):
    """Calculate additional team metrics for radar charts"""
    _empty = {
        'completion_rate': 0,
        'catch_rate': 0,
        'goals_per_point': 0,
        'assists_per_point': 0,
        'throws_per_point': 0,
        'hucks_per_point': 0,
        'blocks_per_point': 0,
        'turnovers_forced_per_point': 0,
        'break_throw_percentage': 0,
        'break_percentage': 0,
    }
    if not games:
        return _empty

    # Per-point rates count only points with full stats (not Game Day only)
    total_points = 0
    for game in games:
        try:
            total_points += sum(1 for p in game_points(game) if is_analysed(p))
        except Exception as e:
            current_app.logger.error(f"Error counting points for game {game.id}: {str(e)}")

    if total_points == 0:
        return _empty
    
    # Get point IDs for filtering
    point_ids = []
    for game in games:
        try:
            points = game_points(game)
            point_ids.extend([p.id for p in points])
        except Exception as e:
            current_app.logger.error(f"Error getting points for game {game.id}: {str(e)}")
    
    # Count all throws
    throws_query = Throw.query.filter_by(team_organization_id=get_current_team_id())
    throws_query = throws_query.filter(Throw.point_id.in_(point_ids))
    throws = throws_query.all()
    # Plus throwaways with no stored throw (thrown before any catch was
    # recorded in the point): still thrown, and not completed
    thrown = {t.throwing_event_id for t in throws}
    unthrown = sum(len(unthrown_throwaways(p.events, thrown)) for g in games for p in game_points(g))
    attempts = len(throws) + unthrown

    # Count completions and break throws
    completions = sum(1 for t in throws if t.is_completion)
    break_throws = sum(1 for t in throws if t.break_throw)

    # Count goals and assists
    # A Callahan is a goal (and a block), as for players
    goals_query = Event.query.filter(
        Event.event_type.in_(['goal', 'callahan']),
        Event.is_opponent.isnot(True),
        Event.team_organization_id == get_current_team_id()
    ).filter(Event.point_id.in_(point_ids))

    goals = goals_query.count()
    assists = sum(1 for t in throws if t.throw_type == 'assist')

    # Catch rate: passes caught (completed throws) out of passes caught
    # or dropped. A pickup isn't a pass.
    catches = completions

    drops = Event.query.filter_by(
        event_type='drop',
        team_organization_id=get_current_team_id()
    ).filter(Event.point_id.in_(point_ids)).count()

    # Blocks and takeaways (blocks, forced turnovers, Callahans) made on
    # D-line points with full stats: the per-D-point rates divide by those
    # points, so a block on an O-line point (after a turn) doesn't count.
    analysed_d_ids = [p.id for game in games for p in game_line_points(game, 'D-line') if is_analysed(p)]
    d_events = Event.query.filter(
        Event.is_opponent.isnot(True),
        Event.team_organization_id == get_current_team_id(),
        Event.point_id.in_(analysed_d_ids),
    )
    blocks = d_events.filter(Event.event_type.in_(['block', 'callahan'])).count() if analysed_d_ids else 0
    turnovers_forced = d_events.filter(
        Event.event_type.in_(['block', 'forced_turnover', 'callahan'])).count() if analysed_d_ids else 0

    # Count hucks
    # (20 m+ long and 15 m+ upfield, as everywhere else)
    hucks = sum(1 for t in throws if throw_kind(t.x_start, t.y_start, t.x_end, t.y_end) == 'huck')

    # Calculate D-line totals once: conversion from every point, per-D-point
    # rates from points with full stats
    d_points_count = 0
    d_conversions = 0
    analysed_d_points = 0

    for game in games:
        d_points = game_line_points(game, 'D-line')
        d_points_count += sum(1 for p in d_points if point_has_result(p))
        d_conversions += sum(1 for p in d_points if point_we_scored(p))
        analysed_d_points += sum(1 for p in d_points if is_analysed(p))

    # Break % (break throw rate) = percentage of throws that are break throws
    break_throw_percentage = (break_throws / len(throws)) * 100 if throws else 0

    # D-line conversion rate (kept for templates that reference break_percentage by name)
    break_percentage = (d_conversions / d_points_count) * 100 if d_points_count > 0 else 0

    # Calculate o-line points
    o_points_count = 0
    for game in games:
        try:
            o_points = game_line_points(game, 'O-line')
            o_points_count += len(o_points)
        except Exception as e:
            current_app.logger.error(f"Error calculating o-line stats for game {game.id}: {str(e)}")

    # Calculate throws per point correctly - total throws divided by total points
    throws_per_point = attempts / total_points if total_points > 0 else 0

    result = {
        # The team's passes caught out of passes thrown: a drop is an
        # incomplete pass (for a player's throwing, it's the receiver's)
        'completion_rate': (completions / (attempts + drops)) * 100 if attempts + drops else 0,
        'catch_rate': (catches / (catches + drops)) * 100 if (catches + drops) > 0 else 0,
        'goals_per_point': goals / total_points,
        'assists_per_point': assists / total_points,
        'throws_per_point': throws_per_point,
        'hucks_per_point': hucks / total_points,
        # blocks / takeaways on D-line points per D-line point (full stats)
        'blocks_per_point': blocks / analysed_d_points if analysed_d_points > 0 else 0,
        'turnovers_forced_per_point': turnovers_forced / analysed_d_points if analysed_d_points > 0 else 0,
        'break_throw_percentage': break_throw_percentage,
        'break_percentage': break_percentage,       # D-line conversion rate alias
    }

    return result

def get_previous_period_games(season, tournament_id, squad=None):
    """Games from the period before for comparison: the tournament before
    this one in the same season, or the season before this one."""
    from app.models.season import Season

    team_id = get_current_team_id()
    if tournament_id:
        current_tournament = Tournament.query.filter_by(id=tournament_id, team_organization_id=team_id).first()
        if current_tournament and current_tournament.start_date:
            prev_tournament = Tournament.query.filter(
                Tournament.season_id == current_tournament.season_id,
                Tournament.squad_id == current_tournament.squad_id,
                Tournament.start_date < current_tournament.start_date,
                Tournament.team_organization_id == team_id
            ).order_by(Tournament.start_date.desc()).first()
            if prev_tournament:
                return Game.query.filter_by(tournament_id=prev_tournament.id, team_organization_id=team_id).all()
    elif season is not None:
        prev_season = (Season.query.filter(Season.team_organization_id == team_id, Season.year < season.year)
                       .order_by(Season.year.desc()).first())
        if prev_season:
            query = Game.query.filter_by(season_id=prev_season.id, team_organization_id=team_id)
            if squad is not None:
                query = query.filter_by(squad_id=squad.id)
            return query.all()

    # Default: return empty list if no previous period found
    return []

def process_heatmap_data(player_id=None, opposition_team=None, limit=None, point_ids=None):
    """Process throw data for heatmap visualization with limit and point filtering"""
    heatmap_data = []
    
    # Helper function to add events to heatmap_data
    def add_events_to_heatmap(query, event_type):
        for event in query.all():
            if event.field_position_x is not None and event.field_position_y is not None:
                heatmap_data.append({
                    'x': event.field_position_x,
                    'y': event.field_position_y,
                    'value': 1,
                    'type': event_type
                })

    # 1. Get Throw Start Locations
    throw_query = Throw.query.filter_by(team_organization_id=get_current_team_id())
    if player_id:
        throw_query = throw_query.filter(Throw.thrower_id == player_id)
    if point_ids:
        throw_query = throw_query.filter(Throw.point_id.in_(point_ids))
    if limit:
        # The most recent throws
        throw_query = throw_query.order_by(Throw.id.desc()).limit(limit)
    for throw in throw_query.all():
        if throw.x_start is not None and throw.y_start is not None:
            heatmap_data.append({
                'x': throw.x_start,
                'y': throw.y_start,
                'value': 1,
                'type': 'throw_start'
            })

    # 2. Get Goal, Throwaway, and Scored On Locations from Events
    event_types_to_query = ['goal', 'throwaway', 'scored_on']
    for event_type in event_types_to_query:
        event_query = Event.query.filter_by(
            event_type=event_type,
            team_organization_id=get_current_team_id()
        )
        if player_id:
            event_query = event_query.filter_by(player_id=player_id)
        if point_ids:
            event_query = event_query.filter(Event.point_id.in_(point_ids))
        if limit:
            event_query = event_query.order_by(Event.id.desc()).limit(limit)
        
        add_events_to_heatmap(event_query, event_type)

    return heatmap_data

def generate_player_connections(opposition_team=None, min_connections=1, point_ids=None):
    """Generate player connection data using Throws model with minimum connection threshold"""
    query = Throw.query.filter(
        Throw.thrower_id.isnot(None),
        Throw.receiver_id.isnot(None),
        Throw.team_organization_id == get_current_team_id()
    )
    
    if opposition_team:
        query = query.filter(Throw.opposition_team == opposition_team)
    if point_ids:
        query = query.filter(Throw.point_id.in_(point_ids))
    
    throws = query.all()

    # Track unique players and their connections
    players = set()
    connections = {}
    
    for throw in throws:
        players.add(throw.thrower_id)
        players.add(throw.receiver_id)
        
        key = f"{throw.thrower_id}-{throw.receiver_id}"
        if key in connections:
            connections[key]['value'] += 1
        else:
            connections[key] = {
                'source': throw.thrower_id,
                'target': throw.receiver_id,
                'value': 1
            }
    
    # Filter connections by minimum threshold
    if min_connections > 1:
        connections = {k: v for k, v in connections.items() if v['value'] >= min_connections}
    
    # Create nodes list - only include players that have connections after filtering
    player_ids_in_connections = set()
    for conn in connections.values():
        player_ids_in_connections.add(conn['source'])
        player_ids_in_connections.add(conn['target'])
    
    players_by_id = {p.id: p for p in Player.query.filter(
        Player.id.in_(player_ids_in_connections),
        Player.team_organization_id == get_current_team_id()
    )} if player_ids_in_connections else {}
    nodes = []
    for player_id in player_ids_in_connections:
        player = players_by_id.get(player_id)
        if player:
            nodes.append({
                'id': player.id,
                'name': player.name,
                'jersey_number': player.jersey_number,
                'position': player.position
            })
    
    return {
        'nodes': nodes,
        'links': list(connections.values())
    }
