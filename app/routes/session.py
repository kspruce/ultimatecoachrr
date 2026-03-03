from flask import (
    Blueprint, abort, render_template, redirect, url_for, flash, 
    request, jsonify, current_app, render_template_string, session
)
from flask_login import login_required, current_user
from app import db
from app.models.session import SessionPlan, SessionComponent, SavedDrill, Attendance, SessionRSVP
from app.models.player import Player
from app.forms.session import (
    SessionRSVPForm, SessionPlanForm, DrillForm, 
    SessionComponentForm, AttendanceForm, SessionFilterForm
)
from datetime import datetime, timedelta
import json
import os
import uuid
from app.utils.utils import save_uploaded_file, delete_file
from werkzeug.utils import secure_filename
from PIL import Image
from io import BytesIO
import base64
from flask_wtf.csrf import CSRFProtect
from app.utils.s3_utils import upload_file_to_s3, delete_file_from_s3
from app.utils.storage import store_file
from app.utils.utils import admin_required, coach_required, stat_taker_required
from app.forms.session import (
    SessionRSVPForm, SessionPlanForm, DrillForm, 
    SessionComponentForm, AttendanceForm, SessionFilterForm, AdminSessionRSVPForm  # Add AdminSessionRSVPForm
)

csrf = CSRFProtect()

bp = Blueprint('session', __name__, url_prefix='/sessions')

# Helper function to get current team ID
def get_current_team_id():
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

# Existing Session Routes
@bp.route('/')
@login_required
def index():
    form = SessionFilterForm()
    
    # Get filter parameters
    focus_area = request.args.get('focus_area', '')
    date_range = request.args.get('date_range', 'all')
    session_type = request.args.get('session_type', '')
    
    # Set form values from query parameters
    if focus_area:
        form.focus_area.data = focus_area
    if date_range:
        form.date_range.data = date_range
    if session_type:
        form.session_type.data = session_type
    
    # Build query based on filters
    query = SessionPlan.query.filter_by(team_organization_id=get_current_team_id())
    
    if focus_area:
        query = query.filter(SessionPlan.focus_area == focus_area)
    
    if session_type:
        query = query.filter(SessionPlan.session_type == session_type)
    
    if date_range != 'all':
        today = datetime.now().date()
        if date_range == 'past_week':
            start_date = today - timedelta(days=7)
        elif date_range == 'past_month':
            start_date = today - timedelta(days=30)
        elif date_range == 'past_year':
            start_date = today - timedelta(days=365)
        
        query = query.filter(SessionPlan.date >= start_date)
    
    # Get sessions and sort by date (newest first)
    sessions = query.order_by(SessionPlan.date.desc()).all()
    
    # Get upcoming sessions (future dates)
    upcoming_sessions = SessionPlan.query.filter(
        SessionPlan.date >= datetime.now().date(),
        SessionPlan.team_organization_id == get_current_team_id()
    ).order_by(SessionPlan.date).limit(5).all()
    
    return render_template(
        'session/index.html',
        sessions=sessions,
        upcoming_sessions=upcoming_sessions,
        form=form
    )

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add_session():
    form = SessionPlanForm()
    
    if form.validate_on_submit():
        # Find the highest existing session ID and add 1
        highest_id = db.session.query(db.func.max(SessionPlan.id)).scalar() or 0
        next_id = highest_id + 1
        
        session_plan = SessionPlan(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            title=form.title.data,
            date=form.date.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            location=form.location.data,
            focus_area=form.focus_area.data,
            notes=form.notes.data,
            is_recurring=form.is_recurring.data,
            recurrence_pattern=form.recurrence_pattern.data if form.is_recurring.data else None,
            session_type=form.session_type.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        db.session.add(session_plan)
        db.session.commit()
        
        flash(f'Session plan "{session_plan.title}" has been created!', 'success')
        return redirect(url_for('session.detail', session_id=session_plan.id))
    
    return render_template('session/session_form.html', form=form, title='Add Session Plan')

# Drill Library Routes
@bp.route('/drills')
@login_required
def drills():
    """Display all drills in the library"""
    drills = SavedDrill.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SavedDrill.title).all()
    
    return render_template('session/drills/list.html', drills=drills)

@bp.route('/drills/add', methods=['GET', 'POST'])
@bp.route('/drills/add/<string:drill_type>', methods=['GET', 'POST'])
@login_required
@coach_required
def add_drill(drill_type='basic'):
    form = DrillForm()

    if form.validate_on_submit():
        # Find the highest existing drill ID and add 1
        highest_id = db.session.query(db.func.max(SavedDrill.id)).scalar() or 0
        next_id = highest_id + 1
        
        drill = SavedDrill(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            title=form.title.data,
            description=form.description.data,
            setup_instructions=form.setup_instructions.data,
            recommended_duration=form.recommended_duration.data,
            min_players=form.min_players.data,
            max_players=form.max_players.data,
            skill_level=form.skill_level.data,
            focus_area=form.focus_area.data,
            equipment_needed=form.equipment_needed.data,
            ultiplay_embed=form.ultiplay_embed.data,
            created_by=current_user.id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )

        db.session.add(drill)
        db.session.commit()

        flash(f'Drill "{drill.title}" has been created!', 'success')
        return redirect(url_for('session.drills'))

    return render_template('session/drills/form.html', form=form)

@bp.route('/drills/editor')
@bp.route('/drills/editor/<int:drill_id>')
@login_required
def drill_editor(drill_id=None):
    """Render the drill editor page"""
    drill = None
    if drill_id:
        drill = SavedDrill.query.filter_by(
            id=drill_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Ensure user has permission to edit this drill
        if drill.created_by != current_user.id and not current_user.is_admin:
            abort(403)
    
    return render_template('session/drills/editor.html', drill=drill, hide_container=True)

@bp.route('/drills/view/<int:drill_id>')
@login_required
def drill_viewer(drill_id):
    """View a drill"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    return render_template('session/drills/viewer.html', drill=drill)

@bp.route('/drills/<int:drill_id>')
@login_required
def drill_detail(drill_id):
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Find the session ID associated with this drill (if any)
    session_component = SessionComponent.query.filter_by(
        drill_id=drill_id,
        team_organization_id=get_current_team_id()
    ).first()
    
    session_id = session_component.session_id if session_component else None

    return render_template('session/drills/detail.html', drill=drill, session_id=session_id)
    
# Drill API Routes
@bp.route('/api/drills', methods=['POST'])
@login_required
@coach_required
def create_drill():
    """Create a new drill via API"""
    try:
        data = request.get_json()
        
        # Find the highest existing drill ID and add 1
        highest_id = db.session.query(db.func.max(SavedDrill.id)).scalar() or 0
        next_id = highest_id + 1
        
        drill = SavedDrill(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            title=data.get('title', 'Untitled Drill'),
            description=data.get('description', ''),
            setup_instructions=data.get('setup_instructions', ''),
            recommended_duration=data.get('recommended_duration'),
            min_players=data.get('min_players'),
            max_players=data.get('max_players'),
            skill_level=data.get('skill_level'),
            focus_area=data.get('focus_area'),
            equipment_needed=data.get('equipment_needed'),
            ultiplay_embed=data.get('ultiplay_embed'),
            is_public=data.get('is_public', False),
            created_by=current_user.id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )

        db.session.add(drill)
        db.session.commit()

        return jsonify({
            'success': True,
            'drill_id': drill.id,
            'message': 'Drill created successfully'
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating drill: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to create drill'
        }), 500

@bp.route('/api/drills/<int:drill_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_drill(drill_id):
    # Add error handling for authentication
    if not current_user.is_authenticated:
        return jsonify({
            'success': False,
            'message': 'Authentication required'
        }), 401

    try:
        drill = SavedDrill.query.filter_by(
            id=drill_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Check permissions
        if drill.created_by != current_user.id and not current_user.is_admin:
            return jsonify({
                'success': False,
                'message': 'Permission denied'
            }), 403

        if request.method == 'DELETE':
            try:
                # Delete associated diagram if it exists
                if drill.diagram_url:
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], drill.diagram_url)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        current_app.logger.info(f"Deleted file: {file_path}")

                # Delete associated components
                components_deleted = SessionComponent.query.filter_by(
                    drill_id=drill.id,
                    team_organization_id=get_current_team_id()
                ).delete()
                
                current_app.logger.info(f"Deleted {components_deleted} components")

                # Delete the drill
                title = drill.title
                db.session.delete(drill)
                db.session.commit()

                current_app.logger.info(f"Successfully deleted drill: {title}")
                return jsonify({
                    'success': True,
                    'message': f'Drill "{title}" has been deleted successfully'
                })

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting drill: {str(e)}")
                return jsonify({
                    'success': False,
                    'message': f'Error deleting drill: {str(e)}'
                }), 500

    except Exception as e:
        current_app.logger.error(f"Error in manage_drill: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500



# Session Component Routes
@bp.route('/<int:session_id>/components')
@login_required
def components(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    return render_template('session/components.html', session=session_plan, components=components)

@bp.route('/<int:session_id>/add_component', methods=['GET', 'POST'])
@login_required
@coach_required
def add_component(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionComponentForm()
    
    # Populate drill choices - only from current team
    form.drill_id.choices = [(0, 'None')] + [(d.id, d.title) for d in SavedDrill.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SavedDrill.title).all()]
    
    # Set default order to next available
    next_order = 1
    last_component = SessionComponent.query.filter_by(
        session_id=session_id,
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order.desc()).first()
    
    if last_component:
        next_order = last_component.order + 1
    form.order.data = next_order
    
    if form.validate_on_submit():
        # Find the highest existing component ID and add 1
        highest_id = db.session.query(db.func.max(SessionComponent.id)).scalar() or 0
        next_id = highest_id + 1
        
        component = SessionComponent(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            session_id=session_id,
            title=form.title.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            order=form.order.data,
            component_type=form.component_type.data,
            focus_area=form.focus_area.data,
            notes=form.notes.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        # If a saved drill was selected, associate it and copy its details
        if form.drill_id.data and form.drill_id.data > 0:
            drill = SavedDrill.query.filter_by(
                id=form.drill_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            
            if drill:
                component.drill_id = drill.id
                if not form.description.data:
                    component.description = drill.description
                if not form.duration_minutes.data and drill.recommended_duration:
                    component.duration_minutes = drill.recommended_duration
                if not form.focus_area.data:
                    component.focus_area = drill.focus_area
        
        db.session.add(component)
        db.session.commit()
        
        flash(f'Component "{component.title}" has been added!', 'success')
        return redirect(url_for('session.components', session_id=session_id))
    
    return render_template('session/component_form.html', form=form, session=session_plan, title='Add Session Component')

@bp.route('/edit_component/<int:component_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_component(component_id):
    component = SessionComponent.query.filter_by(
        id=component_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    session_plan = SessionPlan.query.filter_by(
        id=component.session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionComponentForm(obj=component)
    
    # Populate drill choices - only from current team
    form.drill_id.choices = [(0, 'None')] + [(d.id, d.title) for d in SavedDrill.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SavedDrill.title).all()]
    
    if form.validate_on_submit():
        component.title = form.title.data
        component.description = form.description.data
        component.duration_minutes = form.duration_minutes.data
        component.order = form.order.data
        component.component_type = form.component_type.data
        component.focus_area = form.focus_area.data
        component.notes = form.notes.data
        
        # Update drill association
        if form.drill_id.data and form.drill_id.data > 0:
            # Verify drill belongs to current team
            drill = SavedDrill.query.filter_by(
                id=form.drill_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            
            if drill:
                component.drill_id = drill.id
            else:
                component.drill_id = None
        else:
            component.drill_id = None
        
        db.session.commit()
        
        flash(f'Component "{component.title}" has been updated!', 'success')
        return redirect(url_for('session.components', session_id=component.session_id))
    
    return render_template('session/component_form.html', form=form, component=component, session=session_plan, title='Edit Session Component')

@bp.route('/delete_component/<int:component_id>', methods=['POST'])
@login_required
@coach_required
def delete_component(component_id):
    component = SessionComponent.query.filter_by(
        id=component_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    session_id = component.session_id
    title = component.title
    
    db.session.delete(component)
    db.session.commit()
    
    flash(f'Component "{title}" has been deleted!', 'success')
    return redirect(url_for('session.components', session_id=session_id))

# Attendance Routes
@bp.route('/<int:session_id>/attendance', methods=['GET', 'POST'])
@login_required
@coach_required
def attendance(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = AttendanceForm(team_organization_id=get_current_team_id())  # ADD team_organization_id here
    
    if form.validate_on_submit():
        # Get the selected status
        status = form.status.data
        
        # Delete existing attendance records for the selected players
        for player_id in form.players.data:
            Attendance.query.filter_by(
                session_id=session_id, 
                player_id=player_id,
                team_organization_id=get_current_team_id()
            ).delete()
        
        # Create new attendance records for the selected players
        for player_id in form.players.data:
            # Verify player belongs to current team
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=get_current_team_id()
            ).first()
            
            if player:
                # Find the highest existing attendance ID and add 1
                highest_id = db.session.query(db.func.max(Attendance.id)).scalar() or 0
                next_id = highest_id + 1
                
                attendance = Attendance(
                    id=next_id,  # Explicitly set the ID to avoid conflicts
                    session_id=session_id,
                    player_id=player_id,
                    status=status,
                    notes=form.notes.data,
                    team_organization_id=get_current_team_id()  # Add team organization ID
                )
                db.session.add(attendance)
        
        db.session.commit()
        
        flash(f'Attendance for {len(form.players.data)} players has been recorded as {status}!', 'success')
        return redirect(url_for('session.attendance', session_id=session_id))
    
    # Pre-select players based on the selected status in the form
    if request.method == 'GET':
        status = request.args.get('status', 'present')
        form.status.data = status
        
        # Get players with the selected status
        attendances = Attendance.query.filter_by(
            session_id=session_id, 
            status=status,
            team_organization_id=get_current_team_id()
        ).all()
        
        form.players.data = [a.player_id for a in attendances]
    
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).order_by(Player.name).all()
    
    attendances = Attendance.query.filter_by(
        session_id=session_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)
    
    return render_template(
        'session/attendance.html', 
        session=session_plan, 
        form=form, 
        players=players, 
        attendances=attendances,
        attendance_by_status=attendance_by_status
    )

# RSVP Routes
@bp.route('/<int:session_id>/rsvp', methods=['GET', 'POST'])
@bp.route('/<int:session_id>/rsvp/<int:player_id>', methods=['GET', 'POST'])
@login_required
def rsvp(session_id, player_id=None):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Determine if admin is RSVPing on behalf of a player
    is_admin_rsvp = current_user.is_admin and player_id is not None
    
    if is_admin_rsvp:
        # Admin RSVPing for a specific player
        player = Player.query.filter_by(
            id=player_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        existing_rsvp = SessionRSVP.query.filter_by(
            session_id=session_id,
            player_id=player.id,
            team_organization_id=get_current_team_id()
        ).first()
        
        form = SessionRSVPForm(obj=existing_rsvp)
        
        if form.validate_on_submit():
            if existing_rsvp:
                existing_rsvp.status = form.status.data
                existing_rsvp.notes = form.notes.data
                flash(f'RSVP for {player.name} has been updated!', 'success')
            else:
                rsvp = SessionRSP(
                    session_id=session_id,
                    player_id=player.id,
                    status=form.status.data,
                    notes=form.notes.data,
                    team_organization_id=get_current_team_id()
                )
                db.session.add(rsvp)
                flash(f'RSVP for {player.name} has been submitted!', 'success')
            
            db.session.commit()
            return redirect(url_for('session.rsvps', session_id=session_id))
        
        return render_template('session/rsvp.html', form=form, session=session_plan, 
                             existing_rsvp=existing_rsvp, player=player, is_admin=True)
    
    elif current_user.is_admin:
        # Admin selecting which player to RSVP for
        form = AdminSessionRSVPForm(team_organization_id=get_current_team_id())
        
        if form.validate_on_submit():
            selected_player_id = form.player_id.data
            player = Player.query.filter_by(
                id=selected_player_id,
                team_organization_id=get_current_team_id()
            ).first_or_404()
            
            existing_rsvp = SessionRSVP.query.filter_by(
                session_id=session_id,
                player_id=player.id,
                team_organization_id=get_current_team_id()
            ).first()
            
            if existing_rsvp:
                existing_rsvp.status = form.status.data
                existing_rsvp.notes = form.notes.data
                flash(f'RSVP for {player.name} has been updated!', 'success')
            else:
                rsvp = SessionRSVP(
                    session_id=session_id,
                    player_id=player.id,
                    status=form.status.data,
                    notes=form.notes.data,
                    team_organization_id=get_current_team_id()
                )
                db.session.add(rsvp)
                flash(f'RSVP for {player.name} has been submitted!', 'success')
            
            db.session.commit()
            return redirect(url_for('session.rsvps', session_id=session_id))
        
        return render_template('session/rsvp.html', form=form, session=session_plan, is_admin=True)
    
    else:
        # Regular player RSVPing for themselves
        if not current_user.player:
            flash('You need to link your account to a player before you can RSVP.', 'warning')
            return redirect(url_for('auth.link_player'))
        
        player = current_user.player
        
        existing_rsvp = SessionRSVP.query.filter_by(
            session_id=session_id, 
            player_id=player.id,
            team_organization_id=get_current_team_id()
        ).first()
        
        form = SessionRSVPForm(obj=existing_rsvp)
        
        if form.validate_on_submit():
            if existing_rsvp:
                existing_rsvp.status = form.status.data
                existing_rsvp.notes = form.notes.data
                flash('Your RSVP has been updated!', 'success')
            else:
                rsvp = SessionRSVP(
                    session_id=session_id,
                    player_id=player.id,
                    status=form.status.data,
                    notes=form.notes.data,
                    team_organization_id=get_current_team_id()
                )
                db.session.add(rsvp)
                flash('Your RSVP has been submitted!', 'success')
            
            db.session.commit()
            return redirect(url_for('session.detail', session_id=session_id))
        
        return render_template('session/rsvp.html', form=form, session=session_plan, 
                             existing_rsvp=existing_rsvp, is_admin=False)
@bp.route('/<int:session_id>/rsvps')
@login_required
def rsvps(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Group RSVPs by status
    attending = SessionRSVP.query.filter_by(
        session_id=session_id, 
        status='attending',
        team_organization_id=get_current_team_id()
    ).all()
    
    not_attending = SessionRSVP.query.filter_by(
        session_id=session_id, 
        status='not_attending',
        team_organization_id=get_current_team_id()
    ).all()
    
    maybe = SessionRSVP.query.filter_by(
        session_id=session_id, 
        status='maybe',
        team_organization_id=get_current_team_id()
    ).all()
    
    return render_template(
        'session/rsvps.html', 
        session=session_plan, 
        attending=attending, 
        not_attending=not_attending, 
        maybe=maybe
    )

# Analytics Routes
@bp.route('/attendance_analytics')
@login_required
def attendance_analytics():
    # Get all sessions with dates, ordered by date
    sessions = SessionPlan.query.filter(
        SessionPlan.date != None,
        SessionPlan.team_organization_id == get_current_team_id()
    ).order_by(SessionPlan.date).all()
    
    # Get all active players
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).order_by(Player.name).all()
    
    # Get selected player for individual trend
    selected_player_id = request.args.get('player_id', type=int)
    selected_player = None
    
    if selected_player_id:
        selected_player = Player.query.filter_by(
            id=selected_player_id,
            team_organization_id=get_current_team_id()
        ).first()
    
    # Calculate attendance statistics for each player
    player_stats = []
    for player in players:
        # Get attendance records for this player
        attendances = Attendance.query.filter_by(
            player_id=player.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        # Count attendance by status
        present_count = sum(1 for a in attendances if a.status == 'present')
        late_count = sum(1 for a in attendances if a.status == 'late')
        absent_count = sum(1 for a in attendances if a.status == 'absent')
        excused_count = sum(1 for a in attendances if a.status == 'excused')
        
        # Calculate attendance rate
        total_sessions = len(sessions)
        attended_sessions = present_count + late_count
        attendance_rate = (attended_sessions / total_sessions * 100) if total_sessions > 0 else 0
        
        player_stats.append({
            'player': player,
            'present': present_count,
            'late': late_count,
            'absent': absent_count,
            'excused': excused_count,
            'total_attended': attended_sessions,
            'attendance_rate': attendance_rate
        })
    
    # Sort player stats by attendance rate (descending)
    player_stats.sort(key=lambda x: x['attendance_rate'], reverse=True)
    
    # Calculate overall attendance statistics
    total_attendances = sum(p['total_attended'] for p in player_stats)
    total_possible = len(players) * len(sessions)
    overall_attendance_rate = (total_attendances / total_possible * 100) if total_possible > 0 else 0
    
    # Generate attendance trend data
    trend_data = []
    
    if selected_player:
        # Individual player trend
        attendance_by_session = {}
        attendances = Attendance.query.filter_by(
            player_id=selected_player.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        for attendance in attendances:
            attendance_by_session[attendance.session_id] = attendance
        
        for session_plan in sessions:
            attendance = attendance_by_session.get(session_plan.id)
            status_value = 0  # Default: absent/unknown
            
            if attendance:
                if attendance.status == 'present':
                    status_value = 1
                elif attendance.status == 'late':
                    status_value = 0.5
                elif attendance.status == 'excused':
                    status_value = 0.25
            
            trend_data.append({
                'date': session_plan.date.strftime('%Y-%m-%d'),
                'title': session_plan.title,
                'status': attendance.status if attendance else 'unknown',
                'value': status_value
            })
    else:
        # Team trend
        for session_plan in sessions:
            present_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='present',
                team_organization_id=get_current_team_id()
            ).count()
            
            late_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='late',
                team_organization_id=get_current_team_id()
            ).count()
            
            absent_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='absent',
                team_organization_id=get_current_team_id()
            ).count()
            
            excused_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='excused',
                team_organization_id=get_current_team_id()
            ).count()
            
            trend_data.append({
                'date': session_plan.date.strftime('%Y-%m-%d'),
                'title': session_plan.title,
                'present': present_count,
                'late': late_count,
                'absent': absent_count,
                'excused': excused_count
            })
    
    return render_template(
        'session/attendance_analytics.html',
        sessions=sessions,
        players=players,
        player_stats=player_stats,
        overall_attendance_rate=overall_attendance_rate,
        trend_data=json.dumps(trend_data),
        selected_player=selected_player
    )

@bp.route('/player_attendance/<int:player_id>')
@login_required
def player_attendance(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get all sessions with dates
    sessions = SessionPlan.query.filter(
        SessionPlan.date != None,
        SessionPlan.team_organization_id == get_current_team_id()
    ).order_by(SessionPlan.date).all()
    
    # Get attendance records for this player
    attendances = Attendance.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary of attendance records by session ID
    attendance_by_session = {a.session_id: a for a in attendances}
    
    # Calculate attendance statistics
    present_count = sum(1 for a in attendances if a.status == 'present')
    late_count = sum(1 for a in attendances if a.status == 'late')
    absent_count = sum(1 for a in attendances if a.status == 'absent')
    excused_count = sum(1 for a in attendances if a.status == 'excused')
    
    total_sessions = len(sessions)
    attended_sessions = present_count + late_count
    attendance_rate = (attended_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Generate attendance trend data for chart
    trend_data = []
    for session_plan in sessions:
        attendance = attendance_by_session.get(session_plan.id)
        status = attendance.status if attendance else 'unknown'
        
        trend_data.append({
            'date': session_plan.date.strftime('%Y-%m-%d'),
            'title': session_plan.title,
            'status': status
        })
    
    # NEW CODE: Get tournament attendance data
    from app.models.tournament import Tournament
    from app.models.tournament_rsvp import TournamentRSVP
    from app.models.game import Game
    from app.models.game_player import GamePlayer
    
    # Get tournaments where the player was selected
    tournament_rsvps = TournamentRSVP.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary of tournament data
    tournament_data = {}
    
    for rsvp in tournament_rsvps:
        tournament = Tournament.query.filter_by(
            id=rsvp.tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if tournament:
            # Get games where player was assigned
            games = db.session.query(Game).join(
                GamePlayer, Game.id == GamePlayer.game_id
            ).filter(
                Game.tournament_id == tournament.id,
                GamePlayer.player_id == player_id,
                Game.team_organization_id == get_current_team_id(),
                GamePlayer.team_organization_id == get_current_team_id()
            ).all()
            
            tournament_data[tournament.id] = {
                'tournament': tournament,
                'rsvp': rsvp,
                'games': games
            }
    
    # Calculate tournament attendance statistics
    total_tournaments = len(tournament_data)
    tournaments_attending = sum(1 for t in tournament_data.values() if t['rsvp'].status == 'attending')
    tournaments_selected = sum(1 for t in tournament_data.values() if t['rsvp'].selected_by_admin)
    total_games = sum(len(t['games']) for t in tournament_data.values())
    
    return render_template(
        'session/player_attendance.html',
        player=player,
        sessions=sessions,
        attendance_by_session=attendance_by_session,
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        excused_count=excused_count,
        attendance_rate=attendance_rate,
        trend_data=json.dumps(trend_data),
        # Add tournament data to template context
        tournament_data=tournament_data,
        total_tournaments=total_tournaments,
        tournaments_attending=tournaments_attending,
        tournaments_selected=tournaments_selected,
        total_games=total_games
    )



# API Helper Functions
def get_csrf_token():
    """Get CSRF token from meta tag"""
    return render_template_string(
        '<meta name="csrf-token" content="{{ csrf_token() }}">'
    ).split('content="')[1].split('"')[0]

def validate_drill_data(data):
    """Validate drill data before saving"""
    required_fields = ['title']
    for field in required_fields:
        if field not in data or not data[field]:
            return False, f'Missing required field: {field}'
    return True, None

def clean_drill_elements(elements):
    """Clean and validate drill elements before saving"""
    valid_types = ['player', 'disc', 'cone', 'text', 'path']
    return [el for el in elements if el.get('type') in valid_types]

# Additional API Routes for Drill Management
@bp.route('/api/drills/search')
@login_required
def search_drills():
    """Search drills based on criteria"""
    query = request.args.get('q', '')
    skill_level = request.args.get('skill_level', '')
    focus_area = request.args.get('focus_area', '')
    
    drills = SavedDrill.query.filter_by(team_organization_id=get_current_team_id())
    
    if query:
        drills = drills.filter(
            db.or_(
                SavedDrill.title.ilike(f'%{query}%'),
                SavedDrill.description.ilike(f'%{query}%')
            )
        )
    
    if skill_level:
        drills = drills.filter(SavedDrill.skill_level == skill_level)
    
    if focus_area:
        drills = drills.filter(SavedDrill.focus_area == focus_area)
    
    drills = drills.order_by(SavedDrill.title).all()
    
    return jsonify([{
        'id': drill.id,
        'title': drill.title,
        'description': drill.description,
        'skill_level': drill.skill_level,
        'focus_area': drill.focus_area,
        'diagram_url': drill.diagram_url
    } for drill in drills])

@bp.route('/api/drills/duplicate/<int:drill_id>', methods=['POST'])
@login_required
@coach_required
def duplicate_drill(drill_id):
    """Create a copy of an existing drill"""
    original_drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Find the highest existing drill ID and add 1
    highest_id = db.session.query(db.func.max(SavedDrill.id)).scalar() or 0
    next_id = highest_id + 1
    
    # Create new drill with copied data
    new_drill = SavedDrill(
        id=next_id,  # Explicitly set the ID to avoid conflicts
        title=f"Copy of {original_drill.title}",
        description=original_drill.description,
        setup_instructions=original_drill.setup_instructions,
        recommended_duration=original_drill.recommended_duration,
        min_players=original_drill.min_players,
        max_players=original_drill.max_players,
        skill_level=original_drill.skill_level,
        focus_area=original_drill.focus_area,
        equipment_needed=original_drill.equipment_needed,
        created_by=current_user.id,
        elements=original_drill.elements,
        team_organization_id=get_current_team_id()  # Add team organization ID
    )
    
    db.session.add(new_drill)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'drill_id': new_drill.id,
        'message': 'Drill duplicated successfully'
    })

@bp.route('/<int:session_id>/detail')
@login_required
def detail(session_id):
    """Show session details"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    attendances = session_plan.attendances.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)
    
    return render_template(
        'session/detail.html',
        session=session_plan,
        components=components,
        attendance_by_status=attendance_by_status
    )

@bp.route('/edit/<int:session_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_session(session_id):
    """Edit an existing session"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionPlanForm(obj=session_plan)
    
    if form.validate_on_submit():
        session_plan.title = form.title.data
        session_plan.date = form.date.data
        session_plan.start_time = form.start_time.data
        session_plan.end_time = form.end_time.data
        session_plan.location = form.location.data
        session_plan.focus_area = form.focus_area.data
        session_plan.notes = form.notes.data
        session_plan.is_recurring = form.is_recurring.data
        session_plan.recurrence_pattern = form.recurrence_pattern.data if form.is_recurring.data else None
        session_plan.session_type = form.session_type.data
        
        db.session.commit()
        
        flash(f'Session plan "{session_plan.title}" has been updated!', 'success')
        return redirect(url_for('session.detail', session_id=session_plan.id))
    
    return render_template(
        'session/session_form.html',
        form=form,
        session=session_plan,
        title='Edit Session Plan'
    )

@bp.route('/delete/<int:session_id>', methods=['POST'])
@login_required
@coach_required
def delete_session(session_id):
    try:
        # Log the request
        current_app.logger.info(f"Delete request received for session {session_id}")
        
        session_plan = SessionPlan.query.filter_by(
            id=session_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Check if user has permission (optional)
        if not current_user.is_admin:
            current_app.logger.warning(f"User {current_user.id} attempted to delete session {session_id} without permission")
            flash('Permission denied', 'danger')
            return redirect(url_for('session.index'))

        title = session_plan.title

        # Delete associated records first
        SessionComponent.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        Attendance.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        SessionRSVP.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()

        # Delete the session
        db.session.delete(session_plan)
        db.session.commit()

        current_app.logger.info(f"Successfully deleted session {session_id}")
        
        flash(f'Session "{title}" has been deleted!', 'success')
        return redirect(url_for('session.index'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting session {session_id}: {str(e)}")
        flash(f'Error deleting session: {str(e)}', 'danger')
        return redirect(url_for('session.index'))



@bp.route('/drills/edit/<int:drill_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_drill(drill_id):
    """Edit an existing drill"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = DrillForm(obj=drill)
    
    if form.validate_on_submit():
        drill.title = form.title.data
        drill.description = form.description.data
        drill.setup_instructions = form.setup_instructions.data
        drill.recommended_duration = form.recommended_duration.data
        drill.min_players = form.min_players.data
        drill.max_players = form.max_players.data
        drill.skill_level = form.skill_level.data
        drill.focus_area = form.focus_area.data
        drill.equipment_needed = form.equipment_needed.data
        drill.ultiplay_embed = form.ultiplay_embed.data
        drill.is_public = form.is_public.data if hasattr(form, 'is_public') else False
        
        db.session.commit()
        flash(f'Drill "{drill.title}" has been updated!', 'success')
        return redirect(url_for('session.drills'))
    
    return render_template(
        'session/drills/form.html',
        form=form,
        drill=drill,
        title='Edit Drill'
    )


@bp.route('/drills/delete/<int:drill_id>', methods=['POST'])
@login_required
@coach_required
def delete_drill(drill_id):
    """Delete a drill (form-based deletion)"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    if drill.created_by != current_user.id and not current_user.is_admin:
        abort(403)

    try:
        # Delete associated components
        SessionComponent.query.filter_by(
            drill_id=drill.id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        title = drill.title
        db.session.delete(drill)
        db.session.commit()
        
        flash(f'Drill "{title}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting drill: {str(e)}")
        flash('An error occurred while deleting the drill.', 'danger')

    return redirect(url_for('session.drills'))
    
@bp.errorhandler(401)
def unauthorized_error(error):
    return jsonify({
        'success': False,
        'message': 'Authentication required'
    }), 401

@bp.errorhandler(403)
def forbidden_error(error):
    return jsonify({
        'success': False,
        'message': 'Permission denied'
    }), 403

@bp.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'success': False,
        'message': 'Resource not found'
    }), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500


def verify_file_paths():
    """Utility function to verify file paths and permissions"""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    
    # Check if directory exists
    if not os.path.exists(upload_folder):
        try:
            os.makedirs(upload_folder)
            print(f"Created upload directory: {upload_folder}")
        except Exception as e:
            print(f"Error creating upload directory: {e}")
            return False
    
    # Check if directory is writable
    if not os.access(upload_folder, os.W_OK):
        print(f"Upload directory is not writable: {upload_folder}")
        return False
    
    # Check if directory is readable
    if not os.access(upload_folder, os.R_OK):
        print(f"Upload directory is not readable: {upload_folder}")
        return False
        
    return True

# Add this to your route to debug file paths
@bp.route('/debug/files')
@login_required
def debug_files():
    """Debug endpoint to check file paths and permissions"""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    static_folder = current_app.static_folder
    
    # Get all drills with diagrams
    drills_with_diagrams = SavedDrill.query.filter(
        SavedDrill.diagram_url.isnot(None),
        SavedDrill.team_organization_id == get_current_team_id()
    ).all()
    
    debug_info = {
        'upload_folder': upload_folder,
        'upload_folder_exists': os.path.exists(upload_folder),
        'upload_folder_writable': os.access(upload_folder, os.W_OK),
        'static_folder': static_folder,
        'static_folder_exists': os.path.exists(static_folder),
        'drills_with_diagrams': [
            {
                'id': drill.id,
                'title': drill.title,
                'diagram_url': drill.diagram_url,
                'file_exists': os.path.exists(os.path.join(upload_folder, drill.diagram_url)) if drill.diagram_url else False
            }
            for drill in drills_with_diagrams
        ]
    }
    
    return jsonify(debug_info)

@bp.before_request
def before_request():
    """Log request information"""
    if 'static' in request.path:
        current_app.logger.debug(f"Static file request: {request.path}")

@bp.route('/<int:session_id>/export_pdf')
@login_required
def export_pdf(session_id):
    """Export session plan as PDF"""
    try:
        import pdfkit
        from flask import make_response
        
        session_plan = SessionPlan.query.filter_by(
            id=session_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        components = session_plan.components.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(SessionComponent.order).all()
        
        attendances = session_plan.attendances.filter_by(
            team_organization_id=get_current_team_id()
        ).all()
        
        # Group attendances by status
        attendance_by_status = {
            'present': [],
            'absent': [],
            'late': [],
            'excused': []
        }
        
        for attendance in attendances:
            if attendance.status in attendance_by_status:
                attendance_by_status[attendance.status].append(attendance)
        
        # Render the template to HTML
        html = render_template(
            'session/pdf_export.html',
            session=session_plan,
            components=components,
            attendance_by_status=attendance_by_status
        )
        
        # PDF options
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
        }
        
        # Generate PDF from HTML
        try:
            pdf = pdfkit.from_string(html, False, options=options)
        except Exception as e:
            current_app.logger.error(f"PDF generation error: {str(e)}")
            # Fallback to simpler options
            pdf = pdfkit.from_string(html, False)
        
        # Create response with PDF
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=session_{session_id}_{session_plan.title.replace(" ", "_")}.pdf'
        
        return response
        
    except ImportError:
        # If pdfkit is not available, try WeasyPrint
        try:
            from weasyprint import HTML
            
            html = render_template(
                'session/pdf_export.html',
                session=session_plan,
                components=components,
                attendance_by_status=attendance_by_status
            )
            
            pdf = HTML(string=html).write_pdf()
            
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=session_{session_id}_{session_plan.title.replace(" ", "_")}.pdf'
            
            return response
            
        except Exception as e:
            current_app.logger.error(f"PDF generation error: {str(e)}")
            flash(f"Could not generate PDF: {str(e)}", "error")
            return redirect(url_for('session.detail', session_id=session_id))

@bp.route('/<int:session_id>/printable')
@login_required
def printable_view(session_id):
    """Show printable view of session plan"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    attendances = session_plan.attendances.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)
    
    return render_template(
        'session/printable.html',
        session=session_plan,
        components=components,
        attendance_by_status=attendance_by_status
    )

        
