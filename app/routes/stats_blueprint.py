from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app_factory import db
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, not_
from app.utils.stats_service import StatsService
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.throws import Throw
from app.models.stats import PlayerPointStats
from app.models.team_organization import TeamOrganization

# Create a Blueprint for stats routes
stats_dashboard = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

@stats_dashboard.route('/')
def index():
    """
    Main stats dashboard page
    """
    # Get team organization ID from session or request
    team_organization_id = request.args.get('team_id', type=int)
    
    # Get date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get team stats from cache
    team_stats = StatsService.get_team_stats(team_organization_id, start_date, end_date)
    
    # Get recent games
    games_query = Game.query
    if team_organization_id:
        games_query = games_query.filter_by(team_organization_id=team_organization_id)
    if start_date:
        games_query = games_query.filter(Game.date >= start_date)
    if end_date:
        games_query = games_query.filter(Game.date <= end_date)
    
    recent_games = games_query.order_by(Game.date.desc()).limit(5).all()
    
    # Get top players by PER
    top_players = []
    players_query = Player.query.filter_by(active=True)
    if team_organization_id:
        players_query = players_query.filter_by(team_organization_id=team_organization_id)
    
    players = players_query.all()
    
    for player in players:
        # Get player stats from cache
        player_stats = StatsService.get_player_stats(
            player.id, 
            team_organization_id, 
            start_date, 
            end_date
        )
        
        if player_stats.get('points_played', 0) > 0:
            top_players.append({
                'player': player,
                'per': player_stats.get('per', 0),
                'points_played': player_stats.get('points_played', 0)
            })
    
    # Sort by PER and limit to top 10
    top_players.sort(key=lambda x: x['per'], reverse=True)
    top_players = top_players[:10]
    
    # Get performance trends
    performance_trends = get_performance_trends(team_organization_id)
    
    stats = {
        'active_players_count': Player.query.filter_by(active=True).count(),
        # Add other stats as needed
    }
    
    return render_template(
        '/stats/index.html',
        team_stats=team_stats,
        recent_games=recent_games,
        top_players=top_players,
        performance_trends=performance_trends,
        stats=stats 
    )

@stats_dashboard.route('/player/<int:player_id>')
def player_stats(player_id):
    """
    Player statistics page
    """
    # Get player
    player = Player.query.get_or_404(player_id)
    
    # Get team organization ID from session or request
    team_organization_id = request.args.get('team_id', type=int) or player.team_organization_id
    
    # Get date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get player stats from cache
    stats = StatsService.get_player_stats(
        player_id, 
        team_organization_id, 
        start_date, 
        end_date
    )
    
    # Get team stats for comparison
    team_summary = StatsService.get_team_stats(team_organization_id, start_date, end_date)
    
    # Get recent games the player participated in
    recent_games = []
    
    # Fixed JOIN syntax
    games_query = db.session.query(Game).join(
        Point, Point.game_id == Game.id
    ).join(
        LineUp, LineUp.point_id == Point.id
    ).filter(
        LineUp.player_id == player_id
    ).distinct()
    
    if team_organization_id:
        games_query = games_query.filter(Game.team_organization_id == team_organization_id)
    if start_date:
        games_query = games_query.filter(Game.date >= start_date)
    if end_date:
        games_query = games_query.filter(Game.date <= end_date)
    
    recent_games = games_query.order_by(Game.date.desc()).limit(5).all()
    
    # Get player performance trends
    performance_trends = get_player_performance_trends(player_id, team_organization_id)
    
    return render_template(
        'player_stats.html',
        player=player,
        stats=stats,
        team_summary=team_summary,
        recent_games=recent_games,
        performance_trends=performance_trends
    )

@stats_dashboard.route('/team')
def team_stats():
    """
    Team statistics page
    """
    # Get team organization ID from session or request
    team_organization_id = request.args.get('team_id', type=int)
    
    # Get date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get team stats from cache
    team_summary = StatsService.get_team_stats(team_organization_id, start_date, end_date)
    
    # Get previous period stats for comparison
    prev_start_date = None
    prev_end_date = None
    
    if start_date and end_date:
        # Calculate previous period of same length
        period_length = (end_date - start_date).days
        prev_end_date = start_date - timedelta(days=1)
        prev_start_date = prev_end_date - timedelta(days=period_length)
        
        prev_team_summary = StatsService.get_team_stats(
            team_organization_id, 
            prev_start_date, 
            prev_end_date
        )
        
        # Add previous period stats to team_summary
        team_summary['prev_o_line_conversion_rate'] = prev_team_summary.get('o_line_conversion_rate', 0)
        team_summary['prev_d_line_conversion_rate'] = prev_team_summary.get('d_line_conversion_rate', 0)
        team_summary['prev_o_line_efficiency'] = prev_team_summary.get('o_line_efficiency', 0)
        team_summary['prev_d_line_efficiency'] = prev_team_summary.get('d_line_efficiency', 0)
        team_summary['prev_defensive_efficiency'] = prev_team_summary.get('defensive_efficiency', 0)
        team_summary['prev_break_percentage'] = prev_team_summary.get('break_percentage', 0)
        team_summary['prev_blocks_per_point'] = prev_team_summary.get('blocks_per_point', 0)
        team_summary['prev_turnovers_forced_per_point'] = prev_team_summary.get('turnovers_forced_per_point', 0)
    
    # Get active players
    players_query = Player.query.filter_by(active=True)
    if team_organization_id:
        players_query = players_query.filter_by(team_organization_id=team_organization_id)
    
    players = players_query.all()
    
    # Calculate player stats and efficiencies
    player_stats = {}
    o_line_efficiency = {}
    d_line_efficiency = {}
    
    for player in players:
        # Get player stats from cache
        stats = StatsService.get_player_stats(
            player.id, 
            team_organization_id, 
            start_date, 
            end_date
        )
        
        player_stats[player.id] = stats
        
        # Store efficiencies for sorting
        o_line_efficiency[player] = stats.get('o_line_efficiency', 0)
        d_line_efficiency[player] = stats.get('d_line_efficiency', 0)
    
    # Sort players by efficiency
    o_line_players = sorted(
        [p for p in players if player_stats[p.id].get('o_line_points_played', 0) >= 5],
        key=lambda p: o_line_efficiency[p],
        reverse=True
    )
    
    d_line_players = sorted(
        [p for p in players if player_stats[p.id].get('d_line_points_played', 0) >= 5],
        key=lambda p: d_line_efficiency[p],
        reverse=True
    )
    
    # Split by gender if available
    o_line_women = [p for p in o_line_players if p.gender == 'female'][:5]
    o_line_men = [p for p in o_line_players if p.gender == 'male'][:5]
    
    d_line_women = [p for p in d_line_players if p.gender == 'female'][:5]
    d_line_men = [p for p in d_line_players if p.gender == 'male'][:5]
    
    # Get performance trends
    performance_trends = get_performance_trends(team_organization_id)
    
    return render_template(
        'team_stats.html',
        team_summary=team_summary,
        player_stats=player_stats,
        o_line_players=o_line_players[:10],
        d_line_players=d_line_players[:10],
        o_line_women=o_line_women,
        o_line_men=o_line_men,
        d_line_women=d_line_women,
        d_line_men=d_line_men,
        o_line_efficiency=o_line_efficiency,
        d_line_efficiency=d_line_efficiency,
        performance_trends=performance_trends
    )

@stats_dashboard.route('/game/<int:game_id>')
def game_stats(game_id):
    """
    Game statistics page
    """
    # Get game
    game = Game.query.get_or_404(game_id)
    
    # Get game stats from cache
    game_stats = StatsService.get_game_stats(game_id)
    
    # Get points
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    
    # Get player stats for this game
    player_stats = {}
    player_efficiencies = {}
    
    # Get all players who participated in this game
    players_query = db.session.query(Player).join(LineUp, Point).filter(
        Point.game_id == game_id
    ).distinct()
    
    players = players_query.all()
    
    for player in players:
        # Calculate player stats for this game only
        stats = calculate_player_game_stats(player.id, game_id)
        player_stats[player.id] = stats
        
        # Store efficiency for sorting
        player_efficiencies[player] = stats.get('per', 0)
    
    # Sort players by PER
    top_players = sorted(
        players,
        key=lambda p: player_efficiencies[p],
        reverse=True
    )[:10]
    
    # Get point timeline data
    point_timeline = []
    
    for point in points:
        point_data = {
            'point_number': point.point_number,
            'our_line_type': point.our_line_type,
            'our_score_before': point.our_score_before,
            'their_score_before': point.their_score_before,
            'our_score_after': point.our_score_after,
            'their_score_after': point.their_score_after,
            'point_outcome': point.point_outcome,
            'duration': point.duration
        }
        
        point_timeline.append(point_data)
    
    return render_template(
        'game_stats.html',
        game=game,
        game_stats=game_stats,
        points=points,
        player_stats=player_stats,
        top_players=top_players,
        point_timeline=point_timeline
    )

@stats_dashboard.route('/refresh_cache')
def refresh_cache():
    """
    Refresh the stats cache
    """
    # Get parameters
    player_id = request.args.get('player_id', type=int)
    team_organization_id = request.args.get('team_id', type=int)
    game_id = request.args.get('game_id', type=int)
    
    # Invalidate cache
    count = StatsService.invalidate_cache(player_id, team_organization_id, game_id)
    
    # Redirect back to the appropriate page
    if player_id:
        return redirect(url_for('stats_dashboard.player_stats', player_id=player_id))
    elif game_id:
        return redirect(url_for('stats_dashboard.game_stats', game_id=game_id))
    elif team_organization_id:
        return redirect(url_for('stats_dashboard.team_stats', team_id=team_organization_id))
    else:
        return redirect(url_for('stats_dashboard.index'))

# Helper functions

def calculate_player_game_stats(player_id, game_id):
    """
    Calculate player statistics for a specific game
    
    Args:
        player_id: ID of the player
        game_id: ID of the game
        
    Returns:
        dict: Player statistics for the game
    """
    # Get points played by the player in this game
    points_query = db.session.query(Point).join(LineUp).filter(
        LineUp.player_id == player_id,
        Point.game_id == game_id
    )
    
    points = points_query.all()
    
    # Calculate basic stats
    points_played = len(points)
    o_line_points_played = sum(1 for p in points if p.our_line_type == 'O-line')
    d_line_points_played = sum(1 for p in points if p.our_line_type == 'D-line')
    
    # Calculate efficiency stats
    o_line_points = [p for p in points if p.our_line_type == 'O-line']
    d_line_points = [p for p in points if p.our_line_type == 'D-line']
    
    if o_line_points:
        o_scored = sum(1 for p in o_line_points if p.point_outcome == 'scored')
        o_line_efficiency = o_scored / len(o_line_points)
    else:
        o_line_efficiency = 0.0
        
    if d_line_points:
        d_not_conceded = sum(1 for p in d_line_points if p.point_outcome != 'conceded')
        d_line_efficiency = d_not_conceded / len(d_line_points)
    else:
        d_line_efficiency = 0.0
    
    # Get throw stats
    player = Player.query.get(player_id)
    throws_query = player.throws_made.join(Throw.point).filter(Point.game_id == game_id)
    
    completions = throws_query.filter_by(outcome='complete').count()
    throw_attempts = throws_query.count()
    completion_percentage = (completions / throw_attempts * 100) if throw_attempts > 0 else 0
    
    # Get scoring stats
    events_query = player.player_events.join(Event.point).filter(Point.game_id == game_id)
    
    goals = events_query.filter_by(event_type='goal').count()
    assists = events_query.filter_by(event_type='assist').count()
    blocks = events_query.filter_by(event_type='block').count()
    
    # Get plus/minus from PlayerPointStats
    plus_minus_query = db.session.query(
        func.sum(PlayerPointStats.o_line_plus_minus).label('o_plus_minus'),
        func.sum(PlayerPointStats.d_line_plus_minus).label('d_plus_minus')
    ).filter(
        PlayerPointStats.player_id == player_id,
        PlayerPointStats.point_id.in_([p.id for p in points])
    )
    
    result = plus_minus_query.first()
    o_line_plus_minus = result.o_plus_minus or 0.0
    d_line_plus_minus = result.d_plus_minus or 0.0
    
    # Calculate a simple PER for this game
    per = (
        (goals * 1.5) + 
        (assists * 1.2) + 
        (blocks * 1.4) - 
        ((throw_attempts - completions) * 1.0) +
        (o_line_plus_minus * 0.8) + 
        (d_line_plus_minus * 0.8)
    )
    
    # Normalize PER to a 0-100 scale
    normalized_per = min(max(per * 5 + 50, 0), 100)
    
    return {
        'points_played': points_played,
        'o_line_points_played': o_line_points_played,
        'd_line_points_played': d_line_points_played,
        'o_line_efficiency': o_line_efficiency,
        'd_line_efficiency': d_line_efficiency,
        'completions': completions,
        'throw_attempts': throw_attempts,
        'completion_percentage': completion_percentage,
        'goals': goals,
        'assists': assists,
        'blocks': blocks,
        'o_line_plus_minus': o_line_plus_minus,
        'd_line_plus_minus': d_line_plus_minus,
        'per': normalized_per
    }

def get_performance_trends(team_organization_id, num_periods=5):
    """
    Get team performance trends over time
    
    Args:
        team_organization_id: ID of the team organization
        num_periods: Number of time periods to include
        
    Returns:
        dict: Performance trends data
    """
    # Get games for this team
    games_query = Game.query.filter_by(team_organization_id=team_organization_id)
    games = games_query.order_by(Game.date).all()
    
    if not games:
        return None
    
    # Group games by month
    game_months = {}
    for game in games:
        if not game.date:
            continue
            
        month_key = game.date.strftime('%Y-%m')
        if month_key not in game_months:
            game_months[month_key] = []
        
        game_months[month_key].append(game)
    
    # Sort months and take the most recent ones
    sorted_months = sorted(game_months.keys())
    recent_months = sorted_months[-num_periods:] if len(sorted_months) > num_periods else sorted_months
    
    # Calculate stats for each month
    dates = []
    labels = []
    o_line_efficiency = []
    d_line_efficiency = []
    break_percentage = []
    
    for month in recent_months:
        month_games = game_months[month]
        
        # Get all points from these games
        point_ids = []
        for game in month_games:
            point_ids.extend([p.id for p in game.points.all()])
        
        points = Point.query.filter(Point.id.in_(point_ids)).all()
        
        # Calculate stats
        o_points = [p for p in points if p.our_line_type == 'O-line']
        d_points = [p for p in points if p.our_line_type == 'D-line']
        
        if o_points:
            o_scored = sum(1 for p in o_points if p.point_outcome == 'scored')
            o_eff = (o_scored / len(o_points)) * 100
        else:
            o_eff = 0
            
        if d_points:
            d_not_conceded = sum(1 for p in d_points if p.point_outcome != 'conceded')
            d_eff = (d_not_conceded / len(d_points)) * 100
        else:
            d_eff = 0
            
        if points:
            breaks = sum(1 for p in points if p.is_break)
            break_pct = (breaks / len(points)) * 100
        else:
            break_pct = 0
        
        # Format date for display
        display_date = datetime.strptime(month, '%Y-%m').strftime('%b %Y')
        
        # Add to trends
        dates.append(month)
        labels.append(display_date)
        o_line_efficiency.append(o_eff)
        d_line_efficiency.append(d_eff)
        break_percentage.append(break_pct)
    
    return {
        'dates': dates,
        'labels': labels,
        'o_line_efficiency': o_line_efficiency,
        'd_line_efficiency': d_line_efficiency,
        'break_percentage': break_percentage
    }

def get_player_performance_trends(player_id, team_organization_id=None, num_periods=5):
    """
    Get player performance trends over time
    
    Args:
        player_id: ID of the player
        team_organization_id: Optional ID of the team organization
        num_periods: Number of time periods to include
        
    Returns:
        dict: Performance trends data
    """
    # Get games this player participated in
    games_query = db.session.query(Game).join(
        Point, Point.game_id == Game.id
    ).join(
        LineUp, LineUp.point_id == Point.id
    ).filter(
        LineUp.player_id == player_id
    ).distinct()

    
    if team_organization_id:
        games_query = games_query.filter(Game.team_organization_id == team_organization_id)
    
    games = games_query.order_by(Game.date).all()
    
    if not games:
        return None
    
    # Group games by month
    game_months = {}
    for game in games:
        if not game.date:
            continue
            
        month_key = game.date.strftime('%Y-%m')
        if month_key not in game_months:
            game_months[month_key] = []
        
        game_months[month_key].append(game)
    
    # Sort months and take the most recent ones
    sorted_months = sorted(game_months.keys())
    recent_months = sorted_months[-num_periods:] if len(sorted_months) > num_periods else sorted_months
    
    # Calculate stats for each month
    dates = []
    labels = []
    per_values = []
    o_line_efficiency = []
    d_line_efficiency = []
    
    for month in recent_months:
        month_games = game_months[month]
        
        # Get start and end dates for this month
        start_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        if month == datetime.now().strftime('%Y-%m'):
            end_date = datetime.now().date()
        else:
            next_month = datetime.strptime(month + '-01', '%Y-%m-%d') + timedelta(days=32)
            end_date = (next_month.replace(day=1) - timedelta(days=1)).date()
        
        # Get player stats for this month
        stats = StatsService.get_player_stats(
            player_id, 
            team_organization_id, 
            start_date, 
            end_date
        )
        
        # Format date for display
        display_date = datetime.strptime(month, '%Y-%m').strftime('%b %Y')
        
        # Add to trends
        dates.append(month)
        labels.append(display_date)
        per_values.append(stats.get('per', 0))
        o_line_efficiency.append(stats.get('o_line_efficiency', 0) * 100)
        d_line_efficiency.append(stats.get('d_line_efficiency', 0) * 100)
    
    return {
        'dates': dates,
        'labels': labels,
        'per': per_values,
        'o_line_efficiency': o_line_efficiency,
        'd_line_efficiency': d_line_efficiency
    }