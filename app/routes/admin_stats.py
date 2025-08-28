# app/routes/admin_stats.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import admin_required  # Import from app.utils package
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.stats import PlayerStats, TeamStats
from app.utils.stats_calculator import (
    get_players_base_stats, 
    calculate_team_summary,
    calculate_additional_team_metrics,
    calculate_team_averages,
    calculate_per_from_stats
)
from app.utils.stats_retrieval import get_current_team_id  # Import from stats_retrieval
from sqlalchemy import func
from app import db
import time
from app.forms.stats_form import StatsCalculatorForm

# Create a blueprint for admin stats routes
admin_stats_bp = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

@admin_stats_bp.route('/calculator', methods=['GET', 'POST'])
@login_required
@admin_required
def calculator():
    form = StatsCalculatorForm()
    
    # Populate form choices
    team_org_id = get_current_team_id()
    tournaments = Tournament.query.filter_by(team_organization_id=team_org_id).order_by(Tournament.start_date.desc()).all()
    form.tournament_id.choices = [(str(t.id), f"{t.name} ({t.start_date.strftime('%Y-%m-%d')})") for t in tournaments]
    
    seasons = [s[0] for s in db.session.query(Tournament.season).filter_by(
        team_organization_id=team_org_id).distinct().all() if s[0]]
    form.season.choices = [(s, s) for s in seasons]
    
    recent_games = Game.query.filter_by(team_organization_id=team_org_id).order_by(Game.date.desc()).limit(20).all()
    form.game_id.choices = [(str(g.id), f"{g.date.strftime('%Y-%m-%d')} vs {g.opponent}") for g in recent_games]
    
    # Get stats on how many records are already in the database
    player_stats_count = db.session.query(func.count(PlayerStats.id)).scalar()
    team_stats_count = db.session.query(func.count(TeamStats.id)).scalar()
    
    if form.validate_on_submit():
        # Process form submission
        scope = form.scope.data
        tournament_id = form.tournament_id.data if form.tournament_id.data else None
        game_id = form.game_id.data if form.game_id.data else None
        season = form.season.data if form.season.data else None
        
        # Start timing the operation
        start_time = time.time()
        
        # Determine which games to process based on the scope
        games = []
        if scope == 'game' and game_id:
            game = Game.query.get(int(game_id))
            if game:
                games = [game]
                flash_prefix = f"Game '{game.opponent}'"
        elif scope == 'tournament' and tournament_id:
            tournament = Tournament.query.get(int(tournament_id))
            if tournament:
                games = tournament.games.all()
                flash_prefix = f"Tournament '{tournament.name}'"
        elif scope == 'season' and season:
            tourney_ids = [t.id for t in Tournament.query.filter_by(season=season).all()]
            games = Game.query.filter(Game.tournament_id.in_(tourney_ids)).all()
            flash_prefix = f"Season '{season}'"
        elif scope == 'all':
            games = Game.query.filter_by(team_organization_id=team_org_id).all()
            flash_prefix = "All games"
        
        if games:
            # Get all active players
            players = Player.query.filter_by(active=True, team_organization_id=team_org_id).all()
            
            # Calculate team stats
            team_stats = calculate_team_summary(games)
            team_stats.update(calculate_additional_team_metrics(games))
            team_avgs = calculate_team_averages(games)
            
            # Calculate player stats
            player_stats_dict = get_players_base_stats(players, games)
            
            # Store team stats in the database
            store_team_stats(team_stats, game_id, tournament_id, season)
            
            # Store player stats in the database
            store_player_stats(player_stats_dict, team_avgs, players, game_id, tournament_id, season)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            flash(f"{flash_prefix} statistics calculated and stored successfully in {execution_time:.2f} seconds!", "success")
            return redirect(url_for('admin_stats.calculator'))
        else:
            flash("No games found for the selected criteria", "warning")
    
    return render_template(
        'admin/stats_calculator.html',
        form=form,  # Pass the form to the template
        tournaments=tournaments,
        seasons=seasons,
        recent_games=recent_games,
        player_stats_count=player_stats_count,
        team_stats_count=team_stats_count
    )

def store_team_stats(team_stats, game_id=None, tournament_id=None, season=None):
    """Store or update team statistics in the TeamStats table."""
    team_org_id = get_current_team_id()
    
    try:
        # Find if a record already exists for this scope
        existing = TeamStats.query.filter_by(
            team_organization_id=team_org_id,
            game_id=game_id,
            tournament_id=tournament_id,
            season=season
        ).first()

        if not existing:
            # If it doesn't exist, create a new one
            existing = TeamStats(
                team_organization_id=team_org_id,
                game_id=game_id,
                tournament_id=tournament_id,
                season=season
            )
            db.session.add(existing)

        # Explicitly map each stat from the dictionary to the model attribute
        # Use .get() with a default value to prevent errors if a key is missing
        existing.games_played = team_stats.get('games_played', 0)
        existing.wins = team_stats.get('wins', 0)
        existing.losses = team_stats.get('losses', 0)
        existing.ties = team_stats.get('ties', 0)
        existing.total_points = team_stats.get('total_points', 0)
        existing.o_line_points = team_stats.get('o_line_points', 0)
        existing.o_line_conversions = team_stats.get('o_line_conversions', 0)
        existing.d_line_points = team_stats.get('d_line_points', 0)
        existing.d_line_conversions = team_stats.get('d_line_conversions', 0)
        existing.win_percentage = team_stats.get('win_percentage', 0.0)
        existing.o_line_conversion_rate = team_stats.get('o_line_conversion_rate', 0.0)
        existing.d_line_conversion_rate = team_stats.get('d_line_conversion_rate', 0.0)
        existing.is_dirty = False # Mark as clean after calculation

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"A database error occurred while saving team stats: {e}", "danger")
        print(f"Error in store_team_stats: {e}")




def store_player_stats(player_stats_dict, team_avgs, players, game_id=None, tournament_id=None, season=None):
    """Store or update player statistics in the PlayerStats table."""
    team_org_id = get_current_team_id()

    try:
        for player in players:
            if player.id in player_stats_dict:
                stats = player_stats_dict[player.id]
                
                # Skip players who didn't play
                if stats.get('points_played', 0) == 0:
                    continue

                # Calculate PER before saving
                stats['per'] = calculate_per_from_stats(stats, team_avgs)
                
                # Find if a record already exists for this scope
                existing = PlayerStats.query.filter_by(
                    player_id=player.id,
                    game_id=game_id,
                    tournament_id=tournament_id,
                    season=season
                ).first()

                if not existing:
                    # If it doesn't exist, create a new one
                    existing = PlayerStats(
                        player_id=player.id,
                        team_organization_id=team_org_id,
                        game_id=game_id,
                        tournament_id=tournament_id,
                        season=season
                    )
                    db.session.add(existing)

                # Explicitly map each stat from the dictionary to the model attribute
                existing.games_played = stats.get('games_played', 0)
                existing.points_played = stats.get('points_played', 0)
                existing.o_line_points_played = stats.get('o_line_points_played', 0)
                existing.d_line_points_played = stats.get('d_line_points_played', 0)
                existing.goals = stats.get('goals', 0)
                existing.assists = stats.get('assists', 0)
                existing.hockey_assists = stats.get('hockey_assists', 0)
                existing.blocks = stats.get('blocks', 0)
                existing.throws = stats.get('throws', 0)
                existing.completions = stats.get('completions', 0)
                existing.throwaways = stats.get('throwaways', 0)
                existing.drops = stats.get('drops', 0)
                existing.stalls = stats.get('stalls', 0)
                existing.completion_rate = stats.get('completion_rate', 0.0)
                existing.catch_rate = stats.get('catch_rate', 0.0)
                existing.plus_minus = stats.get('plus_minus', 0.0)
                existing.per = stats.get('per', 0.0)
                existing.is_dirty = False # Mark as clean

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"A database error occurred while saving player stats: {e}", "danger")
        print(f"Error in store_player_stats: {e}")



