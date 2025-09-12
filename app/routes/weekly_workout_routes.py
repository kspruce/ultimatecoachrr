# app/routes/weekly_workout_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, g, session
from flask_login import login_required, current_user
from app import db
from app.models.off_season import OffSeasonPhase, OffSeasonWorkout, PlayerOffSeasonProgress
from app.models.weekly_schedule_template import WeeklyScheduleTemplate
from app.models.weekly_workout_completion import WeeklyWorkoutCompletion
from datetime import datetime, date, timedelta
import calendar

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
        flash('There is no active training phase at the moment.', 'info')
        return redirect(url_for('off_season.index'))
    
    # Get the selected template type (default to standard)
    template_type = request.args.get('template_type', 'standard')
    
    # Get the schedule template for this phase
    template = WeeklyScheduleTemplate.query.filter_by(
        phase_id=current_phase.id,
        template_type=template_type,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not template:
        flash(f'No {template_type} schedule template found for the current phase.', 'warning')
        return redirect(url_for('off_season.phase_detail', phase_id=current_phase.id))
    
    # Calculate the current week number within the phase
    days_since_phase_start = (today - current_phase.start_date).days
    current_week = (days_since_phase_start // 7) + 1
    
    # Calculate the start date of the current week (Monday)
    # Get the Monday of the current week
    monday_offset = today.weekday()  # 0 for Monday, 6 for Sunday
    week_start_date = today - timedelta(days=monday_offset)
    
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
    
    return render_template('off_season/weekly_schedule.html',
                           player=player,
                           current_phase=current_phase,
                           template=template,
                           weekly_completion=weekly_completion,
                           template_types=template_types,
                           selected_type=template_type,
                           current_week=current_week,
                           week_start_date=week_start_date,
                           week_dates=week_dates,
                           today=today)

@weekly_workout.route('/off-season/toggle-workout-completion', methods=['POST'])
@login_required
def toggle_workout_completion():
    """Toggle completion status for a workout in the weekly schedule"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        return jsonify({'success': False, 'message': 'Player profile not linked'})
    
    data = request.json
    completion_id = data.get('completion_id')
    day = data.get('day')
    time_of_day = data.get('time_of_day')
    notes = data.get('notes', '')
    
    if not all([completion_id, day, time_of_day]):
        return jsonify({'success': False, 'message': 'Missing required parameters'})
    
    # Get the weekly completion record
    completion = WeeklyWorkoutCompletion.query.filter_by(
        id=completion_id,
        player_id=current_user.player.id,
        team_organization_id=get_current_team_id()
    ).first()
    
    if not completion:
        return jsonify({'success': False, 'message': 'Completion record not found'})
    
    try:
        # Toggle the completion status
        field_name = f"{day}_{time_of_day}_completed"
        notes_field = f"{day}_notes"
        
        # Check if the field exists
        if hasattr(completion, field_name):
            current_value = getattr(completion, field_name)
            setattr(completion, field_name, not current_value)
            
            # Update notes if provided
            if notes:
                setattr(completion, notes_field, notes)
            
            # Recalculate completion percentage
            completion.calculate_completion_percentage()
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'completed': not current_value,
                'completion_percentage': completion.completion_percentage
            })
        else:
            return jsonify({'success': False, 'message': f'Invalid field: {field_name}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@weekly_workout.route('/off-season/view-weekly-progress')
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
        # Get the most recent phase
        current_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).order_by(OffSeasonPhase.end_date.desc()).first()
        
        if not current_phase:
            flash('No training phases found.', 'info')
            return redirect(url_for('off_season.index'))
    
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
    
    return render_template('off_season/weekly_progress.html',
                           player=player,
                           current_phase=current_phase,
                           weekly_completions=weekly_completions,
                           total_percentage=total_percentage,
                           today=today)

@weekly_workout.route('/off-season/admin/player-weekly-progress')
@login_required
def admin_player_weekly_progress():
    """Admin view of weekly progress for all players"""
    # Only admins can view this page
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Get all players
    from app.models.player import Player
    players = Player.query.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Get current phase
    today = date.today()
    current_phase = OffSeasonPhase.query.filter(
        OffSeasonPhase.start_date <= today,
        OffSeasonPhase.end_date >= today,
        OffSeasonPhase.team_organization_id == get_current_team_id()
    ).first()
    
    if not current_phase:
        # Get the most recent phase
        current_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).order_by(OffSeasonPhase.end_date.desc()).first()
        
        if not current_phase:
            flash('No training phases found.', 'info')
            return redirect(url_for('off_season.admin'))
    
    # Calculate the current week number within the phase
    days_since_phase_start = (today - current_phase.start_date).days
    current_week = (days_since_phase_start // 7) + 1
    
    # Get weekly progress data for all players
    progress_data = {}
    for player in players:
        # Get the player's weekly completions for this phase
        weekly_completions = WeeklyWorkoutCompletion.query.filter_by(
            player_id=player.id,
            phase_id=current_phase.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        # Calculate overall completion percentage
        total_percentage = 0
        if weekly_completions:
            for completion in weekly_completions:
                total_percentage += completion.completion_percentage
            total_percentage /= len(weekly_completions)
        
        # Store data for this player
        progress_data[player.id] = {
            'weekly_completions': weekly_completions,
            'total_percentage': total_percentage
        }
    
    return render_template('off_season/admin_weekly_progress.html',
                           players=players,
                           current_phase=current_phase,
                           current_week=current_week,
                           progress_data=progress_data,
                           today=today)