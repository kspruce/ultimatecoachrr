from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user
from app import db
from app.models.session import SessionPlan, SessionRSVP
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.player import Player
from datetime import datetime, timedelta
import json

calendar_bp = Blueprint('calendar', __name__)

@calendar_bp.route('/calendar')
@login_required
def index():
    # Get upcoming sessions
    upcoming_sessions = SessionPlan.query.filter(
        SessionPlan.date >= datetime.now().date()
    ).order_by(SessionPlan.date).all()
    
    # Get upcoming tournaments
    upcoming_tournaments = Tournament.query.filter(
        Tournament.start_date >= datetime.now().date()
    ).order_by(Tournament.start_date).all()
    
    # Create events list for calendar
    events = []
    
    # Add session events
    for session_plan in upcoming_sessions:  # Changed variable name from 'session' to 'session_plan'
        # Check if user has RSVP'd
        rsvp_status = None
        if current_user.player:
            rsvp = SessionRSVP.query.filter_by(
                session_id=session_plan.id,  # Changed from session.id
                player_id=current_user.player.id
            ).first()
            if rsvp:
                rsvp_status = rsvp.status
        
        event = {
            'id': session_plan.id,  # Changed from session.id
            'title': session_plan.title,  # Changed from session.title
            'start': session_plan.date.strftime('%Y-%m-%d'),  # Changed from session.date
            'type': 'session',
            'formatted_date': session_plan.formatted_date,  # Changed from session.formatted_date
            'formatted_time': session_plan.formatted_time,  # Changed from session.formatted_time
            'location': session_plan.location,  # Changed from session.location
            'focus_area': session_plan.focus_area,  # Changed from session.focus_area
            'notes': session_plan.notes,  # Changed from session.notes
            'rsvp_status': rsvp_status,
            # Add these URLs
            'details_url': url_for('session.detail', session_id=session_plan.id),  # Changed from session.id
            'edit_url': url_for('session.edit_session', session_id=session_plan.id),  # Changed from session.id
            'manage_url': url_for('session.rsvps', session_id=session_plan.id)  # Changed from session.id
        }
        events.append(event)
    
    # Add tournament events
    for tournament in upcoming_tournaments:
        # Check if user has RSVP'd
        rsvp_status = None
        selected_by_admin = False
        if current_user.player:
            rsvp = TournamentRSVP.query.filter_by(
                tournament_id=tournament.id,
                player_id=current_user.player.id
            ).first()
            if rsvp:
                rsvp_status = rsvp.status
                selected_by_admin = rsvp.selected_by_admin
        
        # Format date range
        formatted_date = tournament.formatted_date_range
        
        event = {
            'id': tournament.id,
            'title': tournament.name,
            'start': tournament.start_date.strftime('%Y-%m-%d'),
            'end': tournament.end_date.strftime('%Y-%m-%d') if tournament.end_date else None,
            'type': 'tournament',
            'formatted_date': formatted_date,
            'location': tournament.location,
            'notes': '',
            'rsvp_status': rsvp_status,
            'selected_by_admin': selected_by_admin,
            # Add these URLs
            'details_url': url_for('tournament.detail', tournament_id=tournament.id),
            'edit_url': url_for('tournament.edit', tournament_id=tournament.id),
            'manage_url': url_for('tournament.rsvps', tournament_id=tournament.id)
        }
        events.append(event)
    
    return render_template('calendar/index.html', events=json.dumps(events))

@calendar_bp.route('/sessions/<int:session_id>/rsvp', methods=['GET', 'POST'])
@login_required
def session_rsvp(session_id):
    """Handle RSVP for a session."""
    if not current_user.player:
        flash('You need to link your account to a player profile to RSVP.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    session = SessionPlan.query.get_or_404(session_id)
    
    # Check if user has already RSVP'd
    existing_rsvp = SessionRSVP.query.filter_by(
        session_id=session.id,
        player_id=current_user.player.id
    ).first()
    
    # Handle AJAX request
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        status = data.get('status')
        notes = data.get('notes', '')
        
        if status not in ['attending', 'maybe', 'not_attending']:
            return jsonify({'success': False, 'message': 'Invalid status'})
        
        if existing_rsvp:
            existing_rsvp.status = status
            existing_rsvp.notes = notes
            existing_rsvp.updated_at = datetime.utcnow()
        else:
            new_rsvp = SessionRSVP(
                session_id=session.id,
                player_id=current_user.player.id,
                status=status,
                notes=notes
            )
            db.session.add(new_rsvp)
        
        db.session.commit()
        return jsonify({'success': True})
    
    # Handle form submission
    from app.forms.rsvp_form import RSVPForm
    form = RSVPForm()
    
    if form.validate_on_submit():
        if existing_rsvp:
            existing_rsvp.status = form.status.data
            existing_rsvp.notes = form.notes.data
            existing_rsvp.updated_at = datetime.utcnow()
        else:
            new_rsvp = SessionRSVP(
                session_id=session.id,
                player_id=current_user.player.id,
                status=form.status.data,
                notes=form.notes.data
            )
            db.session.add(new_rsvp)
        
        db.session.commit()
        flash('Your RSVP has been recorded.', 'success')
        return redirect(url_for('session.detail', session_id=session.id))
    
    # Pre-populate form with existing RSVP data
    if existing_rsvp:
        form.status.data = existing_rsvp.status
        form.notes.data = existing_rsvp.notes
    
    return render_template('calendar/rsvp.html', form=form, session=session, existing_rsvp=existing_rsvp)


@calendar_bp.route('/api/rsvp', methods=['POST'])
@login_required
def api_rsvp():
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format'}), 400
    
    data = request.get_json()
    event_id = data.get('id')
    event_type = data.get('type')
    status = data.get('status')
    notes = data.get('notes', '')
    
    if not all([event_id, event_type, status]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    if not current_user.player:
        return jsonify({'success': False, 'message': 'You need to link your account to a player first'}), 400
    
    try:
        if event_type == 'session':
            # Handle session RSVP
            existing_rsvp = SessionRSVP.query.filter_by(
                session_id=event_id,
                player_id=current_user.player.id
            ).first()
            
            if existing_rsvp:
                existing_rsvp.status = status
                existing_rsvp.notes = notes
            else:
                rsvp = SessionRSVP(
                    session_id=event_id,
                    player_id=current_user.player.id,
                    status=status,
                    notes=notes
                )
                db.session.add(rsvp)
        
        elif event_type == 'tournament':
            # Handle tournament RSVP
            existing_rsvp = TournamentRSVP.query.filter_by(
                tournament_id=event_id,
                player_id=current_user.player.id
            ).first()
            
            if existing_rsvp:
                existing_rsvp.status = status
                existing_rsvp.notes = notes
            else:
                rsvp = TournamentRSVP(
                    tournament_id=event_id,
                    player_id=current_user.player.id,
                    status=status,
                    notes=notes
                )
                db.session.add(rsvp)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'RSVP updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500