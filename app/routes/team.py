from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
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
from app.utils.utils import admin_required, coach_required, stat_taker_required
from app.models.session import SessionPlan
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from datetime import datetime
from markupsafe import Markup
from app.utils.team_filter import get_current_team_id
import re
import random
import string

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
    active_only = 'active_only' in request.args
    
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
    query = Player.query.filter_by(team_organization_id=get_current_team_id())
    
    if position:
        query = query.filter(Player.position == position)
    if line_preference:
        query = query.filter(Player.line_preference == line_preference)
    if gender_match:
        query = query.filter(Player.gender_match == gender_match)
    if team and hasattr(Player, 'team'):
        query = query.filter(Player.team == team)
    if active_only:
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
@coach_required
def add_player():
    form = PlayerForm()
    if form.validate_on_submit():
        try:
            # Find the highest existing player ID and add 1
            highest_id = db.session.query(db.func.max(Player.id)).scalar() or 0
            next_id = highest_id + 1
            
            # Create the player
            player = Player(
                id=next_id,  # Explicitly set the ID to avoid conflicts
                name=form.name.data,
                jersey_number=form.jersey_number.data,
                position=form.position.data,
                gender=form.gender_match.data,
                gender_match=form.gender_match.data,
                email=form.email.data,
                active=form.active.data,
                team_organization_id=get_current_team_id()  # Add team organization ID
            )
            
            db.session.add(player)
            
            # Create user account if requested
            if form.create_account.data and form.username.data and form.password.data:
                # Check if username already exists
                existing_user = User.query.filter_by(username=form.username.data).first()
                if existing_user:
                    flash(f'Username {form.username.data} is already taken.', 'danger')
                    return render_template('team/player_form.html', title='Add Player', form=form)
                
                # Find the highest existing user ID and add 1
                highest_user_id = db.session.query(db.func.max(User.id)).scalar() or 0
                next_user_id = highest_user_id + 1
                
                user = User(
                    id=next_user_id,  # Explicitly set the ID
                    username=form.username.data,
                    email=form.email.data,
                    role='player',
                    is_superadmin=False,
                    team_organization_id=get_current_team_id()  # Add team organization ID
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
@coach_required
def edit_player(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
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
                        # Check if new username is already taken
                        existing_user = User.query.filter(
                            User.username == form.username.data,
                            User.id != player.user_account.id
                        ).first()
                        
                        if existing_user:
                            flash(f'Username {form.username.data} is already taken.', 'danger')
                            return render_template('team/player_form.html', title='Edit Player', form=form, player=player)
                        
                        player.user_account.username = form.username.data
                    
                    if form.password.data:
                        player.user_account.set_password(form.password.data)
                else:
                    # Check if username is already taken
                    existing_user = User.query.filter_by(username=form.username.data).first()
                    if existing_user:
                        flash(f'Username {form.username.data} is already taken.', 'danger')
                        return render_template('team/player_form.html', title='Edit Player', form=form, player=player)
                    
                    # Find the highest existing user ID and add 1
                    highest_user_id = db.session.query(db.func.max(User.id)).scalar() or 0
                    next_user_id = highest_user_id + 1
                    
                    # Create new user account
                    user = User(
                        id=next_user_id,  # Explicitly set the ID
                        username=form.username.data,
                        email=form.email.data,
                        role='player',
                        is_superadmin=False,
                        team_organization_id=get_current_team_id()  # Add team organization ID
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
@coach_required
def delete_player(player_id):
    try:
        player = Player.query.filter_by(
            id=player_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        name = player.name

        # Delete player_point_stats
        db.session.execute(
            text("DELETE FROM player_point_stats WHERE player_id = :player_id AND team_organization_id = :team_id"),
            {"player_id": player_id, "team_id": get_current_team_id()}
        )

        # Delete throws first (both as thrower and receiver)
        db.session.execute(
            text("DELETE FROM throw WHERE (thrower_id = :player_id OR receiver_id = :player_id) AND team_organization_id = :team_id"),
            {"player_id": player_id, "team_id": get_current_team_id()}
        )

        # Delete related records - Updated to use new relationship pattern
        # Remove player from clips (many-to-many relationship)
        player.clips = []  # This will remove the associations without deleting clips
        
        LineUp.query.filter_by(
            player_id=player_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        Event.query.filter_by(
            receiver_id=player_id,
            team_organization_id=get_current_team_id()
        ).update({Event.receiver_id: None})
        
        Event.query.filter_by(
            player_id=player_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        Pull.query.filter_by(
            player_id=player_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        Attendance.query.filter_by(
            player_id=player_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        if hasattr(player, 'session_rsvps'):
            SessionRSVP.query.filter_by(
                player_id=player_id,
                team_organization_id=get_current_team_id()
            ).delete()

        # Delete associated user account if it exists
        if player.user_account and player.user_account.team_organization_id == get_current_team_id():
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
    from sqlalchemy import func, desc
    
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get recent lineups
    recent_lineups = player.lineups.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(desc('id')).limit(10).all()
    
    # Create a list of unique games from these lineups
    unique_games = {}
    recent_games = []
    for lineup in recent_lineups:
        if lineup.point and lineup.point.game:
            game_id = lineup.point.game.id
            if game_id not in unique_games:
                unique_games[game_id] = 1
                recent_games.append(lineup.point.game)
    
    # Calculate games played
    subquery = db.session.query(
        LineUp.point_id
    ).join(
        LineUp.point
    ).filter(
        LineUp.player_id == player_id,
        LineUp.team_organization_id == get_current_team_id()
    ).distinct().subquery()
    
    games_played = db.session.query(func.count()).select_from(subquery).scalar() or 0
    points_played = player.lineups.filter_by(
        team_organization_id=get_current_team_id()
    ).count()
    
    # Pass current date for filtering upcoming sessions
    now = datetime.now().date()
    
    return render_template(
        'team/player_detail.html', 
        player=player, 
        now=now,
        games_played=games_played,
        points_played=points_played,
        recent_games=recent_games
    )



@bp.route('/debug')
@login_required
def debug():
    players = Player.query.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    return render_template('team/debug.html', players=players)

@bp.route('/player/<int:player_id>/update_goals', methods=['POST'])
@login_required
def update_player_goals(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Check permissions - only the player, coaches, or admins can update goals
    if not (current_user.is_admin or current_user.id == player.user_id or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to update goals for this player.', 'danger')
        return redirect(url_for('team.player_detail', player_id=player_id))
    
    try:
        # Update player goals
        player.short_term_goals = request.form.get('short_term_goals')
        player.mid_term_goals = request.form.get('mid_term_goals')
        player.long_term_goals = request.form.get('long_term_goals')
        player.skills_to_develop = request.form.get('skills_to_develop')
        
        # Only admins and coaches can update feedback
        if current_user.is_admin or (hasattr(current_user, 'role') and current_user.role == 'coach'):
            player.coach_feedback = request.form.get('coach_feedback')
        
        db.session.commit()
        flash('Player goals updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating goals: {str(e)}', 'danger')
    
    return redirect(url_for('team.player_detail', player_id=player_id))

@bp.route('/settings/features', methods=['GET', 'POST'])
@login_required
@coach_required
def feature_settings():
    team_id = get_current_team_id()
    team = TeamOrganization.query.get_or_404(team_id)

    # Ensure settings row exists
    if team.settings is None:
        team.settings = TeamSettings(team_id=team.id)
        db.session.add(team.settings)
        db.session.commit()

    settings = team.settings

    if request.method == 'POST':
        settings.stats_enabled = bool(request.form.get('stats_enabled'))
        settings.gameday_enabled = bool(request.form.get('gameday_enabled'))
        settings.playbook_enabled = bool(request.form.get('playbook_enabled'))
        settings.theory_enabled = bool(request.form.get('theory_enabled'))
        settings.drills_enabled = bool(request.form.get('drills_enabled'))
        settings.sessions_enabled = bool(request.form.get('sessions_enabled'))
        settings.clip_enabled = bool(request.form.get('clip_enabled'))
        settings.scouting_enabled = bool(request.form.get('scouting_enabled'))
        settings.fitness_enabled = bool(request.form.get('fitness_enabled'))

        db.session.commit()
        flash('Feature visibility updated.', 'success')
        return redirect(url_for('team.feature_settings'))

    return render_template('team/feature_settings.html', team=team)


# ─────────────────────────────────────────────────────────
# Bulk Player Import
# ─────────────────────────────────────────────────────────

VALID_POSITIONS    = {'handler', 'cutter', 'hybrid'}
VALID_GENDER_MATCH = {'Mixed', "Women's", "Men's"}

def _generate_username(name, team_id):
    """Derive a unique username from a player's name."""
    parts = name.strip().split()
    base = (parts[0] + (parts[-1][0] if len(parts) > 1 else '')).lower()
    base = re.sub(r'[^a-z0-9]', '', base) or 'player'
    username = base
    counter = 1
    while User.query.filter_by(username=username).first():
        username = f"{base}{counter}"
        counter += 1
    return username


def _temp_password(length=10):
    """Generate a readable temporary password (no ambiguous chars)."""
    chars = 'abcdefghjkmnpqrstuvwxyz23456789'
    return ''.join(random.choices(chars, k=length))


@bp.route('/bulk-import', methods=['GET', 'POST'])
@coach_required
def bulk_import():
    """Paste or upload a CSV of players; optionally auto-create user accounts.

    CSV columns (header row optional):
        name, jersey_number, position, email, gender_match, line_preference
    Only 'name' is required; all other columns are optional.
    """
    team_id = get_current_team_id()

    if request.method == 'POST':
        raw = request.form.get('csv_data', '').strip()
        create_accounts = 'create_accounts' in request.form

        if not raw:
            flash('No data provided — please paste your CSV above.', 'warning')
            return redirect(url_for('team.bulk_import'))

        lines = [l.strip() for l in raw.splitlines() if l.strip()]

        # Skip header row if present
        if lines and lines[0].lower().lstrip('\ufeff').startswith('name'):
            lines = lines[1:]

        results = []   # dicts with keys: name, status, note, credentials
        errors  = []

        for line_no, line in enumerate(lines, 1):
            # Support comma or tab separated
            parts = [p.strip().strip('"') for p in re.split(r'[,\t]', line)]
            name = parts[0] if parts else ''
            if not name:
                errors.append(f"Row {line_no}: empty name, skipped.")
                continue

            # Parse optional fields with sensible defaults/validation
            try:
                jersey = int(parts[1]) if len(parts) > 1 and parts[1] else None
            except ValueError:
                jersey = None

            position = parts[2].lower() if len(parts) > 2 and parts[2].lower() in VALID_POSITIONS else None
            email    = parts[3] if len(parts) > 3 and parts[3] else None
            gm_raw   = parts[4] if len(parts) > 4 else ''
            gender_match = gm_raw if gm_raw in VALID_GENDER_MATCH else 'Mixed'

            # Check for duplicate name within team
            existing = Player.query.filter_by(name=name, team_organization_id=team_id).first()
            if existing:
                errors.append(f"Row {line_no}: '{name}' already exists in roster, skipped.")
                continue

            try:
                player = Player(
                    name=name,
                    jersey_number=jersey,
                    position=position,
                    email=email,
                    gender_match=gender_match,
                    active=True,
                    team_organization_id=team_id,
                )
                db.session.add(player)
                db.session.flush()   # get player.id before creating user

                credentials = None
                if create_accounts:
                    if not email:
                        note = 'No email — account not created'
                    elif User.query.filter_by(email=email).first():
                        note = 'Email already in use — account not created'
                    else:
                        username = _generate_username(name, team_id)
                        temp_pw  = _temp_password()
                        user = User(
                            username=username,
                            email=email,
                            role='player',
                            is_superadmin=False,
                            team_organization_id=team_id,
                        )
                        user.set_password(temp_pw)
                        db.session.add(user)
                        db.session.flush()
                        player.user_id = user.id
                        credentials = {'username': username, 'password': temp_pw}
                        note = 'Player + account created'
                else:
                    note = 'Player created'

                db.session.commit()
                results.append({
                    'name': name,
                    'jersey': jersey,
                    'email': email or '—',
                    'note': note,
                    'credentials': credentials,
                })

            except Exception as e:
                db.session.rollback()
                errors.append(f"Row {line_no} ('{name}'): {e}")

        return render_template(
            'team/bulk_import_results.html',
            results=results,
            errors=errors,
            create_accounts=create_accounts,
        )

    return render_template('team/bulk_import.html')
