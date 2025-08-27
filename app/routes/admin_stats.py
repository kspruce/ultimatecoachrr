# app/routes/admin_stats.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import admin_required  # Import directly from app.utils
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
from sqlalchemy import func
from app import db
import time

# Create a blueprint for admin stats routes
admin_stats_bp = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

def get_current_team_id():
    """Get the current team organization ID from the logged-in user"""
    if current_user and hasattr(current_user, 'team_organization_id'):
        return current_user.team_organization_id
    return None

@admin_stats_bp.route('/calculator', methods=['GET', 'POST'])
@login_required
@admin_required  # Use the existing decorator from app.utils
def calculator():
    """Admin interface for calculating and storing statistics in the database."""
    team_org_id = get_current_team_id()
    if not team_org_id:
        flash("No team organization found", "danger")
        return redirect(url_for('main.index'))
    
    # Get all tournaments for this team
    tournaments = Tournament.query.filter_by(team_organization_id=team_org_id).order_by(Tournament.start_date.desc()).all()
    
    # Get all seasons (distinct)
    seasons = [s[0] for s in db.session.query(Tournament.season).filter_by(
        team_organization_id=team_org_id).distinct().all() if s[0]]
    
    # Get stats on how many records are already in the database
    player_stats_count = db.session.query(func.count(PlayerStats.id)).scalar()
    team_stats_count = db.session.query(func.count(TeamStats.id)).scalar()
    
    # Process form submission
    if request.method == 'POST':
        scope = request.form.get('scope')
        tournament_id = request.form.get('tournament_id')
        game_id = request.form.get('game_id')
        season = request.form.get('season')
        
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
    
    # For the game dropdown, get recent games
    recent_games = Game.query.filter_by(team_organization_id=team_org_id).order_by(Game.date.desc()).limit(20).all()
    
    return render_template(
        'admin/stats_calculator.html',
        tournaments=tournaments,
        seasons=seasons,
        recent_games=recent_games,
        player_stats_count=player_stats_count,
        team_stats_count=team_stats_count
    )

def store_team_stats(team_stats, game_id=None, tournament_id=None, season=None):
    """Store team statistics in the TeamStats table."""
    team_org_id = get_current_team_id()
    
    # Check if a record already exists
    existing = TeamStats.query.filter_by(
        team_organization_id=team_org_id,
        game_id=game_id,
        tournament_id=tournament_id,
        season=season
    ).first()
    
    if existing:
        # Update existing record
        for key, value in team_stats.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
    else:
        # Create new record
        team_stats_obj = TeamStats(
            team_organization_id=team_org_id,
        
