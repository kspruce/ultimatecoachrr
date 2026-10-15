from flask import render_template, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.models.game import Game
import json
from app.utils.team_filter import get_current_team_id

from app.routes.stats import bp, is_admin, is_coach
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_optimized_line_efficiency, calculate_per_from_stats, calculate_team_avg_stats
from app.stats.players import get_players_base_stats
from app.stats.team import calculate_additional_team_metrics, calculate_game_stats, calculate_possession_based_team_metrics, calculate_team_summary, generate_player_connections, process_heatmap_data


@bp.route('/')
@login_required
def index():
    # Default values for all required variables
    default_context = {
        'team_summary': {
            'wins': 0,
            'losses': 0,
            'ties': 0,
            'total_points': 0,
            'o_line_points': 0,
            'o_line_conversions': 0,
            'd_line_points': 0,
            'd_line_conversions': 0,
            'breaks': 0,
            'win_percentage': 0,
            'o_line_conversion_rate': 0,
            'd_line_conversion_rate': 0
        },
        'players': [],
        'recent_games': [],
        'team_stats': [],
        'player_stats': {},
        'o_line_players': [],
        'd_line_players': [],
        'heatmap_data': [],
        'connection_data': {'nodes': [], 'links': []},
        'team_avg_stats': {}
    }

    try:
        # Get active players scoped to the current team organisation
        players_query = Player.query.filter_by(
            active=True,
            team_organization_id=get_current_team_id()
        )
        players = players_query.all()

        if not players:
            flash("No active players found", "warning")
            return render_template('stats/index.html', **default_context)


        # Get recent games with eager loading for tournament only
        recent_games = Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).options(
            db.joinedload(Game.tournament)
        ).order_by(Game.date.desc()).all()
        
        # For each game, explicitly load points to handle dynamic relationship
        for game in recent_games:
            # Force loading of points
            if hasattr(game.points, 'all'):
                _ = game.points.all()


        
        if not recent_games:
            return render_template('stats/index.html', **default_context)

        # Start timing the expensive operations
        import time
        start_time = time.time()
        
        # Calculate team summary stats - SAME AS TEAM_STATS ROUTE
        team_summary = calculate_team_summary(recent_games)
        team_summary.update(calculate_additional_team_metrics(recent_games))
        team_summary.update(calculate_possession_based_team_metrics(recent_games))
        
        # Calculate previous period stats for comparison - SAME AS TEAM_STATS ROUTE
        # For index, we don't have filters, so we'll get previous games based on dates
        prev_games = recent_games[1:] if len(recent_games) > 1 else []
        prev_summary = calculate_team_summary(prev_games)
        prev_metrics = calculate_additional_team_metrics(prev_games)
        
        
        # Add previous metrics with 'prev_' prefix - SAME AS TEAM_STATS ROUTE
        for key, value in prev_metrics.items():
            team_summary[f'prev_{key}'] = value
        for key, value in prev_summary.items():
            if key not in team_summary:
                team_summary[f'prev_{key}'] = value
        
        # Calculate game stats
        team_stats = []
        for game in recent_games[:5]:  # Limit to most recent 5 games for performance
            try:
                stats = calculate_game_stats(game)
                team_stats.append({'stats': stats})
            except Exception as e:
                current_app.logger.error(f"Error calculating stats for game {game.id}: {str(e)}")
                continue
                
        # Calculate team averages once for all players
        current_app.logger.debug("Calculating team averages...")
        team_avgs = get_cached_team_averages(recent_games)
        
        # Calculate player stats in batch
        current_app.logger.debug("Calculating player stats in batch...")
        player_stats = get_players_base_stats(players, recent_games)
        
        # Calculate PER for each player using the preloaded stats
        current_app.logger.debug("Calculating PER for each player...")
        for player_id, stats in player_stats.items():
            if stats['points_played'] > 0:
                stats['per'] = calculate_per_from_stats(stats, team_avgs)

        
        current_app.logger.debug(f"Stats calculation took {time.time() - start_time:.2f} seconds")
        
        # Determine O-line and D-line players based on point participation
        # This part is already optimized by using the preloaded player stats
        o_line_candidates = []
        d_line_candidates = []

        for player in players:
            if player.id in player_stats:
                stats = player_stats[player.id]
                o_line_points = stats.get('o_line_points_played', 0)
                d_line_points = stats.get('d_line_points_played', 0)
                
                if o_line_points > 0:
                    o_line_candidates.append(player)
                if d_line_points > 0:
                    d_line_candidates.append(player)

        # Calculate line efficiency with gender separation
        # This function should be optimized to use the preloaded player stats
        o_line_efficiency = calculate_optimized_line_efficiency(o_line_candidates, player_stats, is_offensive=True)
        d_line_efficiency = calculate_optimized_line_efficiency(d_line_candidates, player_stats, is_offensive=False)
        
        # Separate players by gender with fallback
        o_line_women = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
        o_line_men = [player for player, _ in o_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
        d_line_women = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'female'][:4]
        d_line_men = [player for player, _ in d_line_efficiency if getattr(player, 'gender', '') == 'male'][:4]
        
        # If we don't have enough players with gender data, fall back to the original method
        if not o_line_women and not o_line_men:
            o_line_players = [player for player, _ in o_line_efficiency][:7]
        else:
            o_line_players = o_line_women + o_line_men
        
        if not d_line_women and not d_line_men:
            d_line_players = [player for player, _ in d_line_efficiency][:7]
        else:
            d_line_players = d_line_women + d_line_men
        
        # Calculate team average stats
        team_avg_stats = calculate_team_avg_stats(player_stats)
        
        # Generate heatmap and connection data
        # Consider limiting the amount of data processed here
        heatmap_data = process_heatmap_data(limit=1000)
        connection_data = generate_player_connections(min_connections=2)

        return render_template(
            'stats/index.html',
            team_summary=team_summary,
            players=players,
            recent_games=recent_games,
            team_stats=team_stats,
            player_stats=player_stats,
            o_line_players=o_line_players,
            d_line_players=d_line_players,
            o_line_women=o_line_women,
            o_line_men=o_line_men,
            d_line_women=d_line_women,
            d_line_men=d_line_men,
            o_line_efficiency=dict(o_line_efficiency),
            d_line_efficiency=dict(d_line_efficiency),
            heatmap_data=json.dumps(heatmap_data),
            connection_data=json.dumps(connection_data),
            team_avg_stats=team_avg_stats,
            is_admin=is_admin(current_user),
            is_coach=is_coach(current_user)
        )

    except Exception as e:
        current_app.logger.error(f"Error in index route: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"An error occurred: {str(e)}", "danger")
        return render_template('stats/index.html', **default_context)
