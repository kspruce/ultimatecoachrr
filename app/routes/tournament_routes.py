from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.decorators import admin_required
from datetime import datetime
from sqlalchemy import and_

tournament_bp = Blueprint('tournament', __name__)

@tournament_bp.route('/tournaments/<int:tournament_id>/rsvps')
@login_required
@admin_required
def rsvps(tournament_id):
    """Display RSVPs for a tournament."""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get RSVPs grouped by status
    attending = TournamentRSVP.query.filter_by(tournament_id=tournament_id, status='attending').all()
    maybe = TournamentRSVP.query.filter_by(tournament_id=tournament_id, status='maybe').all()
    not_attending = TournamentRSVP.query.filter_by(tournament_id=tournament_id, status='not_attending').all()
    
    # Get selected players
    selected_players = Player.query.join(TournamentRSVP).filter(
        and_(
            TournamentRSVP.tournament_id == tournament_id,
            TournamentRSVP.selected_by_admin == True
        )
    ).all()
    
    # Create form for player selection
    from flask_wtf import FlaskForm
    from wtforms import SubmitField
    
    class SelectionForm(FlaskForm):
        submit = SubmitField('Save Selections')
    
    selection_form = SelectionForm()
    
    return render_template(
        'tournament_rsvps.html',
        tournament=tournament,
        attending=attending,
        maybe=maybe,
        not_attending=not_attending,
        selected_players=selected_players,
        selection_form=selection_form
    )

@tournament_bp.route('/tournaments/<int:tournament_id>/update_selections', methods=['POST'])
@login_required
@admin_required
def update_selections(tournament_id):
    """Update player selections for a tournament."""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get selected player IDs from form
    selected_player_ids = request.form.getlist('selected_players')
    
    # Update all RSVPs for this tournament
    all_rsvps = TournamentRSVP.query.filter_by(tournament_id=tournament_id).all()
    
    for rsvp in all_rsvps:
        rsvp.selected_by_admin = str(rsvp.player_id) in selected_player_ids
    
    db.session.commit()
    
    flash(f'{len(selected_player_ids)} players selected for {tournament.name}', 'success')
    return redirect(url_for('tournament.rsvps', tournament_id=tournament_id))

@tournament_bp.route('/tournaments/<int:tournament_id>/assign_players')
@login_required
@admin_required
def assign_players(tournament_id):
    """Assign selected players to games in a tournament."""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get selected players
    selected_players = Player.query.join(TournamentRSVP).filter(
        and_(
            TournamentRSVP.tournament_id == tournament_id,
            TournamentRSVP.selected_by_admin == True
        )
    ).all()
    
    # Get games in this tournament
    games = Game.query.filter_by(tournament_id=tournament_id).order_by(Game.date).all()
    
    # Get current player assignments for each game
    game_players = {}
    for game in games:
        player_ids = [gp.player_id for gp in game.assigned_players.all()]
        game_players[game.id] = player_ids
    
    # Create form for player assignment
    from flask_wtf import FlaskForm
    from wtforms import SubmitField
    
    class AssignmentForm(FlaskForm):
        submit = SubmitField('Save Assignments')
    
    form = AssignmentForm()
    
    return render_template(
        'assign_players.html',
        tournament=tournament,
        selected_players=selected_players,
        games=games,
        game_players=game_players,
        form=form
    )

@tournament_bp.route('/tournaments/<int:tournament_id>/games/<int:game_id>/update_players', methods=['POST'])
@login_required
@admin_required
def update_game_players(tournament_id, game_id):
    """Update player assignments for a specific game."""
    tournament = Tournament.query.get_or_404(tournament_id)
    game = Game.query.get_or_404(game_id)
    
    # Ensure game belongs to tournament
    if game.tournament_id != tournament_id:
        flash('Game does not belong to this tournament.', 'danger')
        return redirect(url_for('tournament.assign_players', tournament_id=tournament_id))
    
    # Get selected player IDs from form
    selected_player_ids = request.form.getlist('game_players')
    
    # Remove existing assignments
    GamePlayer.query.filter_by(game_id=game_id).delete()
    
    # Add new assignments
    for player_id in selected_player_ids:
        game_player = GamePlayer(
            game_id=game_id,
            player_id=int(player_id)
        )
        db.session.add(game_player)
    
    db.session.commit()
    
    flash(f'{len(selected_player_ids)} players assigned to game vs {game.opponent}', 'success')
    return redirect(url_for('tournament.assign_players', tournament_id=tournament_id))