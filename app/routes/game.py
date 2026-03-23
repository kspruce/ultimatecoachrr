from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from app import db
from app.models.game import Game
from app.models.tournament import Tournament
from app.forms.game import GameForm, GameFilterForm
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.event import Event, Pull
from app.utils.utils import admin_required, coach_required, stat_taker_required
from datetime import datetime
from app.models.game_player import GamePlayer
from app.models.tournament_rsvp import TournamentRSVP
from sqlalchemy import and_
from app.utils.team_filter import get_current_team_id

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
    query = Game.query.filter_by(team_organization_id=get_current_team_id())
    
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
    
    # Get tournaments for quick filters
    tournaments = Tournament.query.filter_by(team_organization_id=get_current_team_id()).order_by(Tournament.start_date.desc()).all()
    
    return render_template('game/index.html', 
                         games=games, 
                         form=form,
                         delete_form=delete_form,
                         tournaments=tournaments)

@bp.route('/<int:game_id>')
@login_required
def detail(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    all_players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).all()
    
    delete_form = FlaskForm()  # Add CSRF form here too

    # Get players assigned to the game — single JOIN query instead of two round-trips
    game_players = (
        Player.query
        .join(GamePlayer, GamePlayer.player_id == Player.id)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.team_organization_id == get_current_team_id(),
            Player.team_organization_id == get_current_team_id(),
        )
        .all()
    )

    # Fall back to the first-point lineup if no GamePlayer records exist
    if not game_players and game.points.count() > 0:
        first_point = game.points.options(joinedload('lineups').joinedload('player')).first()
        game_players = [
            lu.player for lu in first_point.lineups
            if lu.player and lu.player.team_organization_id == get_current_team_id()
        ]

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
        # Find the highest existing game ID and add 1
        highest_id = db.session.query(db.func.max(Game.id)).scalar() or 0
        next_id = highest_id + 1
        
        game = Game(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            opponent=form.opponent.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            date=form.date.data,
            youtube_link=form.youtube_link.data,
            notes=form.notes.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        if form.tournament_id.data > 0:
            game.tournament_id = form.tournament_id.data
        
        db.session.add(game)
        db.session.flush()

        # ── Auto-assign players to the new game ───────────────────────────
        # Priority: players attending the linked tournament → full active roster
        team_id = get_current_team_id()
        auto_player_ids = []

        if game.tournament_id:
            # Players who RSVP'd as attending (or were admin-selected) for this tournament
            attending_rsvps = TournamentRSVP.query.filter(
                TournamentRSVP.tournament_id == game.tournament_id,
                TournamentRSVP.team_organization_id == team_id,
                TournamentRSVP.status == 'attending'
            ).all()
            auto_player_ids = [r.player_id for r in attending_rsvps]

        if not auto_player_ids:
            # No tournament attendance data — fall back to the full active roster
            auto_player_ids = [
                p.id for p in Player.query.filter_by(
                    active=True,
                    team_organization_id=team_id
                ).all()
            ]

        for player_id in auto_player_ids:
            next_gp_id = (db.session.query(db.func.max(GamePlayer.id)).scalar() or 0) + 1
            db.session.add(GamePlayer(
                id=next_gp_id,
                game_id=game.id,
                player_id=player_id,
                team_organization_id=team_id
            ))
        # ─────────────────────────────────────────────────────────────────

        if form.players_present.data:
            point = Point.query.filter_by(game_id=game.id).first()
            if not point:
                # Find the highest existing point ID and add 1
                highest_point_id = db.session.query(db.func.max(Point.id)).scalar() or 0
                next_point_id = highest_point_id + 1
                
                point = Point(
                    id=next_point_id,  # Explicitly set the ID
                    game_id=game.id,
                    point_number=1,
                    our_line_type='O-Line',
                    our_score_before=0,
                    their_score_before=0,
                    starting_position='offense',
                    point_outcome='scored',
                    our_score_after=1,
                    their_score_after=0,
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(point)
                db.session.flush()

            for player_id in form.players_present.data:
                # Find the highest existing lineup ID and add 1
                highest_lineup_id = db.session.query(db.func.max(LineUp.id)).scalar() or 0
                next_lineup_id = highest_lineup_id + 1
                
                lineup = LineUp(
                    id=next_lineup_id,  # Explicitly set the ID
                    player_id=player_id, 
                    point_id=point.id, 
                    line_type='O-Line',
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
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
@coach_required
def edit(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
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
@coach_required
def delete(game_id):
    try:
        game = Game.query.filter_by(
            id=game_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        opponent = game.opponent

        # First, get all point IDs for this game
        point_ids = [point.id for point in game.points]
        
        if point_ids:
            # Delete GameDayEvent records first (these are causing the foreign key violation)
            db.session.execute(
                text("DELETE FROM game_day_event WHERE point_id IN :point_ids AND team_organization_id = :team_id"),
                {"point_ids": tuple(point_ids) if len(point_ids) > 1 else f"({point_ids[0]})", "team_id": get_current_team_id()}
            )
            
            # Delete GameDayPlayerStats records
            db.session.execute(
                text("DELETE FROM game_day_player_stats WHERE game_id = :game_id AND team_organization_id = :team_id"),
                {"game_id": game_id, "team_id": get_current_team_id()}
            )

        # Delete all related data for each point
        for point in game.points:
            # Delete throws associated with events in this point
            db.session.execute(
                text("DELETE FROM throw WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )
            
            # Delete player point stats
            db.session.execute(
                text("DELETE FROM player_point_stats WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )
            
            # Delete cutting skills
            db.session.execute(
                text("DELETE FROM cutting_skill WHERE point_id = :point_id AND team_organization_id = :team_id"),
                {"point_id": point.id, "team_id": get_current_team_id()}
            )

            # Delete events
            Event.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()
            
            # Delete pulls
            Pull.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()
            
            # Delete lineups
            LineUp.query.filter_by(point_id=point.id, team_organization_id=get_current_team_id()).delete()

        # Delete all points
        Point.query.filter_by(game_id=game_id, team_organization_id=get_current_team_id()).delete()

        # Delete clips if any
        if hasattr(game, 'clips'):
            for clip in game.clips:
                # Delete clip tags
                db.session.execute(
                    text("DELETE FROM clip_tag_relation WHERE clip_id = :clip_id AND team_organization_id = :team_id"),
                    {"clip_id": clip.id, "team_id": get_current_team_id()}
                )
                # Delete clip players
                db.session.execute(
                    text("DELETE FROM clip_player WHERE clip_id = :clip_id AND team_organization_id = :team_id"),
                    {"clip_id": clip.id, "team_id": get_current_team_id()}
                )
            # Delete clips
            db.session.execute(
                text("DELETE FROM clip WHERE game_id = :game_id AND team_organization_id = :team_id"),
                {"game_id": game_id, "team_id": get_current_team_id()}
            )

        # Delete game player associations
        GamePlayer.query.filter_by(game_id=game_id, team_organization_id=get_current_team_id()).delete()

        # Finally delete the game
        db.session.delete(game)
        db.session.commit()
        
        message = f'Game against {opponent} and all associated data has been deleted!'
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
        return redirect(url_for('game.detail', game_id=game_id))

@bp.route('/<int:game_id>/update_players', methods=['POST'])
@login_required
@coach_required
def update_players(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    player_ids = request.form.getlist('player_ids', type=int)

    # Delete existing GamePlayer records
    GamePlayer.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).delete()
    
    # Add new GamePlayer records
    for player_id in player_ids:
        # Find the highest existing GamePlayer ID and add 1
        highest_id = db.session.query(db.func.max(GamePlayer.id)).scalar() or 0
        next_id = highest_id + 1
        
        game_player = GamePlayer(
            id=next_id,  # Explicitly set the ID
            game_id=game_id,
            player_id=player_id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        db.session.add(game_player)

    db.session.commit()
    flash('Players updated successfully!', 'success')
    return redirect(url_for('game.detail', game_id=game_id))

@bp.route('/add_multiple', methods=['GET', 'POST'])
@login_required
def add_multiple():
    tournament_id = request.args.get('tournament_id', type=int)
    tournament = None
    if tournament_id:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
    
    if request.method == 'POST':
        games_data = request.form.to_dict(flat=False)
        games_count = len(games_data.get('opponent[]', []))
        
        for i in range(games_count):
            # Find the highest existing game ID and add 1
            highest_id = db.session.query(db.func.max(Game.id)).scalar() or 0
            next_id = highest_id + 1
            
            game = Game(
                id=next_id,  # Explicitly set the ID
                opponent=games_data['opponent[]'][i],
                our_score=int(games_data['our_score[]'][i]),
                their_score=int(games_data['their_score[]'][i]),
                date=datetime.strptime(games_data['date[]'][i], '%Y-%m-%d').date(),
                youtube_link=games_data['youtube_link[]'][i] if games_data['youtube_link[]'][i] else None,
                notes=games_data['notes[]'][i] if games_data['notes[]'][i] else None,
                team_organization_id=get_current_team_id()  # Add team organization ID
            )
            
            if tournament_id:
                game.tournament_id = tournament_id
                
            db.session.add(game)
        
        db.session.commit()
        flash(f'{games_count} games have been added!', 'success')
        
        if tournament_id:
            return redirect(url_for('tournament.detail', tournament_id=tournament_id))
        return redirect(url_for('game.index'))
    
    return render_template('game/add_multiple.html', tournament=tournament)
