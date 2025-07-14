from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import text
from app import db
from app.models.tournament import Tournament
from app.models.game import Game
from app.forms.tournament import TournamentForm, TournamentFilterForm
from app.utils.utils import admin_required

bp = Blueprint('tournament', __name__, url_prefix='/tournaments')

@bp.route('/')
@login_required
def index():
    form = TournamentFilterForm()
    delete_form = FlaskForm()  # Add this for CSRF protection
    
    # Get filter parameters
    season = request.args.get('season', '')
    
    # Set form values from query parameters
    form.season.data = season
    
    # Build query based on filters
    query = Tournament.query
    
    if season:
        query = query.filter(Tournament.season == season)
    
    # Get tournaments and sort by start date (most recent first)
    tournaments = query.order_by(Tournament.start_date.desc()).all()
    
    return render_template('tournament/index.html', 
                         tournaments=tournaments, 
                         form=form,
                         delete_form=delete_form)

@bp.route('/<int:tournament_id>')
@login_required
def detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    games = tournament.games.order_by(Game.date.desc()).all()
    delete_form = FlaskForm()  # Add CSRF form here too
    return render_template('tournament/detail.html', 
                         tournament=tournament, 
                         games=games,
                         delete_form=delete_form)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    form = TournamentForm()
    if form.validate_on_submit():
        tournament = Tournament(
            name=form.name.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            location=form.location.data,
            season=form.season.data
        )
        db.session.add(tournament)
        db.session.commit()
        flash(f'Tournament {tournament.name} has been added!', 'success')
        return redirect(url_for('tournament.index'))
    return render_template('tournament/form.html', form=form, title='Add Tournament')

@bp.route('/edit/<int:tournament_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    form = TournamentForm(obj=tournament)
    
    if form.validate_on_submit():
        tournament.name = form.name.data
        tournament.start_date = form.start_date.data
        tournament.end_date = form.end_date.data
        tournament.location = form.location.data
        tournament.season = form.season.data
        
        db.session.commit()
        flash(f'Tournament {tournament.name} has been updated!', 'success')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))
    
    return render_template('tournament/form.html', form=form, title='Edit Tournament')

@bp.route('/delete/<int:tournament_id>', methods=['POST'])
@login_required
@admin_required
def delete(tournament_id):
    try:
        tournament = Tournament.query.get_or_404(tournament_id)
        name = tournament.name

        # Delete all related data for each game in the tournament
        for game in tournament.games:
            # Delete throws associated with events in each point
            for point in game.points:
                # Delete throws
                db.session.execute(
                    text("DELETE FROM throw WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete player point stats
                db.session.execute(
                    text("DELETE FROM player_point_stats WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )

                # Delete events
                db.session.execute(
                    text("DELETE FROM event WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete pulls
                db.session.execute(
                    text("DELETE FROM pull WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )
                
                # Delete lineups
                db.session.execute(
                    text("DELETE FROM line_up WHERE point_id = :point_id"),
                    {"point_id": point.id}
                )

            # Delete points
            db.session.execute(
                text("DELETE FROM point WHERE game_id = :game_id"),
                {"game_id": game.id}
            )

            # Delete clips if any
            if hasattr(game, 'clips'):
                for clip in game.clips:
                    # Delete clip tags
                    db.session.execute(
                        text("DELETE FROM clip_tag_relation WHERE clip_id = :clip_id"),
                        {"clip_id": clip.id}
                    )
                    # Delete clip players
                    db.session.execute(
                        text("DELETE FROM clip_player WHERE clip_id = :clip_id"),
                        {"clip_id": clip.id}
                    )
                # Delete clips
                db.session.execute(
                    text("DELETE FROM clip WHERE game_id = :game_id"),
                    {"game_id": game.id}
                )

            # Delete the game
            db.session.delete(game)

        # Finally delete the tournament
        db.session.delete(tournament)
        db.session.commit()
        
        flash(f'Tournament {name} and all associated data has been deleted!', 'success')
        return redirect(url_for('tournament.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting tournament: {str(e)}', 'danger')
        return redirect(url_for('tournament.index'))
