from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from app import db
from app.models.game import Game
from app.models.tournament import Tournament
from app.forms.game import GameForm, GameFilterForm
from app.models.point import Point, LineUp
from app.models.player import Player
from app.utils.utils import admin_required

bp = Blueprint('game', __name__, url_prefix='/games')

@bp.route('/')
@login_required
def index():
    form = GameFilterForm()
    delete_form = FlaskForm()  # Add this for CSRF protection
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    opponent = request.args.get('opponent', '')
    result = request.args.get('result', '')
    
    # Set form values from query parameters
    if tournament_id:
        form.tournament_id.data = tournament_id
    form.opponent.data = opponent
    form.result.data = result
    
    # Build query based on filters
    query = Game.query
    
    if tournament_id and tournament_id > 0:
        query = query.filter(Game.tournament_id == tournament_id)
    if opponent:
        query = query.filter(Game.opponent.ilike(f'%{opponent}%'))
    if result == 'win':
        query = query.filter(Game.our_score > Game.their_score)
    elif result == 'loss':
        query = query.filter(Game.our_score < Game.their_score)
    elif result == 'tie':
        query = query.filter(Game.our_score == Game.their_score)
    
    # Get games and sort by date (most recent first)
    games = query.order_by(Game.date.desc()).all()
    
    return render_template('game/index.html', 
                         games=games, 
                         form=form,
                         delete_form=delete_form)

@bp.route('/<int:game_id>')
@login_required
def detail(game_id):
    game = Game.query.get_or_404(game_id)
    all_players = Player.query.filter_by(active=True).all()
    delete_form = FlaskForm()  # Add CSRF form here too

    # Get players already assigned to the game through LineUp
    game_players = []
    if game.points.count() > 0:
        first_point = game.points.first()
        game_players = [lineup.player for lineup in first_point.lineups]

    return render_template('game/detail.html', 
                         game=game, 
                         all_players=all_players, 
                         game_players=game_players,
                         delete_form=delete_form)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = GameForm()
    
    if form.validate_on_submit():
        game = Game(
            opponent=form.opponent.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            date=form.date.data,
            youtube_link=form.youtube_link.data,
            notes=form.notes.data
        )
        
        if form.tournament_id.data > 0:
            game.tournament_id = form.tournament_id.data
        
        db.session.add(game)
        db.session.flush()
        
        if form.players_present.data:
            point = Point.query.filter_by(game_id=game.id).first()
            if not point:
                point = Point(
                    game_id=game.id,
                    point_number=1,
                    our_line_type='O-Line',
                    our_score_before=0,
                    their_score_before=0,
                    starting_position='offense',
                    point_outcome='scored',
                    our_score_after=1,
                    their_score_after=0
                )
                db.session.add(point)
                db.session.flush()

            for player_id in form.players_present.data:
                lineup = LineUp(player_id=player_id, point_id=point.id, line_type='O-Line')
                db.session.add(lineup)

        db.session.commit()
        flash(f'Game against {game.opponent} has been added!', 'success')
        return redirect(url_for('game.index'))
    
    tournament_id = request.args.get('tournament_id', type=int)
    if tournament_id:
        form.tournament_id.data = tournament_id
    
    return render_template('game/form.html', form=form, title='Add Game')

@bp.route('/edit/<int:game_id>', methods=['GET', 'POST'])
@login_required
def edit(game_id):
    game = Game.query.get_or_404(game_id)
    form = GameForm(obj=game)
    
    if form.validate_on_submit():
        game.opponent = form.opponent.data
        game.our_score = form.our_score.data
        game.their_score = form.their_score.data
        game.date = form.date.data
        game.youtube_link = form.youtube_link.data
        game.notes = form.notes.data
        
        if form.tournament_id.data > 0:
            game.tournament_id = form.tournament_id.data
        else:
            game.tournament_id = None
        
        db.session.commit()
        flash(f'Game against {game.opponent} has been updated!', 'success')
        return redirect(url_for('game.detail', game_id=game.id))
    
    return render_template('game/form.html', form=form, title='Edit Game')

@bp.route('/delete/<int:game_id>', methods=['POST'])
@login_required
@admin_required
def delete(game_id):
    try:
        game = Game.query.get_or_404(game_id)
        opponent = game.opponent
        
        # Check if game has points or clips
        if game.points.count() > 0 or game.clips.count() > 0:
            message = f'Cannot delete game against {opponent} because it has points or clips associated with it.'
            if request.is_json:
                return jsonify({'success': False, 'message': message}), 400
            flash(message, 'danger')
            return redirect(url_for('game.detail', game_id=game.id))
        
        db.session.delete(game)
        db.session.commit()
        
        message = f'Game against {opponent} has been deleted!'
        if request.is_json:
            return jsonify({'success': True, 'message': message})
            
        flash(message, 'success')
        return redirect(url_for('game.index'))
        
    except Exception as e:
        db.session.rollback()
        message = f'Error deleting game: {str(e)}'
        if request.is_json:
            return jsonify({'success': False, 'message': message}), 500
        flash(message, 'danger')
        return redirect(url_for('game.detail', game_id=game.id))

@bp.route('/<int:game_id>/update_players', methods=['POST'])
@login_required
def update_players(game_id):
    game = Game.query.get_or_404(game_id)
    player_ids = request.form.getlist('player_ids', type=int)

    point = Point.query.filter_by(game_id=game.id).first()
    if not point:
        point = Point(
            game_id=game.id,
            point_number=1,
            our_line_type='O-Line',
            our_score_before=0,
            their_score_before=0,
            starting_position='offense',
            point_outcome='scored',
            our_score_after=1,
            their_score_after=0
        )
        db.session.add(point)
        db.session.flush()

    LineUp.query.filter_by(point_id=point.id).delete()

    for player_id in player_ids:
        lineup = LineUp(player_id=player_id, point_id=point.id)
        db.session.add(lineup)

    db.session.commit()
    flash('Players updated successfully!', 'success')
    return redirect(url_for('game.detail', game_id=game_id))
