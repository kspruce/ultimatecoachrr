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
    """Display the calendar view with sessions and tournaments."""
    # Get upcoming sessions and tournaments (next 3 months)
    today = datetime.now().date()
    end_date = today + timedelta(days=90)
    
    # Get sessions
    sessions = SessionPlan.query.filter(
        (SessionPlan.date >= today) & (SessionPlan.date <= end_date)
    ).order_by(SessionPlan.date).all()
    
    # Get tournaments
    tournaments = Tournament.query.filter(
        (Tournament.start_date >= today) | 
        ((Tournament.start_date <= today) & (Tournament.end_date >= today))
    ).order_by(Tournament.start_date).all()
    
    # Format events for FullCalendar
    events = []
    
    # Add sessions to events
    for session in sessions:
        # Check if current user has RSVP'd
        rsvp_status = None
        rsvp_notes = None
        
        if current_user.player:
            rsvp = SessionRSVP.query.filter_by(
                session_id=session.id,
                player_id=current_user.player.id
            ).first()
            
            if rsvp:
                rsvp_status = rsvp.status
                rsvp_notes = rsvp.notes
        
        event = {
            'id': session.id,
            'title': session.title,
            'start': session.date.isoformat(),
            'extendedProps': {
                'id': session.id,
                'type': 'session',
                'formatted_date': session.formatted_date,
                'formatted_time': session.formatted_time,
                'location': session.location,
                'focus_area': session.focus_area,
                'notes': session.notes,
                'rsvp_status': rsvp_status,
                'rsvp_notes': rsvp_notes
            }
        }
        
        # Add time if available
        if session.start_time:
            start_datetime = datetime.combine(session.date, session.start_time)
            event['start'] = start_datetime.isoformat()
            
            if session.end_time:
                end_datetime = datetime.combine(session.date, session.end_time)
                event['end'] = end_datetime.isoformat()
        
        events.append(event)
    
    # Add tournaments to events
    for tournament in tournaments:
        # Check if current user has RSVP'd
        rsvp_status = None
        rsvp_notes = None
        selected_by_admin = False
        
        if current_user.player:
            rsvp = TournamentRSVP.query.filter_by(
                tournament_id=tournament.id,
                player_id=current_user.player.id
            ).first()
            
            if rsvp:
                rsvp_status = rsvp.status
                rsvp_notes = rsvp.notes
                selected_by_admin = rsvp.selected_by_admin
        
        event = {
            'id': tournament.id,
            'title': tournament.name,
            'start': tournament.start_date.isoformat(),
            'end': (tournament.end_date + timedelta(days=1)).isoformat() if tournament.end_date else None,
            'allDay': True,
            'extendedProps': {
                'id': tournament.id,
                'type': 'tournament',
                'formatted_date': tournament.formatted_date_range,
                'location': tournament.location,
                'notes': '',
                'rsvp_status': rsvp_status,
                'rsvp_notes': rsvp_notes,
                'selected_by_admin': selected_by_admin
            }
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
    
    return render_template('rsvp.html', form=form, session=session, existing_rsvp=existing_rsvp)

@calendar_bp.route('/tournaments/<int:tournament_id>/rsvp', methods=['GET', 'POST'])
@login_required
def tournament_rsvp(tournament_id):
    """Handle RSVP for a tournament."""
    if not current_user.player:
        flash('You need to link your account to a player profile to RSVP.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Check if user has already RSVP'd
    existing_rsvp = TournamentRSVP.query.filter_by(
        tournament_id=tournament.id,
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
            new_rsvp = TournamentRSVP(
                tournament_id=tournament.id,
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
            new_rsvp = TournamentRSVP(
                tournament_id=tournament.id,
                player_id=current_user.player.id,
                status=form.status.data,
                notes=form.notes.data
            )
            db.session.add(new_rsvp)
        
        db.session.commit()
        flash('Your RSVP has been recorded.', 'success')
        return redirect(url_for('tournament.detail', tournament_id=tournament.id))
    
    # Pre-populate form with existing RSVP data
    if existing_rsvp:
        form.status.data = existing_rsvp.status
        form.notes.data = existing_rsvp.notes
    
    return render_template('tournament_rsvp.html', form=form, tournament=tournament, existing_rsvp=existing_rsvp)