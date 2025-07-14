from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.tournament import Tournament
from app.models.game import Game  # Add this import
from app.forms.tournament import TournamentForm, TournamentFilterForm


bp = Blueprint('tournament', __name__, url_prefix='/tournaments')

@bp.route('/')
@login_required
def index():
    form = TournamentFilterForm()
    
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
    
    return render_template('tournament/index.html', tournaments=tournaments, form=form)

@bp.route('/<int:tournament_id>')
@login_required
def detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    # Change this line to order by Game.date instead of Tournament.start_date
    games = tournament.games.order_by(Game.date.desc()).all()
    return render_template('tournament/detail.html', tournament=tournament, games=games)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
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
def delete(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    name = tournament.name
    
    # Check if tournament has games
    if tournament.games.count() > 0:
        flash(f'Cannot delete tournament {name} because it has games associated with it.', 'danger')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))
    
    db.session.delete(tournament)
    db.session.commit()
    flash(f'Tournament {name} has been deleted!', 'success')
    return redirect(url_for('tournament.index'))
