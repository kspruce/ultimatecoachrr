from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import text
from app import db
from app.models.player import Player
from app.models.user import User
from app.forms.team import PlayerForm, PlayerFilterForm
from app.models.point import LineUp
from app.models.event import Event, Pull
from app.models.session import Attendance, SessionRSVP
from app.utils.utils import admin_required

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
    
    # Create a form instance for CSRF token
    csrf_form = FlaskForm()
    
    return render_template('team/index.html', 
                         players=players, 
                         form=form,
                         csrf_form=csrf_form)

@bp.route('/add_player', methods=['GET', 'POST'])
@login_required
@admin_required
def add_player():
    form = PlayerForm()
    if form.validate_on_submit():
        try:
            # Create the player
            player = Player(
                name=form.name.data,
                jersey_number=form.jersey_number.data,
                position=form.position.data,
                gender=form.gender_match.data,
                gender_match=form.gender_match.data,
                team=form.team.data if hasattr(form, 'team') else None,
                email=form.email.data,
                line_preference=form.line_preference.data,
                active=form.active.data
            )
            
            db.session.add(player)
            
            # Create user account if requested
            if form.create_account.data and form.username.data and form.password.data:
                user = User(
                    username=form.username.data,
                    email=form.email.data,
                    role='player',
                    is_admin=False
                )
                user.set_password(form.password.data)
                db.session.add(user)
                db.session.flush()  # Get user.id
                
                # Link player to user
                player.user_id = user.id
            
            db.session.commit()
            flash(f'Player {player.name} has been added!', 'success')
            
            # Check if "Save and Add Another" was clicked
            if 'add_another' in request.form:
                return redirect(url_for('team.add_player'))
            return redirect(url_for('team.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding player: {str(e)}', 'danger')
            return render_template('team/player_form.html', title='Add Player', form=form)
            
    return render_template('team/player_form.html', title='Add Player', form=form)

@bp.route('/edit_player/<int:player_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    form = PlayerForm(obj=player)
    
    if request.method == 'GET' and player.user_account:
        form.create_account.data = True
        form.username.data = player.user_account.username
    
    if form.validate_on_submit():
        try:
            player.name = form.name.data
            player.jersey_number = form.jersey_number.data
            player.position = form.position.data
            player.gender = form.gender_match.data
            player.gender_match = form.gender_match.data
            player.team = form.team.data if hasattr(form, 'team') else None
            player.email = form.email.data
            player.line_preference = form.line_preference.data
            player.active = form.active.data

            # Handle user account
            if form.create_account.data:
                if player.user_account:
                    # Update existing user account
                    if form.username.data != player.user_account.username:
                        player.user_account.username = form.username.data
                    if form.password.data:
                        player.user_account.set_password(form.password.data)
                else:
                    # Create new user account
                    user = User(
                        username=form.username.data,
                        email=form.email.data,
                        role='player',
                        is_admin=False
                    )
                    user.set_password(form.password.data)
                    db.session.add(user)
                    db.session.flush()
                    player.user_id = user.id
            
            db.session.commit()
            flash(f'Player {player.name} has been updated!', 'success')
            return redirect(url_for('team.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating player: {str(e)}', 'danger')
    
    return render_template('team/player_form.html', title='Edit Player', form=form, player=player)

@bp.route('/delete_player/<int:player_id>', methods=['POST'])
@login_required
@admin_required
def delete_player(player_id):
    try:
        player = Player.query.get_or_404(player_id)
        name = player.name

        # Delete player_point_stats
        db.session.execute(
            text("DELETE FROM player_point_stats WHERE player_id = :player_id"),
            {"player_id": player_id}
        )

        # Delete throws first (both as thrower and receiver)
        db.session.execute(
            text("DELETE FROM throw WHERE thrower_id = :player_id OR receiver_id = :player_id"),
            {"player_id": player_id}
        )

        # Delete related records - Updated to use new relationship pattern
        # Remove player from clips (many-to-many relationship)
        player.clips = []  # This will remove the associations without deleting clips
        
        LineUp.query.filter_by(player_id=player_id).delete()
        Event.query.filter_by(receiver_id=player_id).update({Event.receiver_id: None})
        Event.query.filter_by(player_id=player_id).delete()
        Pull.query.filter_by(player_id=player_id).delete()
        Attendance.query.filter_by(player_id=player_id).delete()
        
        if hasattr(player, 'session_rsvps'):
            SessionRSVP.query.filter_by(player_id=player_id).delete()

        # Delete associated user account if it exists
        if player.user_account:
            db.session.delete(player.user_account)

        # Finally delete the player
        db.session.delete(player)
        db.session.commit()
        
        flash(f'Player {name} has been deleted successfully.', 'success')
        return redirect(url_for('team.index'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting player: {str(e)}', 'danger')
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
