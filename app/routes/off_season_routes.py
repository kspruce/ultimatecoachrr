# app/routes/off_season_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.off_season import OffSeasonPhase, OffSeasonWorkout, OffSeasonExercise, PlayerOffSeasonProgress, DEFAULT_PHASES
from app.models.player import Player
from datetime import datetime, date
from sqlalchemy import func
import markdown
import os
import json

# Create blueprint
off_season = Blueprint('off_season', __name__)

@off_season.route('/off-season')
@login_required
def index():
    """Main off-season training page"""
    # Get current phase based on date
    today = date.today()
    current_phase = OffSeasonPhase.query.filter(
        OffSeasonPhase.start_date <= today,
        OffSeasonPhase.end_date >= today,
        OffSeasonPhase.team_organization_id == current_user.current_team_id
    ).first()
    
    # If no current phase, get the next upcoming phase
    if not current_phase:
        current_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.start_date > today,
            OffSeasonPhase.team_organization_id == current_user.current_team_id
        ).order_by(OffSeasonPhase.start_date).first()
    
    # Get all phases for navigation
    all_phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get recent workouts
    recent_workouts = OffSeasonWorkout.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonWorkout.created_at.desc()).limit(5).all()
    
    # Get player progress if player is linked
    player_progress = None
    if hasattr(current_user, 'player') and current_user.player:
        player_progress = PlayerOffSeasonProgress.query.filter_by(
            player_id=current_user.player.id,
            team_organization_id=current_user.current_team_id
        ).order_by(PlayerOffSeasonProgress.completion_date.desc()).limit(10).all()
    
    return render_template('off_season/index.html', 
                           current_phase=current_phase,
                           all_phases=all_phases,
                           recent_workouts=recent_workouts,
                           player_progress=player_progress)

@off_season.route('/off-season/phases')
@login_required
def phases():
    """View all off-season phases"""
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    return render_template('off_season/phases.html', phases=phases)

@off_season.route('/off-season/phase/<int:phase_id>')
@login_required
def phase_detail(phase_id):
    """View details of a specific phase"""
    phase = OffSeasonPhase.query.filter_by(
        id=phase_id,
        team_organization_id=current_user.current_team_id
    ).first_or_404()
    
    # Get workouts for this phase
    workouts = OffSeasonWorkout.query.filter_by(
        phase_id=phase_id,
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonWorkout.title).all()
    
    return render_template('off_season/phase_detail.html', phase=phase, workouts=workouts)

@off_season.route('/off-season/workouts')
@login_required 
def workouts():
    """View all workouts across all phases"""
    # Get filter parameters
    phase_id = request.args.get('phase_id', type=int)
    workout_type = request.args.get('type')
    difficulty = request.args.get('difficulty')
    
    # Base query
    query = OffSeasonWorkout.query.filter_by(team_organization_id=current_user.current_team_id)
    
    # Apply filters
    if phase_id:
        query = query.filter_by(phase_id=phase_id)
    if workout_type:
        query = query.filter_by(workout_type=workout_type)
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)
    
    # Get results
    workouts = query.order_by(OffSeasonWorkout.title).all()
    
    # Get phases for filter dropdown
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get unique workout types and difficulty levels for filter dropdowns
    workout_types = db.session.query(OffSeasonWorkout.workout_type).filter_by(
        team_organization_id=current_user.current_team_id
    ).distinct().all()
    difficulty_levels = db.session.query(OffSeasonWorkout.difficulty_level).filter_by(
        team_organization_id=current_user.current_team_id
    ).distinct().all()
    
    return render_template('off_season/workouts.html', 
                           workouts=workouts,
                           phases=phases,
                           workout_types=[wt[0] for wt in workout_types if wt[0]],
                           difficulty_levels=[dl[0] for dl in difficulty_levels if dl[0]],
                           selected_phase=phase_id,
                           selected_type=workout_type,
                           selected_difficulty=difficulty)

@off_season.route('/off-season/workout/<int:workout_id>')
@login_required 
def workout_detail(workout_id):
    """View details of a specific workout"""
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=current_user.current_team_id
    ).first_or_404()
    
    # Get exercises for this workout
    exercises = OffSeasonExercise.query.filter_by(
        workout_id=workout_id
    ).order_by(OffSeasonExercise.order).all()
    
    # Check if current user has completed this workout
    completed = False
    if hasattr(current_user, 'player') and current_user.player:
        completed = PlayerOffSeasonProgress.query.filter_by(
            player_id=current_user.player.id,
            workout_id=workout_id
        ).first() is not None
    
    return render_template('off_season/workout_detail.html', 
                           workout=workout, 
                           exercises=exercises,
                           completed=completed)

@off_season.route('/off-season/player-progress')
@login_required 
def player_progress():
    """View progress for all players"""
    # Only admins can view all player progress
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Get all players
    players = Player.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).all()
    
    # Get phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get progress data
    progress_data = {}
    for player in players:
        progress_data[player.id] = {}
        for phase in phases:
            # Count completed workouts in this phase
            completed_count = PlayerOffSeasonProgress.query.join(OffSeasonWorkout).filter(
                PlayerOffSeasonProgress.player_id == player.id,
                OffSeasonWorkout.phase_id == phase.id
            ).count()
            
            # Count total workouts in this phase
            total_count = OffSeasonWorkout.query.filter_by(
                phase_id=phase.id,
                team_organization_id=current_user.current_team_id
            ).count()
            
            progress_data[player.id][phase.id] = {
                'completed': completed_count,
                'total': total_count,
                'percentage': round((completed_count / total_count * 100) if total_count > 0 else 0)
            }
    
    return render_template('off_season/player_progress.html', 
                           players=players,
                           phases=phases,
                           progress_data=progress_data)

@off_season.route('/off-season/my-progress')
@login_required 
def my_progress():
    """View current user's progress"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    player = current_user.player
    
    # Get phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get progress data
    progress_data = {}
    for phase in phases:
        # Get completed workouts in this phase
        completed_workouts = db.session.query(OffSeasonWorkout).join(
            PlayerOffSeasonProgress, PlayerOffSeasonProgress.workout_id == OffSeasonWorkout.id
        ).filter(
            PlayerOffSeasonProgress.player_id == player.id,
            OffSeasonWorkout.phase_id == phase.id
        ).all()
        
        # Get all workouts in this phase
        all_workouts = OffSeasonWorkout.query.filter_by(
            phase_id=phase.id,
            team_organization_id=current_user.current_team_id
        ).all()
        
        # Calculate completion percentage
        completion_percentage = round((len(completed_workouts) / len(all_workouts) * 100) if all_workouts else 0)
        
        progress_data[phase.id] = {
            'completed_workouts': completed_workouts,
            'all_workouts': all_workouts,
            'completion_percentage': completion_percentage
        }
    
    # Get recent progress entries
    recent_progress = PlayerOffSeasonProgress.query.filter_by(
        player_id=player.id,
        team_organization_id=current_user.current_team_id
    ).order_by(PlayerOffSeasonProgress.completion_date.desc()).limit(10).all()
    
    return render_template('off_season/my_progress.html', 
                           player=player,
                           phases=phases,
                           progress_data=progress_data,
                           recent_progress=recent_progress)

@off_season.route('/off-season/record-progress/<int:workout_id>', methods=['GET', 'POST'])
@login_required 
def record_progress(workout_id):
    """Record completion of a workout"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=current_user.current_team_id
    ).first_or_404()
    
    if request.method == 'POST':
        # Check if already recorded
        existing = PlayerOffSeasonProgress.query.filter_by(
            player_id=current_user.player.id,
            workout_id=workout_id
        ).first()
        
        if existing:
            # Update existing record
            existing.completion_date = datetime.utcnow()
            existing.notes = request.form.get('notes', '')
            existing.rating = request.form.get('rating', type=int)
            existing.difficulty_feedback = request.form.get('difficulty')
            db.session.commit()
            flash('Workout progress updated!', 'success')
        else:
            # Create new progress record
            progress = PlayerOffSeasonProgress(
                player_id=current_user.player.id,
                phase_id=workout.phase_id,
                workout_id=workout_id,
                notes=request.form.get('notes', ''),
                rating=request.form.get('rating', type=int),
                difficulty_feedback=request.form.get('difficulty'),
                team_organization_id=current_user.current_team_id
            )
            db.session.add(progress)
            db.session.commit()
            flash('Workout completed! Progress recorded.', 'success')
        
        return redirect(url_for('off_season.workout_detail', workout_id=workout_id))
    
    # Check if already completed
    existing = PlayerOffSeasonProgress.query.filter_by(
        player_id=current_user.player.id,
        workout_id=workout_id
    ).first()
    
    return render_template('off_season/record_progress.html', 
                           workout=workout,
                           existing=existing)

@off_season.route('/off-season/guide')
@login_required 
def training_guide():
    """View the full off-season training guide"""
    # Read the markdown file
    guide_path = os.path.join(current_app.root_path, 'static', 'docs', 'ultimate_frisbee_off_season_guide.md')
    
    try:
        with open(guide_path, 'r') as file:
            content = file.read()
            # Convert markdown to HTML
            html_content = markdown.markdown(content)
    except FileNotFoundError:
        html_content = "<p>The off-season training guide is not available.</p>"
    
    return render_template('off_season/guide.html', content=html_content)

# Admin routes for managing off-season content

@off_season.route('/off-season/admin')
@login_required 
def admin():
    """Admin dashboard for off-season training"""
    # Only admins can access this page
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).order_by(OffSeasonPhase.start_date).all()
    
    workouts_count = OffSeasonWorkout.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).count()
    
    exercises_count = db.session.query(func.count(OffSeasonExercise.id)).join(
        OffSeasonWorkout
    ).filter(
        OffSeasonWorkout.team_organization_id == current_user.current_team_id
    ).scalar()
    
    progress_entries = PlayerOffSeasonProgress.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).count()
    
    return render_template('off_season/admin.html',
                           phases=phases,
                           workouts_count=workouts_count,
                           exercises_count=exercises_count,
                           progress_entries=progress_entries)

@off_season.route('/off-season/initialize', methods=['POST'])
@login_required 
def initialize_off_season():
    """Initialize off-season data from defaults"""
    # Only admins can initialize data
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Check if phases already exist
    existing_phases = OffSeasonPhase.query.filter_by(
        team_organization_id=current_user.current_team_id
    ).count()
    
    if existing_phases > 0:
        flash('Off-season phases already exist. Delete existing data before initializing.', 'warning')
        return redirect(url_for('off_season.admin'))
    
    # Create default phases
    for phase_data in DEFAULT_PHASES:
        phase = OffSeasonPhase(
            name=phase_data['name'],
            description=phase_data['description'],
            start_date=datetime.strptime(phase_data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(phase_data['end_date'], '%Y-%m-%d').date(),
            primary_focus=phase_data['primary_focus'],
            training_emphasis=phase_data['training_emphasis'],
            volume_intensity=phase_data['volume_intensity'],
            key_outcome=phase_data['key_outcome'],
            team_organization_id=current_user.current_team_id
        )
        db.session.add(phase)
    
    db.session.commit()
    flash('Off-season training phases have been initialized!', 'success')
    return redirect(url_for('off_season.admin'))

