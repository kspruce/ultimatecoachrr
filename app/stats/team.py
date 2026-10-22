"""Team and game level stats."""
from flask import current_app
from app import db
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.event import Event
from app.models.throws import Throw
from jinja2.utils import htmlsafe_json_dumps  # JSON that is safe inside <script>
from app.utils.team_filter import get_current_team_id

from app.stats.formulas import TURNOVER_EVENTS, calculate_unadjusted_per, get_point_starting_possession, point_we_scored
from app.stats.players import HUCK_DISTANCE, get_players_base_stats
from app.stats.loaders import preload_game_points, game_points, game_line_points, is_analysed


def calculate_team_averages(games=None):
    """
    Calculate team averages for PER normalization with optimizations
    """
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Use batch loading for player stats
    player_stats = get_players_base_stats(players, games)
    
    totals = {
        'o_line_plus_minus': 0,
        'o_line_points': 0,
        'd_line_plus_minus': 0,
        'd_line_points': 0,
        'uper_total': 0,
        'player_count': 0
    }

    # First pass to calculate basic averages (points with full stats only)
    for player_id, stats in player_stats.items():
        if stats['analysed_points'] > 0:
            totals['player_count'] += 1
            totals['o_line_plus_minus'] += stats.get('o_line_plus_minus', 0)
            totals['o_line_points'] += stats.get('analysed_o_line_points', 0)
            totals['d_line_plus_minus'] += stats.get('d_line_plus_minus', 0)
            totals['d_line_points'] += stats.get('analysed_d_line_points', 0)
    
    # Calculate initial averages
    initial_avgs = {
        'avg_o_line_plus_minus_per_point': (totals['o_line_plus_minus'] / totals['o_line_points']) if totals['o_line_points'] > 0 else 0,
        'avg_d_line_plus_minus_per_point': (totals['d_line_plus_minus'] / totals['d_line_points']) if totals['d_line_points'] > 0 else 0,
        'avg_uper': 1  # Initial placeholder
    }
    
    # Second pass to calculate uPER using the initial averages
    for player_id, stats in player_stats.items():
        if stats['analysed_points'] > 0:
            # Calculate unadjusted PERwithout the plus-minus component
            # since we don't have the final team averages yet
            raw_uper = calculate_unadjusted_per(stats)
            totals['uper_total'] += raw_uper
    
    # Update with final avg_uper
    initial_avgs['avg_uper'] = totals['uper_total'] / totals['player_count'] if totals['player_count'] > 0 else 1
    
    return initial_avgs

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

        # REQUIRED by game_stats.html JS
        'point_flow': [],
    }


    for point in all_points:
        point_events = list(point.events)

        # Determine starting possession (single source of truth)
        start_pos = get_point_starting_possession(point)
        is_o_point = start_pos == 'offence'
        is_d_point = start_pos == 'defence'

        if is_o_point:
            stats['o_line_points'] += 1
        if is_d_point:
            stats['d_line_points'] += 1
        analysed = bool(point_events)
        if analysed:
            stats['analysed_points'] += 1
            stats['analysed_o_line_points'] += is_o_point
            stats['analysed_d_line_points'] += is_d_point

        # Canonical possession analysis
        analysis = analyze_point_possessions(point, point_events)
        our_turnovers = analysis['our_turnovers']
        our_possessions = analysis['our_possessions']
        possessions_gained = analysis['possessions_gained']

        stats['turnovers'] += our_turnovers
        stats['possessions'] += our_possessions
        stats['possessions_gained'] += possessions_gained

        scored = point_we_scored(point)

        stats['point_flow'].append({
            'point_number': getattr(point, 'point_number', len(stats['point_flow']) + 1),
            'our_score_after': getattr(point, 'our_score_after', None),
            'their_score_after': getattr(point, 'their_score_after', None),
            'scored': scored,
            'start_possession': start_pos,
            'turnovers': our_turnovers,
            'possessions': our_possessions,
        })


        if scored:
            stats['goals'] += 1
            stats['scoring_possessions'] += our_possessions

            if is_o_point:
                stats['o_line_conversions'] += 1
                if analysed and our_turnovers == 0:
                    stats['clean_holds'] += 1

            if is_d_point:
                stats['d_line_conversions'] += 1
                stats['breaks'] += 1   # <-- THIS IS THE MISSING PIECE
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
        stats['clean_holds'] / stats['analysed_o_line_points'] * 100
        if stats['analysed_o_line_points'] else 0
    )

    stats['clean_break_percentage'] = (
        stats['clean_breaks'] / stats['analysed_d_line_points'] * 100
        if stats['analysed_d_line_points'] else 0
    )

    stats['avg_turnovers_per_point'] = (
        stats['turnovers'] / stats['analysed_points']
        if stats['analysed_points'] else 0
    )

    stats['possessions_per_goal'] = (
        stats['scoring_possessions'] / stats['goals']
        if stats['goals'] else 0
    )

    stats['avg_possessions_gained_per_point'] = (
        stats['possessions_gained'] / stats['d_line_points']
        if stats['d_line_points'] else 0
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
        o_points = game_line_points(game, 'O-line')
        
        o_points_count = len(o_points)
        o_conversions = sum(1 for p in o_points if point_we_scored(p))
        o_line_efficiency.append((o_conversions / o_points_count * 100) if o_points_count > 0 else 0)
        
        # Calculate D-line efficiency - handle both query objects and lists
        d_points = game_line_points(game, 'D-line')
        
        d_points_count = len(d_points)
        d_conversions = sum(1 for p in d_points if point_we_scored(p))
        d_line_efficiency.append((d_conversions / d_points_count * 100) if d_points_count > 0 else 0)
        
        # Calculate break percentage - handle both query objects and lists
        all_points = game_points(game)
        
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

    # Load ALL events once
    point_ids = [p.id for p in points]
    # Determine team_organization_id safely (avoid relying on session/current_user)
    team_org_id = None
    for p in points:
        if getattr(p, "team_organization_id", None):
            team_org_id = p.team_organization_id
            break
    if team_org_id is None:
        # final fallback
        team_org_id = get_current_team_id()

    all_events = (
        Event.query
        .filter(Event.team_organization_id == team_org_id)
        .filter(Event.point_id.in_(point_ids))
        .order_by(Event.point_id, Event.timestamp)
        .all()
    )


    events_by_point = {}
    for e in all_events:
        events_by_point.setdefault(e.point_id, []).append(e)

    # Counters
    o_points = 0
    d_points = 0

    clean_holds = 0
    clean_breaks = 0
    scored_after_turnover = 0

    o_turnovers_total = 0
    d_possessions_gained = 0

    goals_scored = 0
    possessions_in_scoring_points = 0

    for point in points:
        if point.id not in events_by_point:
            continue  # Game Day only: no possessions recorded
        start_pos = get_point_starting_possession(point)
        is_o_point = start_pos == 'offence'
        is_d_point = start_pos == 'defence'

        if is_o_point:
            o_points += 1
        elif is_d_point:
            d_points += 1

        analysis = analyze_point_possessions(
            point,
            events_by_point.get(point.id, [])
        )

        our_turnovers = analysis['our_turnovers']
        our_possessions = analysis['our_possessions']
        possessions_gained = analysis['possessions_gained']

        if is_o_point:
            o_turnovers_total += our_turnovers

        if is_d_point:
            d_possessions_gained += possessions_gained

        if point_we_scored(point):
            goals_scored += 1
            possessions_in_scoring_points += our_possessions

            if our_turnovers > 0:
                scored_after_turnover += 1

            if is_o_point and our_turnovers == 0:
                clean_holds += 1

            if is_d_point and our_turnovers == 0:
                clean_breaks += 1

    return {
        'clean_hold_percentage': (clean_holds / o_points * 100) if o_points else 0,
        'clean_break_percentage': (clean_breaks / d_points * 100) if d_points else 0,
        'regain_offense_count': scored_after_turnover,
        'avg_o_turnovers_per_point': (o_turnovers_total / o_points) if o_points else 0,
        'avg_possessions_gained_per_point': (d_possessions_gained / d_points) if d_points else 0,
        'possessions_per_goal': (
            possessions_in_scoring_points / goals_scored if goals_scored else 0
        ),
    }

def calculate_team_summary(games):
    """Calculate team summary statistics"""
    summary = {
        'games_played': len(games),
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


    for game in games:
        o_points = game_line_points(game, 'O-line')
        d_points = game_line_points(game, 'D-line')
        
        summary['o_line_points'] += len(o_points)
        summary['o_line_conversions'] += sum(1 for p in o_points if point_we_scored(p))
        summary['d_line_points'] += len(d_points)
        summary['d_line_conversions'] += sum(1 for p in d_points if point_we_scored(p))
        summary['breaks'] += sum(1 for p in game_points(game) if p.is_break)
        summary['holds'] += sum(1 for p in game_points(game) if p.is_hold)

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
    """
    Possession-aware analysis for a single point.

    Returns:
      - our_turnovers: turnovers committed while we had possession
      - our_possessions: number of distinct possessions we had in the point
      - possessions_gained: number of times we gained the disc from them
        (useful for D-line turnover generation)

    This is resilient to different event schemas:
      - event_type vs event vs result
      - is_offensive vs offence
      - timestamp vs event_index
    """

    def get_event_type(e):
        return (
            getattr(e, 'event_type', None)
            or getattr(e, 'result', None)
            or getattr(e, 'event', None)
            or getattr(e, 'type', None)
        )

    def get_is_offensive(e):
        # True means we were on offence when the event happened
        v = getattr(e, 'is_offensive', None)
        if v is None:
            v = getattr(e, 'offence', None)
        if v is None:
            v = getattr(e, 'offense', None)
        return v

    def get_order_key(e):
        # Prefer timestamp; fallback to event_index; then 0
        ts = getattr(e, 'timestamp', None)
        if ts is None:
            ts = getattr(e, 'event_index', None)
        return ts if ts is not None else 0

    # Ensure chronological
    events = sorted(list(events or []), key=get_order_key)

    start_pos = get_point_starting_possession(point)
    we_have_disc = (start_pos == 'offence')

    our_turnovers = 0
    our_possessions = 1 if we_have_disc else 0

    # "possessions_gained" = how many times we gained the disc from them
    # If we start on D, first gain increments this (good).
    possessions_gained = 0

    def switch_possession(to_us: bool, gained_from_them: bool = False):
        nonlocal we_have_disc, our_possessions, possessions_gained
        if we_have_disc == to_us:
            return
        we_have_disc = to_us
        if to_us:
            our_possessions += 1
            if gained_from_them:
                possessions_gained += 1

    for e in events:
        et = (get_event_type(e) or '').strip().lower()
        is_off = get_is_offensive(e)

        # Turnovers always flip possession
        if et in TURNOVER_EVENTS:
            if is_off is True:
                # Our turnover
                our_turnovers += 1
                switch_possession(to_us=False)
            elif is_off is False:
                # Their turnover -> we gain
                switch_possession(to_us=True, gained_from_them=True)
            else:
                # Fallback: assume current state
                if we_have_disc:
                    our_turnovers += 1
                    switch_possession(to_us=False)
                else:
                    switch_possession(to_us=True, gained_from_them=True)

        # Blocks also flip possession
        elif et == 'block':
            if is_off is False:
                # We were defending -> our block -> we gain
                switch_possession(to_us=True, gained_from_them=True)
            elif is_off is True:
                # Opponent block while we were attacking
                switch_possession(to_us=False)
            else:
                # Fallback: flip
                # If we had it, they now have it; if they had it, we now have it and we "gained"
                if we_have_disc:
                    switch_possession(to_us=False)
                else:
                    switch_possession(to_us=True, gained_from_them=True)

        # Goals end the point; no need to flip possession

    return {
        'our_turnovers': our_turnovers,
        'our_possessions': our_possessions,
        'possessions_gained': possessions_gained
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

    # Count completions and break throws
    completions = sum(1 for t in throws if t.is_completion)
    break_throws = sum(1 for t in throws if t.break_throw)

    # Count goals and assists
    goals_query = Event.query.filter_by(
        event_type='goal',
        team_organization_id=get_current_team_id()
    ).filter(Event.point_id.in_(point_ids))

    goals = goals_query.count()
    assists = sum(1 for t in throws if t.throw_type == 'assist')

    # Count catch/drop events for catch_rate
    catches = Event.query.filter_by(
        event_type='catch',
        team_organization_id=get_current_team_id()
    ).filter(Event.point_id.in_(point_ids)).count()

    drops = Event.query.filter_by(
        event_type='drop',
        team_organization_id=get_current_team_id()
    ).filter(Event.point_id.in_(point_ids)).count()

    # Count blocks
    blocks_query = Event.query.filter_by(
        event_type='block',
        team_organization_id=get_current_team_id()
    )
    blocks_query = blocks_query.filter(Event.point_id.in_(point_ids))
    blocks = blocks_query.count()

    # Count turnovers forced
    turnovers_forced_query = Event.query.filter(
        Event.event_type.in_(['throwaway', 'drop', 'stall']),
        Event.is_offensive == False,
        Event.team_organization_id == get_current_team_id()
    )
    turnovers_forced_query = turnovers_forced_query.filter(Event.point_id.in_(point_ids))
    turnovers_forced = turnovers_forced_query.count() + blocks

    # Count hucks
    hucks = sum(1 for t in throws if t.calculate_distance() and t.calculate_distance() > HUCK_DISTANCE)

    # Calculate D-line totals once: conversion from every point, per-D-point
    # rates from points with full stats
    d_points_count = 0
    d_conversions = 0
    analysed_d_points = 0

    for game in games:
        d_points = game_line_points(game, 'D-line')
        d_points_count += len(d_points)
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
    throws_per_point = len(throws) / total_points if total_points > 0 else 0

    result = {
        'completion_rate': (completions / len(throws)) * 100 if throws else 0,
        'catch_rate': (catches / (catches + drops)) * 100 if (catches + drops) > 0 else 0,
        'goals_per_point': goals / total_points,
        'assists_per_point': assists / total_points,
        'throws_per_point': throws_per_point,
        'hucks_per_point': hucks / total_points,
        # blocks_per_point: blocks earned on D-line per D-line point played
        'blocks_per_point': blocks / analysed_d_points if analysed_d_points > 0 else 0,
        'turnovers_forced_per_point': turnovers_forced / analysed_d_points if analysed_d_points > 0 else 0,
        'break_throw_percentage': break_throw_percentage,
        'break_percentage': break_percentage,       # D-line conversion rate alias
    }

    return result

def get_previous_period_games(season, tournament_id):
    """Get games from previous period for comparison"""
    if tournament_id:
        # Get current tournament
        current_tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if current_tournament:
            # Find previous tournament in same season
            prev_tournament = Tournament.query.filter(
                Tournament.season == current_tournament.season,
                Tournament.start_date < current_tournament.start_date,
                Tournament.team_organization_id == get_current_team_id()
            ).order_by(Tournament.start_date.desc()).first()
            
            if prev_tournament:
                return Game.query.filter_by(
                    tournament_id=prev_tournament.id,
                    team_organization_id=get_current_team_id()
                ).all()
    elif season:
        # Get previous season
        seasons = db.session.query(Tournament.season).filter_by(
            team_organization_id=get_current_team_id()
        ).distinct().order_by(Tournament.season).all()
        
        seasons = [s[0] for s in seasons if s[0]]
        
        if season in seasons:
            idx = seasons.index(season)
            if idx > 0:
                prev_season = seasons[idx - 1]
                tournament_ids = [t.id for t in Tournament.query.filter_by(
                    season=prev_season,
                    team_organization_id=get_current_team_id()
                ).all()]
                
                return Game.query.filter(
                    Game.tournament_id.in_(tournament_ids),
                    Game.team_organization_id == get_current_team_id()
                ).all()
    
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
