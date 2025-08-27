from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import admin_required
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
from app.utils.team_utils import get_current_team_id
from sqlalchemy import func
from app import db
import time

# Create a blueprint for admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@login_required
@admin_required
def index():
    """Admin dashboard index page."""
    return render_template('admin/index.html')

@admin_bp.route('/stats_calculator')
@login_required
@admin_required
def stats_calculator():
    """Redirect to the stats calculator in the admin_stats blueprint."""
    return redirect(url_for('admin_stats.calculator'))

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

# Register the blueprint in your app's __init__.py
# from app.routes.admin import admin_bp
# app.register_blueprint(admin_bp)
