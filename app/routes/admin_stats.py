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

# Create a blueprint for admin stats routes
admin_stats_bp = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

from app.forms.stats_form import StatsCalculatorForm

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
            game_id=game_id,
            tournament_id=tournament_id,
            season=season,
            **team_stats
        )
        db.session.add(team_stats_obj)
    
    db.session.commit()

def store_player_stats(player_stats_dict, team_avgs, players, game_id=None, tournament_id=None, season=None):
    """Store player statistics in the PlayerStats table."""
    team_org_id = get_current_team_id()
    
    for player in players:
        if player.id in player_stats_dict:
            stats = player_stats_dict[player.id]
            
            # Calculate PER if points played > 0
            if stats.get('points_played', 0) > 0:
                stats['per'] = calculate_per_from_stats(stats, team_avgs)
            else:
                stats['per'] = 0
            
            # Check if a record already exists
            existing = PlayerStats.query.filter_by(
                player_id=player.id,
                game_id=game_id,
                tournament_id=tournament_id,
                season=season
            ).first()
            
            if existing:
                # Update existing record
                for key, value in stats.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                # Create new record
                player_stats_obj = PlayerStats(
                    player_id=player.id,
                    team_organization_id=team_org_id,
                    game_id=game_id,
                    tournament_id=tournament_id,
                    season=season,
                    **stats
                )
                db.session.add(player_stats_obj)
    
    db.session.commit()
