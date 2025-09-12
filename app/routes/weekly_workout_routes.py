# app/routes/weekly_workout_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, g, session
from flask_login import login_required, current_user
from app import db
from app.models.off_season import OffSeasonPhase, OffSeasonWorkout, PlayerOffSeasonProgress
from app.models.weekly_schedule_template import WeeklyScheduleTemplate
from app.models.weekly_workout_completion import WeeklyWorkoutCompletion
from datetime import datetime, date, timedelta
import calendar
import json

# Import get_current_team_id function from off_season_routes
from app.routes.off_season_routes import get_current_team_id

# Create blueprint
weekly_workout = Blueprint('weekly_workout', __name__)

@weekly_workout.route('/off-season/my-weekly-schedule')
@login_required
def my_weekly_schedule():
    """View player's weekly schedule"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    player = current_user.player
    
    # Get current phase based on date
    today = date.today()
    current_phase = OffSeasonPhase.query.filter(
        OffSeasonPhase.start_date <= today,
        OffSeasonPhase.end_date >= today,
        OffSeasonPhase.team_organization_id == get_current_team_id()
    ).first()
    
    if not current_phase:
        # Try to find the most recent phase that has ended
        recent_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.end_date < today,
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).order_by(OffSeasonPhase.end_date.desc()).first()
        
        # If no recent phase, try to find the next upcoming phase
        if not recent_phase:
            upcoming_phase = OffSeasonPhase.query.filter(
                OffSeasonPhase.start_date > today,
                OffSeasonPhase.team_organization_id == get_current_team_id()
            ).order_by(OffSeasonPhase.start_date).first()
            
            if upcoming_phase:
                current_phase = upcoming_phase
            else:
                flash('There is no active training phase at the moment.', 'info')
                return redirect(url_for('off_season.index'))
        else:
            current_phase = recent_phase
    
    # Get the selected template type (default to standard)
    template_type = request.args.get('template_type', 'standard')
    
    # Get the schedule template for this phase
    template = WeeklyScheduleTemplate.query.filter_by(
        phase_id=current_phase.id,
        template_type=template_type,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not template:
        # Try to find any template for this phase
        template = WeeklyScheduleTemplate.query.filter_by(
            phase_id=current_phase.id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if not template:
            flash(f'No schedule template found for the current phase.', 'warning')
            return redirect(url_for('off_season.phase_detail', phase_id=current_phase.id))
        
        template_type = template.template_type
    
    # Calculate the current week number within the phase
    if today >= current_phase.start_date and today <= current_phase.end_date:
        # We're in the active phase
        days_since_phase_start = (today - current_phase.start_date).days
        current_week = (days_since_phase_start // 7) + 1
    elif today < current_phase.start_date:
        # Phase hasn't started yet, show week 1
        current_week = 1
    else:
        # Phase has ended, show the last week
        total_days = (current_phase.end_date - current_phase.start_date).days
        current_week = (total_days // 7) + 1
    
    # Calculate the start date of the current week (Monday)
    if today >= current_phase.start_date and today <= current_phase.end_date:
        # We're in the active phase
        monday_offset = today.weekday()  # 0 for Monday, 6 for Sunday
        week_start_date = today - timedelta(days=monday_offset)
    elif today < current_phase.start_date:
        # Phase hasn't started yet, use the first Monday of the phase
        phase_start_weekday = current_phase.start_date.weekday()
        if phase_start_weekday == 0:  # Monday
            week_start_date = current_phase.start_date
        else:
            # Find the first Monday after phase start
            days_until_monday = 7 - phase_start_weekday
            week_start_date = current_phase.start_date + timedelta(days=days_until_monday)
    else:
        # Phase has ended, use the last week's Monday
        total_days = (current_phase.end_date - current_phase.start_date).days
        total_weeks = (total_days // 7) + 1
        week_start_date = current_phase.start_date + timedelta(days=(total_weeks-1)*7)
        # Adjust to Monday if needed
        while week_start_date.weekday() != 0:
            week_start_date -= timedelta(days=1)
    
    # Check if there's an existing weekly completion record
    weekly_completion = WeeklyWorkoutCompletion.query.filter_by(
        player_id=player.id,
        phase_id=current_phase.id,
        template_id=template.id,
        week_number=current_week,
        team_organization_id=get_current_team_id()
    ).first()
    
    # If no record exists, create one
    if not weekly_completion:
        weekly_completion = WeeklyWorkoutCompletion(
            player_id=player.id,
            phase_id=current_phase.id,
            template_id=template.id,
            week_number=current_week,
            week_start_date=week_start_date,
            team_organization_id=get_current_team_id()
        )
        db.session.add(weekly_completion)
        db.session.commit()
    
    # Get all available templates for this phase
    available_templates = WeeklyScheduleTemplate.query.filter_by(
        phase_id=current_phase.id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary of template types
    template_types = {t.template_type: t.template_type.capitalize() for t in available_templates}
    
    # Get the days of the week for the current week
    week_dates = {}
    for i in range(7):
        day_date = week_start_date + timedelta(days=i)
        day_name = calendar.day_name[i]
        week_dates[day_name.lower()] = day_date
    
    return render_template('weekly_schedule.html',
                           player=player,
                           current_phase=current_phase,
                           template=template,
                           selected_type=template_type,
                           template_types=template_types,
                           current_week=current_week,
                           week_start_date=week_start_date,
                           week_dates=week_dates,
                           weekly_completion=weekly_completion,
                           timedelta=timedelta)

@weekly_workout.route('/off-season/weekly-completion/update', methods=['POST'])
@login_required
def update_weekly_completion():
    """Update weekly workout completion status"""
    if not hasattr(current_user, 'player') or not current_user.player:
        return jsonify({'success': False, 'message': 'No player profile linked'})
    
    data = request.json
    completion_id = data.get('completion_id')
    field = data.get('field')
    value = data.get('value')
    
    if not completion_id or not field:
        return jsonify({'success': False, 'message': 'Missing required data'})
    
    # Get the completion record
    completion = WeeklyWorkoutCompletion.query.filter_by(
        id=completion_id,
        player_id=current_user.player.id,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not completion:
        return jsonify({'success': False, 'message': 'Completion record not found'})
    
    # Update the specified field
    if hasattr(completion, field):
        setattr(completion, field, value)
        
        # Update completion percentage
        total_slots = 14  # 7 days * 2 slots per day
        completed_slots = 0
        
        # Count completed slots
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            morning_field = f"{day}_morning_completed"
            evening_field = f"{day}_evening_completed"
            
            if getattr(completion, morning_field):
                completed_slots += 1
            if getattr(completion, evening_field):
                completed_slots += 1
        
        # Calculate percentage
        completion.completion_percentage = (completed_slots / total_slots) * 100
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Update successful',
            'completion_percentage': completion.completion_percentage
        })
    else:
        return jsonify({'success': False, 'message': f'Invalid field: {field}'})

@weekly_workout.route('/off-season/weekly-completion/notes', methods=['POST'])
@login_required
def update_weekly_notes():
    """Update weekly workout notes"""
    if not hasattr(current_user, 'player') or not current_user.player:
        return jsonify({'success': False, 'message': 'No player profile linked'})
    
    data = request.json
    completion_id = data.get('completion_id')
    day = data.get('day')
    notes = data.get('notes')
    
    if not completion_id or not day:
        return jsonify({'success': False, 'message': 'Missing required data'})
    
    # Get the completion record
    completion = WeeklyWorkoutCompletion.query.filter_by(
        id=completion_id,
        player_id=current_user.player.id,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not completion:
        return jsonify({'success': False, 'message': 'Completion record not found'})
    
    # Update the notes field
    notes_field = f"{day}_notes"
    if hasattr(completion, notes_field):
        setattr(completion, notes_field, notes)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Notes updated'})
    else:
        return jsonify({'success': False, 'message': f'Invalid day: {day}'})

@weekly_workout.route('/off-season/my-weekly-progress')
@login_required
def view_weekly_progress():
    """View weekly progress for all weeks in the current phase"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    player = current_user.player
    
    # Get current phase based on date
    today = date.today()
    current_phase = OffSeasonPhase.query.filter(
        OffSeasonPhase.start_date <= today,
        OffSeasonPhase.end_date >= today,
        OffSeasonPhase.team_organization_id == get_current_team_id()
    ).first()
    
    if not current_phase:
        # Try to find the most recent phase that has ended
        recent_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.end_date < today,
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).order_by(OffSeasonPhase.end_date.desc()).first()
        
        # If no recent phase, try to find the next upcoming phase
        if not recent_phase:
            upcoming_phase = OffSeasonPhase.query.filter(
                OffSeasonPhase.start_date > today,
                OffSeasonPhase.team_organization_id == get_current_team_id()
            ).order_by(OffSeasonPhase.start_date).first()
            
            if upcoming_phase:
                current_phase = upcoming_phase
            else:
                flash('No training phases found.', 'info')
                return redirect(url_for('off_season.index'))
        else:
            current_phase = recent_phase
    
    # Get all weekly completion records for this player in this phase
    weekly_completions = WeeklyWorkoutCompletion.query.filter_by(
        player_id=player.id,
        phase_id=current_phase.id,
        team_organization_id=get_current_team_id()
    ).order_by(WeeklyWorkoutCompletion.week_number).all()
    
    # Calculate overall completion percentage
    total_percentage = 0
    if weekly_completions:
        for completion in weekly_completions:
            total_percentage += completion.completion_percentage
        total_percentage /= len(weekly_completions)
    
    return render_template('weekly_progress.html',
                           player=player,
                           current_phase=current_phase,
                           weekly_completions=weekly_completions,
                           total_percentage=total_percentage)

@weekly_workout.route('/off-season/admin/player-weekly-progress')
@login_required
def admin_player_weekly_progress():
    """Admin view of player weekly progress"""
    # Check if user is admin
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Get all phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date.desc()).all()
    
    # Get selected phase (default to most recent)
    phase_id = request.args.get('phase_id', None)
    if phase_id:
        selected_phase = OffSeasonPhase.query.filter_by(
            id=phase_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
    else:
        # Get current or most recent phase
        today = date.today()
        selected_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.start_date <= today,
            OffSeasonPhase.end_date >= today,
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).first()
        
        if not selected_phase:
            selected_phase = OffSeasonPhase.query.filter_by(
                team_organization_id=get_current_team_id()
            ).order_by(OffSeasonPhase.end_date.desc()).first()
    
    if not selected_phase:
        flash('No training phases found.', 'info')
        return redirect(url_for('off_season.index'))
    
    # Get all players with completion records for this phase
    player_data = db.session.query(
        WeeklyWorkoutCompletion.player_id,
        db.func.avg(WeeklyWorkoutCompletion.completion_percentage).label('avg_completion'),
        db.func.count(WeeklyWorkoutCompletion.id).label('weeks_tracked')
    ).filter_by(
        phase_id=selected_phase.id,
        team_organization_id=get_current_team_id()
    ).group_by(
        WeeklyWorkoutCompletion.player_id
    ).all()
    
    # Get player details
    from app.models.player import Player
    players = []
    for player_id, avg_completion, weeks_tracked in player_data:
        player = Player.query.get(player_id)
        if player:
            players.append({
                'id': player.id,
                'name': player.name,
                'avg_completion': avg_completion,
                'weeks_tracked': weeks_tracked
            })
    
    # Sort by completion percentage (descending)
    players.sort(key=lambda x: x['avg_completion'], reverse=True)
    
    return render_template('admin_weekly_progress.html',
                           phases=phases,
                           selected_phase=selected_phase,
                           players=players)

@weekly_workout.route('/off-season/weekly-completion/<int:completion_id>/details')
@login_required
def weekly_completion_details(completion_id):
    """Get detailed data for a specific weekly completion record"""
    # Check if user has permission
    completion = WeeklyWorkoutCompletion.query.filter_by(
        id=completion_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Only allow the player or admin to view details
    if not current_user.is_admin and (not hasattr(current_user, 'player') or current_user.player.id != completion.player_id):
        return jsonify({'success': False, 'message': 'Access denied'})
    
    # Get template details
    template = WeeklyScheduleTemplate.query.get_or_404(completion.template_id)
    
    # Create day-by-day data
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    day_data = {}
    
    for day in days:
        morning_workout = getattr(template, f"{day}_morning")
        evening_workout = getattr(template, f"{day}_evening")
        morning_completed = getattr(completion, f"{day}_morning_completed")
        evening_completed = getattr(completion, f"{day}_evening_completed")
        notes = getattr(completion, f"{day}_notes")
        
        day_data[day] = {
            'morning': {
                'workout': morning_workout,
                'completed': morning_completed
            },
            'evening': {
                'workout': evening_workout,
                'completed': evening_completed
            },
            'notes': notes
        }
    
    # Format date
    week_start = completion.week_start_date.strftime('%b %d, %Y')
    week_end = (completion.week_start_date + timedelta(days=6)).strftime('%b %d, %Y')
    
    return jsonify({
        'success': True,
        'completion': {
            'id': completion.id,
            'week_number': completion.week_number,
            'week_date': f"{week_start} - {week_end}",
            'completion_percentage': completion.completion_percentage,
            'days': day_data
        }
    })