# app/routes/tournament.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import text, and_
from app import db
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.forms.tournament import TournamentForm, TournamentFilterForm
from app.forms.rsvp_form import RSVPForm
from app.utils.utils import coach_required
from wtforms import SubmitField
from app.utils.team_filter import get_current_team_id, team_player_ids, team_row_or_404
from app.utils.season import (current_season, get_or_create_season, label_year, scope_tournaments, season_for_date,
                              team_seasons, team_squads, viewing_season, viewing_squad)

bp = Blueprint('tournament', __name__, url_prefix='/tournaments')


@bp.route('/')
@login_required
def index():
    form = TournamentFilterForm()
    delete_form = FlaskForm()  # Add this for CSRF protection
    
    # The season (and squad) being viewed, or ?season=<year|all>
    team_id = get_current_team_id()
    form.season.choices = [('all', 'All time')] + [(str(s.year), s.name) for s in team_seasons(team_id)]
    season = viewing_season(team_id)
    form.season.data = str(season.year) if season else 'all'

    query = scope_tournaments(Tournament.query.filter_by(team_organization_id=team_id), team_id)

    # Get tournaments and sort by start date (most recent first)
    tournaments = query.order_by(Tournament.start_date.desc()).all()
    
    return render_template('tournament/index.html', 
                         tournaments=tournaments, 
                         form=form,
                         delete_form=delete_form)

def _season_choices(form):
    team_id = get_current_team_id()
    form.season.choices = [('', 'From the start date')] + [(str(s.year), s.name) for s in team_seasons(team_id)]
    form.squad_id.choices = [('', 'Whole club')] + [(str(s.id), s.name) for s in team_squads(team_id)]


def _apply_season(form, tournament):
    """The picked season (made if it's a new year), else the one the start
    date is in; the tournament's games move with it."""
    team_id = get_current_team_id()
    year = label_year(form.season.data)
    season = None
    if year:
        season = get_or_create_season(team_id, year)
    elif tournament.start_date and team_seasons(team_id):
        season = season_for_date(team_id, tournament.start_date) or get_or_create_season(
            team_id, tournament.start_date.year)
    if season is not None:
        tournament.season_obj = season
        tournament.season = season.name
    squad_id = next((s.id for s in team_squads(team_id) if str(s.id) == (form.squad_id.data or '')), None)
    tournament.squad_id = squad_id
    if tournament.id is not None:
        for game in tournament.games:
            if season is not None:
                game.season = season
            game.squad_id = squad_id


@bp.route('/<int:tournament_id>')
@login_required
def detail(tournament_id):
    tournament = Tournament.query.filter_by(
        id=tournament_id, 
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    games = tournament.games.order_by(Game.date.desc()).all()
    delete_form = FlaskForm()  # Add CSRF form here too
    
    # Get player RSVP if user has a player profile
    player_rsvp = None
    if current_user.player:
        player_rsvp = TournamentRSVP.query.filter_by(
            tournament_id=tournament_id, 
            player_id=current_user.player.id
        ).first()
    
    return render_template('tournament/detail.html', 
                         tournament=tournament, 
                         games=games,
                         delete_form=delete_form,
                         player_rsvp=player_rsvp)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add():
    form = TournamentForm()
    _season_choices(form)
    if request.method == 'GET':
        current = current_season(get_current_team_id())
        form.season.data = str(current.year) if current else ''
        squad = viewing_squad()
        form.squad_id.data = str(squad.id) if squad else ''
    if form.validate_on_submit():
        
        tournament = Tournament(
            name=form.name.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            location=form.location.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        _apply_season(form, tournament)
        
        try:
            db.session.add(tournament)
            db.session.commit()
            flash(f'Tournament {tournament.name} has been added!', 'success')
            return redirect(url_for('tournament.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding tournament: {str(e)}', 'danger')
    
    return render_template('tournament/form.html', form=form, title='Add Tournament')


@bp.route('/edit/<int:tournament_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit(tournament_id):
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = TournamentForm(obj=tournament)
    _season_choices(form)
    if request.method == 'GET':
        form.season.data = str(tournament.season_obj.year) if tournament.season_obj else ''
        form.squad_id.data = str(tournament.squad_id or '')

    if form.validate_on_submit():
        tournament.name = form.name.data
        tournament.start_date = form.start_date.data
        tournament.end_date = form.end_date.data
        tournament.location = form.location.data
        _apply_season(form, tournament)
        
        db.session.commit()
        flash(f'Tournament {tournament.name} has been updated!', 'success')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))
    
    return render_template('tournament/form.html', form=form, title='Edit Tournament')

@bp.route('/delete/<int:tournament_id>', methods=['POST'])
@login_required
@coach_required
def delete(tournament_id):
    try:
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
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

        # Delete all RSVPs
        TournamentRSVP.query.filter_by(tournament_id=tournament_id).delete()
        
        # Finally delete the tournament
        db.session.delete(tournament)
        db.session.commit()
        
        flash(f'Tournament {name} and all associated data has been deleted!', 'success')
        return redirect(url_for('tournament.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting tournament: {str(e)}', 'danger')
        return redirect(url_for('tournament.index'))

# RSVP Routes
@bp.route('/<int:tournament_id>/rsvp', methods=['GET', 'POST'])
@login_required
def rsvp(tournament_id):
    """
    Handle RSVPs for a tournament.
    This function handles both standard form submissions and JSON API requests.
    """
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    if not current_user.player:
        if request.is_json:
            return jsonify({'success': False, 'message': 'You need to link your account to a player first.'}), 403
        flash('You need to link your account to a player before you can RSVP.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    player = current_user.player
    existing_rsvp = TournamentRSVP.query.filter_by(tournament_id=tournament_id, player_id=player.id).first()

    # Handle JSON API request from the calendar modal
    if request.is_json:
        data = request.get_json()
        status = data.get('status')
        notes = data.get('notes', '')

        if not status or status not in ['attending', 'maybe', 'not_attending']:
            return jsonify({'success': False, 'message': 'Invalid status provided.'}), 400
        
        try:
            if existing_rsvp:
                existing_rsvp.status = status
                existing_rsvp.notes = notes
            else:
                
                new_rsvp = TournamentRSVP(
                    tournament_id=tournament_id,
                    player_id=player.id,
                    status=status,
                    notes=notes,
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(new_rsvp)
            db.session.commit()
            return jsonify({'success': True, 'message': 'RSVP updated successfully.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    # Handle standard HTML form submission
    form = RSVPForm(obj=existing_rsvp)
    if form.validate_on_submit():
        try:
            if existing_rsvp:
                existing_rsvp.status = form.status.data
                existing_rsvp.notes = form.notes.data
            else:
                
                new_rsvp = TournamentRSVP(
                    tournament_id=tournament_id,
                    player_id=player.id,
                    status=form.status.data,
                    notes=form.notes.data,
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(new_rsvp)
            
            db.session.commit()
            flash('Your RSVP has been submitted!', 'success')
            return redirect(url_for('tournament.detail', tournament_id=tournament_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting RSVP: {str(e)}', 'danger')
            # Log the error
            import logging
            logging.error(f"Failed to submit RSVP: {str(e)}")

    # Render the RSVP page for GET requests
    return render_template('calendar/tournament_rsvp.html', form=form, tournament=tournament, existing_rsvp=existing_rsvp)


# Admin RSVP Management
@bp.route('/<int:tournament_id>/rsvps')
@login_required
@coach_required
def rsvps(tournament_id):
    """Display RSVPs for a tournament."""
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Load all RSVPs in a single query, then group in Python
    all_rsvps = TournamentRSVP.query.filter_by(
        tournament_id=tournament_id,
        team_organization_id=get_current_team_id()
    ).all()

    attending     = [r for r in all_rsvps if r.status == 'attending']
    maybe         = [r for r in all_rsvps if r.status == 'maybe']
    not_attending = [r for r in all_rsvps if r.status == 'not_attending']

    rsvp_player_ids = [r.player_id for r in all_rsvps]
    
    no_rsvp_players = Player.query.filter(
        Player.active == True,
        Player.team_organization_id == get_current_team_id(),
        ~Player.id.in_(rsvp_player_ids) if rsvp_player_ids else True
    ).all()
    
    # Get selected players
    selected_players = Player.query.join(TournamentRSVP).filter(
        and_(
            TournamentRSVP.tournament_id == tournament_id,
            TournamentRSVP.selected_by_admin == True,
            TournamentRSVP.team_organization_id == get_current_team_id(),
            Player.team_organization_id == get_current_team_id()
        )
    ).all()
    
    # Create form for player selection
    class SelectionForm(FlaskForm):
        submit = SubmitField('Save Selections')
    
    selection_form = SelectionForm()
    
    return render_template(
        'tournament/tournament_rsvps.html',
        tournament=tournament,
        attending=attending,
        maybe=maybe,
        not_attending=not_attending,
        no_rsvp_players=no_rsvp_players,
        selected_players=selected_players,
        selection_form=selection_form
    )

@bp.route('/<int:tournament_id>/update_selections', methods=['POST'])
@login_required
@coach_required
def update_selections(tournament_id):
    """Update player selections for a tournament."""
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get selected player IDs from form
    selected_player_ids = [str(pid) for pid in team_player_ids(request.form.getlist('selected_players'))]
    
    try:
        # Update all RSVPs for this tournament
        all_rsvps = TournamentRSVP.query.filter_by(
            tournament_id=tournament_id,
            team_organization_id=get_current_team_id()
        ).all()
        
        # Create a set of player IDs with RSVPs
        rsvp_player_ids = {rsvp.player_id for rsvp in all_rsvps}
        
        # Update existing RSVPs
        for rsvp in all_rsvps:
            rsvp.selected_by_admin = str(rsvp.player_id) in selected_player_ids
        
        # Create new RSVPs for players who didn't have one but were selected
        for player_id in selected_player_ids:
            player_id = int(player_id)
            if player_id not in rsvp_player_ids:
                
                # Create a new RSVP with admin selection
                new_rsvp = TournamentRSVP(
                    tournament_id=tournament_id,
                    player_id=player_id,
                    status='attending',  # Default status
                    selected_by_admin=True,
                    notes='Added by admin',
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(new_rsvp)
        
        db.session.commit()
        flash(f'{len(selected_player_ids)} players selected for {tournament.name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating selections: {str(e)}', 'danger')
        # Log the error
        import logging
        logging.error(f"Failed to update selections: {str(e)}")
    
    return redirect(url_for('tournament.rsvps', tournament_id=tournament_id))


@bp.route('/<int:tournament_id>/assign_players')
@login_required
@coach_required
def assign_players(tournament_id):
    """Assign selected players to games in a tournament."""
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get selected players
    selected_players = Player.query.join(TournamentRSVP).filter(
        and_(
            TournamentRSVP.tournament_id == tournament_id,
            TournamentRSVP.selected_by_admin == True,
            TournamentRSVP.team_organization_id == get_current_team_id(),
            Player.team_organization_id == get_current_team_id()
        )
    ).all()
    
    # Get games in this tournament
    games = Game.query.filter_by(
        tournament_id=tournament_id,
        team_organization_id=get_current_team_id()
    ).order_by(Game.date).all()
    
    # Load all GamePlayer records for this tournament's games in one query
    game_ids = [g.id for g in games]
    all_assignments = GamePlayer.query.filter(
        GamePlayer.game_id.in_(game_ids)
    ).all() if game_ids else []
    game_players = {}
    for gp in all_assignments:
        game_players.setdefault(gp.game_id, []).append(gp.player_id)
    
    # Create form for player assignment
    class AssignmentForm(FlaskForm):
        submit = SubmitField('Save Assignments')
    
    form = AssignmentForm()
    
    return render_template(
        'tournament/assign_players.html',
        tournament=tournament,
        selected_players=selected_players,
        games=games,
        game_players=game_players,
        form=form
    )

@bp.route('/<int:tournament_id>/games/<int:game_id>/update_players', methods=['POST'])
@login_required
@coach_required
def update_game_players(tournament_id, game_id):
    """Update player assignments for a specific game."""
    tournament = Tournament.query.filter_by(
        id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    game = Game.query.filter_by(
        id=game_id,
        tournament_id=tournament_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get selected player IDs from form
    selected_player_ids = team_player_ids(request.form.getlist('game_players'))
    
    # Remove existing assignments
    GamePlayer.query.filter_by(game_id=game_id).delete()
    
    # Add new assignments
    for player_id in selected_player_ids:
        game_player = GamePlayer(
            game_id=game_id,
            player_id=int(player_id),
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        db.session.add(game_player)
    
    db.session.commit()
    
    flash(f'{len(selected_player_ids)} players assigned to game vs {game.opponent}', 'success')
    return redirect(url_for('tournament.assign_players', tournament_id=tournament_id))

@bp.route('/<int:tournament_id>/bulk-update', methods=['POST'])
@login_required
@coach_required
def bulk_update_game_players(tournament_id):
    tournament = team_row_or_404(Tournament, tournament_id)

    for game in tournament.games:

        selected_player_ids = team_player_ids(request.form.getlist(
            f'game_players_{game.id}'
        ))

        # Delete existing assignments
        GamePlayer.query.filter_by(game_id=game.id).delete()

        # Create new assignments
        for player_id in selected_player_ids:
            assignment = GamePlayer(
                game_id=game.id,
                player_id=int(player_id),
                team_organization_id=get_current_team_id()
            )
            db.session.add(assignment)

    db.session.commit()

    flash("Game assignments updated successfully.", "success")

    return redirect(
        url_for('tournament.assign_players',
                tournament_id=tournament_id)
    )
