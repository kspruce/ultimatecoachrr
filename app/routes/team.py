from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.player import Player
from app.forms.team import PlayerForm, PlayerFilterForm
from app.models.clip import ClipPlayer
from app.models.point import LineUp
from app.models.event import Event, Pull
from app.models.session import Attendance, SessionRSVP

bp = Blueprint('team', __name__, url_prefix='/team')

@bp.route('/')
@login_required
def index():
    form = PlayerFilterForm()
    
    # Get filter parameters
    position = request.args.get('position', '')
    line_preference = request.args.get('line_preference', '')
    gender_match = request.args.get('gender_match', '')
    team = request.args.get('team', '')
    active_only = request.args.get('active_only', 'y')
    
    # Set form values from query parameters
    if position:
        form.position.data = position
    if line_preference:
        form.line_preference.data = line_preference
    if gender_match:
        form.gender_match.data = gender_match
    if team and hasattr(form, 'team'):
        form.team.data = team
    form.active_only.data = active_only != 'n'
    
    # Build query based on filters
    query = Player.query
    
    if position:
        query = query.filter(Player.position == position)
    if line_preference:
        query = query.filter(Player.line_preference == line_preference)
    if gender_match:
        query = query.filter(Player.gender_match == gender_match)
    if team and hasattr(Player, 'team'):
        query = query.filter(Player.team == team)
    if active_only != 'n':
        query = query.filter(Player.active == True)
    
    # Get players and sort by jersey number
    players = query.order_by(Player.jersey_number).all()
    
    # Debug output
    print(f"Found {len(players)} players")
    for player in players:
        print(f"Player: {player.name}, Jersey: {player.jersey_number}")
    
    return render_template('team/index.html', players=players, form=form)



@bp.route('/add_player', methods=['GET', 'POST'])
@login_required
def add_player():
    form = PlayerForm()
    if form.validate_on_submit():
        player = Player(
            name=form.name.data,
            jersey_number=form.jersey_number.data,
            position=form.position.data,
            height=form.height.data if hasattr(form, 'height') else None,
            weight=form.weight.data if hasattr(form, 'weight') else None,
            gender=form.gender_match.data,  # Set gender = gender_match
            gender_match=form.gender_match.data,
            team=form.team.data if hasattr(form, 'team') else None,
            birth_date=form.birth_date.data if hasattr(form, 'birth_date') else None,
            email=form.email.data,
            phone=form.phone.data if hasattr(form, 'phone') else None,
            line_preference=form.line_preference.data,
            active=form.active.data,
            notes=form.notes.data if hasattr(form, 'notes') else None
        )
        db.session.add(player)
        db.session.commit()
        flash(f'Player {player.name} has been added!', 'success')
        return redirect(url_for('team.index'))
    return render_template('team/player_form.html', title='Add Player', form=form)


@bp.route('/edit_player/<int:player_id>', methods=['GET', 'POST'])
@login_required
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    form = PlayerForm(obj=player)
    if form.validate_on_submit():
        player.name = form.name.data
        player.jersey_number = form.jersey_number.data
        player.position = form.position.data
        player.height = form.height.data if hasattr(form, 'height') else None
        player.weight = form.weight.data if hasattr(form, 'weight') else None
        player.gender = form.gender_match.data  # Set gender = gender_match
        player.gender_match = form.gender_match.data
        player.team = form.team.data if hasattr(form, 'team') else None
        player.birth_date = form.birth_date.data if hasattr(form, 'birth_date') else None
        player.email = form.email.data
        player.phone = form.phone.data if hasattr(form, 'phone') else None
        player.line_preference = form.line_preference.data
        player.active = form.active.data
        player.notes = form.notes.data if hasattr(form, 'notes') else None
        db.session.commit()
        flash(f'Player {player.name} has been updated!', 'success')
        return redirect(url_for('team.index'))
    return render_template('team/player_form.html', title='Edit Player', form=form)

@bp.route('/delete_player/<int:player_id>', methods=['POST'])
@login_required
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)
    
    try:
        # Delete clip associations
        ClipPlayer.query.filter_by(player_id=player_id).delete()
        
        # Delete lineup entries
        LineUp.query.filter_by(player_id=player_id).delete()
        
        # Set receiver_id to NULL in events where this player is the receiver
        Event.query.filter_by(receiver_id=player_id).update({Event.receiver_id: None})
        
        # Delete events where this player is the actor
        Event.query.filter_by(player_id=player_id).delete()
        
        # Delete pulls by this player
        Pull.query.filter_by(player_id=player_id).delete()
        
        # Delete attendance records
        Attendance.query.filter_by(player_id=player_id).delete()
        
        # Delete RSVPs
        if 'SessionRSVP' in globals():  # Check if SessionRSVP model exists
            SessionRSVP.query.filter_by(player_id=player_id).delete()
        
        # Now delete the player
        db.session.delete(player)
        db.session.commit()
        
        flash(f'Player {player.name} has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting player: {str(e)}', 'danger')
        print(f"Error deleting player: {str(e)}")
    
    return redirect(url_for('team.index'))

@bp.route('/player/<int:player_id>')
@login_required
def player_detail(player_id):
    player = Player.query.get_or_404(player_id)
    return render_template('team/player_detail.html', player=player)

@bp.route('/debug')
@login_required
def debug():
    players = Player.query.all()
    return render_template('team/debug.html', players=players)