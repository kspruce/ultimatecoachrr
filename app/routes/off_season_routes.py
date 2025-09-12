# app/routes/off_season_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models.off_season import OffSeasonPhase, OffSeasonWorkout, OffSeasonExercise, PlayerOffSeasonProgress, DEFAULT_PHASES
from app.models.player import Player
from app.models.weekly_schedule_template import WeeklyScheduleTemplate
from datetime import datetime, date
from sqlalchemy import func
import markdown
import os
import json
from app.utils.utils import admin_required

# Create blueprint
off_season = Blueprint('off_season', __name__)

# Store team_id in g for each request
@off_season.before_request
def before_request():
    from flask import g, session
    from flask_login import current_user
    
    if current_user.is_authenticated:
        if current_user.is_admin:
            g.current_team_id = session.get('current_team_id', current_user.team_organization_id)
        else:
            g.current_team_id = current_user.team_organization_id

# Then define your helper function
def get_current_team_id():
    from flask import g
    return getattr(g, 'current_team_id', None)

@off_season.route('/off-season')
@login_required
def index():
    """Main off-season training page"""
    # Get current phase based on date
    today = date.today()
    current_phase = OffSeasonPhase.query.filter(
        OffSeasonPhase.start_date <= today,
        OffSeasonPhase.end_date >= today,
        OffSeasonPhase.team_organization_id == get_current_team_id()
    ).first()
    
    # If no current phase, get the next upcoming phase
    if not current_phase:
        current_phase = OffSeasonPhase.query.filter(
            OffSeasonPhase.start_date > today,
            OffSeasonPhase.team_organization_id == get_current_team_id()
        ).order_by(OffSeasonPhase.start_date).first()
    
    # Get all phases for navigation
    all_phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get recent workouts
    recent_workouts = OffSeasonWorkout.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonWorkout.created_at.desc()).limit(5).all()
    
    # Get player progress if player is linked
    player_progress = None
    if hasattr(current_user, 'player') and current_user.player:
        player_progress = PlayerOffSeasonProgress.query.filter_by(
            player_id=current_user.player.id,
            team_organization_id=get_current_team_id()
        ).order_by(PlayerOffSeasonProgress.completion_date.desc()).limit(10).all()
    
    return render_template('off_season/index.html', 
                           current_phase=current_phase,
                           all_phases=all_phases,
                           recent_workouts=recent_workouts,
                           player_progress=player_progress,
                           today=today)

@off_season.route('/off-season/phases')
@login_required
def phases():
    """View all off-season phases"""
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    today = date.today()
    
    return render_template('off_season/phases.html', phases=phases, today=today)

@off_season.route('/off-season/phase/<int:phase_id>')
@login_required
def phase_detail(phase_id):
    """View details of a specific phase"""
    phase = OffSeasonPhase.query.filter_by(
        id=phase_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get workouts for this phase
    workouts = OffSeasonWorkout.query.filter_by(
        phase_id=phase_id,
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonWorkout.title).all()
    
    today = date.today()
    
    # Get schedule templates for this phase
    schedule_templates = {}
    template_types = ['standard', 'minimal', 'high_volume']
    
    for template_type in template_types:
        template = WeeklyScheduleTemplate.query.filter_by(
            phase_id=phase_id,
            template_type=template_type,
            team_organization_id=get_current_team_id()
        ).first()
        schedule_templates[template_type] = template
    
    return render_template('off_season/phase_detail.html', 
                          phase=phase, 
                          workouts=workouts, 
                          today=today,
                          schedule_templates=schedule_templates)

@off_season.route('/off-season/workouts')
@login_required
def workouts():
    """View all workouts across all phases"""
    # Get filter parameters
    phase_id = request.args.get('phase_id', type=int)
    workout_type = request.args.get('type')
    difficulty = request.args.get('difficulty')
    
    # Base query
    query = OffSeasonWorkout.query.filter_by(team_organization_id=get_current_team_id())
    
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
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get unique workout types and difficulty levels for filter dropdowns
    workout_types = db.session.query(OffSeasonWorkout.workout_type).filter_by(
        team_organization_id=get_current_team_id()
    ).distinct().all()
    difficulty_levels = db.session.query(OffSeasonWorkout.difficulty_level).filter_by(
        team_organization_id=get_current_team_id()
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
        team_organization_id=get_current_team_id()
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
        team_organization_id=get_current_team_id()
    ).all()
    
    # Get phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
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
                team_organization_id=get_current_team_id()
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
        team_organization_id=get_current_team_id()
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
            team_organization_id=get_current_team_id()
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
        team_organization_id=get_current_team_id()
    ).order_by(PlayerOffSeasonProgress.completion_date.desc()).limit(10).all()
    
    today = date.today()
    
    return render_template('off_season/my_progress.html', 
                           player=player,
                           phases=phases,
                           progress_data=progress_data,
                           recent_progress=recent_progress,
                           today=today)

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
        team_organization_id=get_current_team_id()
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
                team_organization_id=get_current_team_id()
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
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    workouts_count = OffSeasonWorkout.query.filter_by(
        team_organization_id=get_current_team_id()
    ).count()
    
    exercises_count = db.session.query(func.count(OffSeasonExercise.id)).join(
        OffSeasonWorkout
    ).filter(
        OffSeasonWorkout.team_organization_id == get_current_team_id()
    ).scalar()
    
    progress_entries = PlayerOffSeasonProgress.query.filter_by(
        team_organization_id=get_current_team_id()
    ).count()
    
    today = date.today()
    
    return render_template('off_season/admin.html',
                           phases=phases,
                           workouts_count=workouts_count,
                           exercises_count=exercises_count,
                           progress_entries=progress_entries,
                           today=today)

# Alias for admin_dashboard to match the URL in the navigation
@off_season.route('/off-season/admin-dashboard')
@login_required
def admin_dashboard():
    """Alias for admin dashboard"""
    return admin()

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
        team_organization_id=get_current_team_id()
    ).count()
    
    if existing_phases > 0:
        flash('Off-season phases already exist. Delete existing data before initializing.', 'warning')
        return redirect(url_for('off_season.admin_dashboard'))
    
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
            team_organization_id=get_current_team_id()
        )
        db.session.add(phase)
    
    db.session.commit()
    flash('Off-season training phases have been initialized!', 'success')
    return redirect(url_for('off_season.admin_dashboard'))

# New routes for managing phases, workouts, exercises, and goals

@off_season.route('/off-season/add-phase', methods=['POST'])
@login_required
def add_phase():
    """Add a new training phase"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    try:
        # Create new phase
        phase = OffSeasonPhase(
            name=request.form.get('name'),
            description=request.form.get('description'),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date(),
            primary_focus=request.form.get('primary_focus'),
            training_emphasis=request.form.get('training_emphasis'),
            volume_intensity=request.form.get('volume_intensity'),
            key_outcome=request.form.get('key_outcome'),
            team_organization_id=get_current_team_id()
        )
        db.session.add(phase)
        db.session.commit()
        flash('Training phase added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding phase: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.admin_dashboard'))

@off_season.route('/off-season/edit-phase/<int:phase_id>', methods=['GET', 'POST'])
@login_required
def edit_phase(phase_id):
    """Edit an existing training phase"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    phase = OffSeasonPhase.query.filter_by(
        id=phase_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    if request.method == 'POST':
        try:
            phase.name = request.form.get('name')
            phase.description = request.form.get('description')
            phase.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            phase.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            phase.primary_focus = request.form.get('primary_focus')
            phase.training_emphasis = request.form.get('training_emphasis')
            phase.volume_intensity = request.form.get('volume_intensity')
            phase.key_outcome = request.form.get('key_outcome')
            
            db.session.commit()
            flash('Training phase updated successfully!', 'success')
            return redirect(url_for('off_season.admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating phase: {str(e)}', 'danger')
    
    return render_template('off_season/edit_phase.html', phase=phase)

@off_season.route('/off-season/delete-phase/<int:phase_id>', methods=['POST'])
@login_required
def delete_phase(phase_id):
    """Delete a training phase"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    phase = OffSeasonPhase.query.filter_by(
        id=phase_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Delete all workouts, exercises, and progress data associated with this phase
        workouts = OffSeasonWorkout.query.filter_by(phase_id=phase_id).all()
        for workout in workouts:
            # Delete exercises
            OffSeasonExercise.query.filter_by(workout_id=workout.id).delete()
            
            # Delete progress data
            PlayerOffSeasonProgress.query.filter_by(workout_id=workout.id).delete()
        
        # Delete workouts
        OffSeasonWorkout.query.filter_by(phase_id=phase_id).delete()
        
        # Delete phase
        db.session.delete(phase)
        db.session.commit()
        
        flash('Training phase and all associated data deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting phase: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.admin_dashboard'))

@off_season.route('/off-season/add-workout', methods=['POST'])
@login_required
def add_workout():
    """Add a new workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    try:
        # Validate required fields
        required_fields = ['title', 'description', 'workout_type', 'difficulty_level', 'duration', 'phase_id']
        for field in required_fields:
            if not request.form.get(field):
                flash(f'Error: {field.replace("_", " ").title()} is required', 'danger')
                return redirect(url_for('off_season.add_workout_form'))
        
        # Create new workout
        workout = OffSeasonWorkout(
            title=request.form.get('title'),
            description=request.form.get('description'),
            workout_type=request.form.get('workout_type'),
            instructions=request.form.get('instructions', ''),
            duration=request.form.get('duration'),
            equipment_needed=request.form.get('equipment_needed', ''),
            difficulty_level=request.form.get('difficulty_level'),
            phase_id=request.form.get('phase_id', type=int),
            team_organization_id=get_current_team_id()
        )
        db.session.add(workout)
        db.session.commit()
        flash('Workout added successfully!', 'success')
        
        # Redirect to manage exercises page
        return redirect(url_for('off_season.manage_exercises', workout_id=workout.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding workout: {str(e)}', 'danger')
        # Get phases for the form to redisplay
        phases = OffSeasonPhase.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(OffSeasonPhase.start_date).all()
        return render_template('off_season/add_workout.html', phases=phases)


@off_season.route('/off-season/edit-workout/<int:workout_id>', methods=['GET', 'POST'])
@login_required
def edit_workout(workout_id):
    """Edit an existing workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    if request.method == 'POST':
        try:
            workout.title = request.form.get('title')
            workout.description = request.form.get('description')
            workout.workout_type = request.form.get('workout_type')
            workout.instructions = request.form.get('instructions')
            workout.duration = request.form.get('duration')
            workout.equipment_needed = request.form.get('equipment_needed')
            workout.difficulty_level = request.form.get('difficulty_level')
            workout.phase_id = request.form.get('phase_id', type=int)
            
            db.session.commit()
            flash('Workout updated successfully!', 'success')
            return redirect(url_for('off_season.admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating workout: {str(e)}', 'danger')
    
    return render_template('off_season/edit_workout.html', workout=workout, phases=phases)

@off_season.route('/off-season/delete-workout/<int:workout_id>', methods=['POST'])
@login_required
def delete_workout(workout_id):
    """Delete a workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Delete exercises
        OffSeasonExercise.query.filter_by(workout_id=workout_id).delete()
        
        # Delete progress data
        PlayerOffSeasonProgress.query.filter_by(workout_id=workout_id).delete()
        
        # Delete workout
        db.session.delete(workout)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@off_season.route('/off-season/get-workouts')
@login_required
def get_workouts():
    """Get workouts based on filters"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    phase_id = request.args.get('phase_id', type=int)
    workout_type = request.args.get('type')
    
    # Base query
    query = OffSeasonWorkout.query.filter_by(team_organization_id=get_current_team_id())
    
    # Apply filters
    if phase_id:
        query = query.filter_by(phase_id=phase_id)
    if workout_type:
        query = query.filter_by(workout_type=workout_type)
    
    # Get results
    workouts = query.order_by(OffSeasonWorkout.title).all()
    
    # Format results
    result = []
    for workout in workouts:
        exercises_count = OffSeasonExercise.query.filter_by(workout_id=workout.id).count()
        phase = OffSeasonPhase.query.get(workout.phase_id)
        
        result.append({
            'id': workout.id,
            'title': workout.title,
            'phase_name': phase.name if phase else 'Unknown',
            'workout_type': workout.workout_type,
            'difficulty_level': workout.difficulty_level,
            'exercises_count': exercises_count
        })
    
    return jsonify({'success': True, 'workouts': result})

@off_season.route('/off-season/manage-exercises/<int:workout_id>')
@login_required
def manage_exercises(workout_id):
    """Manage exercises for a workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    exercises = OffSeasonExercise.query.filter_by(
        workout_id=workout_id
    ).order_by(OffSeasonExercise.order).all()
    
    return render_template('off_season/manage_exercises.html', workout=workout, exercises=exercises)

@off_season.route('/off-season/add-exercise/<int:workout_id>', methods=['POST'])
@login_required
def add_exercise(workout_id):
    """Add a new exercise to a workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    workout = OffSeasonWorkout.query.filter_by(
        id=workout_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Get the highest order value
        max_order = db.session.query(func.max(OffSeasonExercise.order)).filter_by(
            workout_id=workout_id
        ).scalar() or 0
        
        # Create new exercise
        exercise = OffSeasonExercise(
            name=request.form.get('name'),
            description=request.form.get('description'),
            sets=request.form.get('sets'),
            reps=request.form.get('reps'),
            rest=request.form.get('rest'),
            notes=request.form.get('notes'),
            order=max_order + 1,
            workout_id=workout_id,
            team_organization_id=get_current_team_id()
        )
        db.session.add(exercise)
        db.session.commit()
        flash('Exercise added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding exercise: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.manage_exercises', workout_id=workout_id))

@off_season.route('/off-season/edit-exercise/<int:workout_id>/<int:exercise_id>', methods=['POST'])
@login_required
def edit_exercise(workout_id, exercise_id):
    """Edit an existing exercise"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    exercise = OffSeasonExercise.query.filter_by(
        id=exercise_id,
        workout_id=workout_id
    ).first_or_404()
    
    try:
        exercise.name = request.form.get('name')
        exercise.description = request.form.get('description')
        exercise.sets = request.form.get('sets')
        exercise.reps = request.form.get('reps')
        exercise.rest = request.form.get('rest')
        exercise.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Exercise updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating exercise: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.manage_exercises', workout_id=workout_id))

@off_season.route('/off-season/delete-exercise/<int:workout_id>/<int:exercise_id>', methods=['POST'])
@login_required
def delete_exercise(workout_id, exercise_id):
    """Delete an exercise"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    exercise = OffSeasonExercise.query.filter_by(
        id=exercise_id,
        workout_id=workout_id
    ).first_or_404()
    
    try:
        # Delete exercise
        db.session.delete(exercise)
        
        # Reorder remaining exercises
        remaining_exercises = OffSeasonExercise.query.filter_by(
            workout_id=workout_id
        ).order_by(OffSeasonExercise.order).all()
        
        for i, ex in enumerate(remaining_exercises, 1):
            ex.order = i
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@off_season.route('/off-season/reorder-exercise/<int:workout_id>', methods=['POST'])
@login_required
def reorder_exercise(workout_id):
    """Reorder exercises in a workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    data = request.json
    exercise_id = data.get('exercise_id')
    direction = data.get('direction')
    
    exercise = OffSeasonExercise.query.filter_by(
        id=exercise_id,
        workout_id=workout_id
    ).first_or_404()
    
    try:
        current_order = exercise.order
        
        if direction == 'up' and current_order > 1:
            # Swap with the exercise above
            other_exercise = OffSeasonExercise.query.filter_by(
                workout_id=workout_id,
                order=current_order - 1
            ).first()
            
            if other_exercise:
                other_exercise.order = current_order
                exercise.order = current_order - 1
        
        elif direction == 'down':
            # Swap with the exercise below
            other_exercise = OffSeasonExercise.query.filter_by(
                workout_id=workout_id,
                order=current_order + 1
            ).first()
            
            if other_exercise:
                other_exercise.order = current_order
                exercise.order = current_order + 1
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# SMART Goals functionality

# Add model for SMART goals
class OffSeasonGoalTemplate(db.Model):
    __tablename__ = 'off_season_goal_template'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # Physical, Technical, Tactical, Mental, Consistency
    measurement_type = db.Column(db.String(50))  # Numeric, Percentage, Frequency, Binary
    example = db.Column(db.String(255))
    tips = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign keys
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase')
    
    def __repr__(self):
        return f'<OffSeasonGoalTemplate {self.title}>'

class PlayerOffSeasonGoal(db.Model):
    __tablename__ = 'player_off_season_goal'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    status = db.Column(db.String(20), default='Not Started')  # Not Started, In Progress, Completed, Missed
    target_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign key for team organization
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    player = db.relationship('Player')
    phase = db.relationship('OffSeasonPhase')
    
    def __repr__(self):
        return f'<PlayerOffSeasonGoal {self.player.name} - {self.description[:20]}>'

@off_season.route('/off-season/add-goal-template', methods=['POST'])
@login_required
def add_goal_template():
    """Add a new SMART goal template"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    try:
        # Create new goal template
        template = OffSeasonGoalTemplate(
            title=request.form.get('title'),
            description=request.form.get('description'),
            category=request.form.get('category'),
            measurement_type=request.form.get('measurement_type'),
            example=request.form.get('example'),
            tips=request.form.get('tips'),
            phase_id=request.form.get('phase_id', type=int),
            team_organization_id=get_current_team_id()
        )
        db.session.add(template)
        db.session.commit()
        flash('Goal template added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding goal template: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.admin_dashboard'))

@off_season.route('/off-season/edit-goal-template/<int:goal_id>', methods=['GET', 'POST'])
@login_required
def edit_goal_template(goal_id):
    """Edit an existing goal template"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    template = OffSeasonGoalTemplate.query.filter_by(
        id=goal_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    if request.method == 'POST':
        try:
            template.title = request.form.get('title')
            template.description = request.form.get('description')
            template.category = request.form.get('category')
            template.measurement_type = request.form.get('measurement_type')
            template.example = request.form.get('example')
            template.tips = request.form.get('tips')
            template.phase_id = request.form.get('phase_id', type=int)
            
            db.session.commit()
            flash('Goal template updated successfully!', 'success')
            return redirect(url_for('off_season.admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating goal template: {str(e)}', 'danger')
    
    return render_template('off_season/edit_goal_template.html', template=template, phases=phases)

@off_season.route('/off-season/delete-goal-template/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal_template(goal_id):
    """Delete a goal template"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    template = OffSeasonGoalTemplate.query.filter_by(
        id=goal_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Delete template
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@off_season.route('/off-season/get-goal-templates')
@login_required
def get_goal_templates():
    """Get all goal templates"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    templates = OffSeasonGoalTemplate.query.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Format results
    result = []
    for template in templates:
        phase = OffSeasonPhase.query.get(template.phase_id)
        
        result.append({
            'id': template.id,
            'title': template.title,
            'phase_name': phase.name if phase else 'Unknown',
            'category': template.category,
            'measurement_type': template.measurement_type
        })
    
    return jsonify({'success': True, 'goals': result})

@off_season.route('/off-season/my-goals')
@login_required
def my_goals():
    """View player's SMART goals"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    player = current_user.player
    
    # Get phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Get goals grouped by phase
    goals = {}
    for phase in phases:
        phase_goals = PlayerOffSeasonGoal.query.filter_by(
            player_id=player.id,
            phase_id=phase.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        goals[phase.id] = phase_goals
    
    # Get goal templates grouped by phase
    templates = {}
    for phase in phases:
        phase_templates = OffSeasonGoalTemplate.query.filter_by(
            phase_id=phase.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        templates[phase.id] = phase_templates
    
    today = date.today()
    
    return render_template('off_season/player_goals.html',
                           player=player,
                           phases=phases,
                           goals=goals,
                           templates=templates,
                           today=today)

@off_season.route('/off-season/add-player-goal', methods=['POST'])
@login_required
def add_player_goal():
    """Add a new player goal"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    try:
        # Create new goal
        goal = PlayerOffSeasonGoal(
            player_id=current_user.player.id,
            phase_id=request.form.get('phase_id', type=int),
            description=request.form.get('description'),
            category=request.form.get('category'),
            target_date=datetime.strptime(request.form.get('target_date'), '%Y-%m-%d').date(),
            notes=request.form.get('notes'),
            team_organization_id=get_current_team_id()
        )
        db.session.add(goal)
        db.session.commit()
        flash('Goal added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding goal: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.my_goals'))

@off_season.route('/off-season/update-player-goal/<int:goal_id>', methods=['POST'])
@login_required
def update_player_goal(goal_id):
    """Update a player goal"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    goal = PlayerOffSeasonGoal.query.filter_by(
        id=goal_id,
        player_id=current_user.player.id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        goal.description = request.form.get('description')
        goal.notes = request.form.get('notes')
        goal.status = request.form.get('status')
        
        db.session.commit()
        flash('Goal updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating goal: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.my_goals'))

@off_season.route('/off-season/delete-player-goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_player_goal(goal_id):
    """Delete a player goal"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return jsonify({'success': False, 'message': 'Player profile not linked'})
    
    goal = PlayerOffSeasonGoal.query.filter_by(
        id=goal_id,
        player_id=current_user.player.id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Delete goal
        db.session.delete(goal)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@off_season.route('/off-season/add-goal-from-template', methods=['POST'])
@login_required
def add_goal_from_template():
    """Add a player goal from a template"""
    # Check if user has a linked player
    if not hasattr(current_user, 'player') or not current_user.player:
        flash('You need to link your account to a player profile first.', 'warning')
        return redirect(url_for('auth.link_player'))
    
    template_id = request.form.get('template_id', type=int)
    template = OffSeasonGoalTemplate.query.filter_by(
        id=template_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    try:
        # Create goal from template
        value = request.form.get('value')
        description = template.description.replace('{X}', value)
        
        goal = PlayerOffSeasonGoal(
            player_id=current_user.player.id,
            phase_id=request.form.get('phase_id', type=int),
            description=description,
            category=template.category,
            target_date=datetime.strptime(request.form.get('target_date'), '%Y-%m-%d').date(),
            notes=request.form.get('notes'),
            team_organization_id=get_current_team_id()
        )
        db.session.add(goal)
        db.session.commit()
        flash('Goal created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating goal: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.my_goals'))

@off_season.route('/off-season/manage-workouts')
@login_required
def manage_workouts():
    """Admin interface for managing workouts"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Change OffSeasonWorkout.name to OffSeasonWorkout.title
    workouts = OffSeasonWorkout.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonWorkout.phase_id, OffSeasonWorkout.title).all()
    
    return render_template('off_season/manage_workouts.html',
                          phases=phases,
                          workouts=workouts)


@off_season.route('/off-season/manage-all-exercises')
@login_required
def manage_all_exercises():
    """Admin interface for managing exercises across all workouts"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    workouts = OffSeasonWorkout.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonWorkout.phase_id, OffSeasonWorkout.title).all()
    
    # Get all exercises organized by workout
    workout_exercises = {}
    for workout in workouts:
        workout_exercises[workout.id] = OffSeasonExercise.query.filter_by(
            workout_id=workout.id
        ).order_by(OffSeasonExercise.order).all()
    
    return render_template('off_season/manage_all_exercises.html',
                          workouts=workouts,
                          workout_exercises=workout_exercises)

@off_season.route('/off-season/manage-goal-templates')
@login_required
def manage_goal_templates():
    """Admin interface for managing goal templates"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    goal_templates = OffSeasonGoalTemplate.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonGoalTemplate.phase_id, OffSeasonGoalTemplate.title).all()
    
    return render_template('off_season/manage_goal_templates.html',
                          phases=phases,
                          goal_templates=goal_templates)

@off_season.route('/off-season/import-sample-content')
@login_required
def import_sample_content():
    """Page for importing sample content"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    return render_template('off_season/import_content.html')
    """Page for importing sample content"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    return render_template('off_season/import_content.html')

@off_season.route('/off-season/import-sample-workouts', methods=['POST'])
@login_required
def import_sample_workouts():
    """Import sample workouts for each phase"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    # Check if workouts already exist
    existing_workouts = OffSeasonWorkout.query.filter_by(
        team_organization_id=get_current_team_id()
    ).count()
    
    if existing_workouts > 0:
        flash('Workouts already exist. Delete existing workouts before importing samples.', 'warning')
        return redirect(url_for('off_season.admin_dashboard'))
    
    # Get phases
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    if not phases:
        flash('No phases found. Initialize phases before importing workouts.', 'warning')
        return redirect(url_for('off_season.admin_dashboard'))
    
    try:
        # Sample workouts for each phase
        sample_workouts = {
            'Foundation Phase': [
                {
                    'title': 'Basic Strength Circuit',
                    'description': 'A full-body circuit focused on building foundational strength with bodyweight exercises.',
                    'workout_type': 'Strength',
                    'difficulty_level': 'Beginner',
                    'duration': '45-60 minutes',
                    'equipment_needed': 'None required, optional: resistance bands',
                    'instructions': 'Complete 3 rounds of the circuit with minimal rest between exercises and 2-3 minutes rest between rounds.',
                    'exercises': [
                        {
                            'name': 'Push-ups',
                            'description': 'Standard push-up position, lower chest to ground and push back up.',
                            'sets': '3',
                            'reps': '10-15',
                            'rest': '30 sec',
                            'notes': 'Modify on knees if needed.'
                        },
                        {
                            'name': 'Bodyweight Squats',
                            'description': 'Stand with feet shoulder-width apart, lower until thighs are parallel to ground.',
                            'sets': '3',
                            'reps': '15-20',
                            'rest': '30 sec',
                            'notes': 'Focus on depth and keeping chest up.'
                        },
                        {
                            'name': 'Plank',
                            'description': 'Hold proper plank position with straight line from head to heels.',
                            'sets': '3',
                            'reps': '30-60 sec',
                            'rest': '30 sec',
                            'notes': 'Keep core engaged throughout.'
                        },
                        {
                            'name': 'Glute Bridges',
                            'description': 'Lie on back, feet flat on floor, lift hips toward ceiling.',
                            'sets': '3',
                            'reps': '15-20',
                            'rest': '30 sec',
                            'notes': 'Squeeze glutes at top of movement.'
                        },
                        {
                            'name': 'Mountain Climbers',
                            'description': 'In push-up position, alternate bringing knees to chest.',
                            'sets': '3',
                            'reps': '30 sec',
                            'rest': '30 sec',
                            'notes': 'Keep hips stable throughout.'
                        }
                    ]
                },
                {
                    'title': 'Mobility Flow',
                    'description': 'A comprehensive mobility routine targeting all major joints to improve range of motion.',
                    'workout_type': 'Mobility',
                    'difficulty_level': 'Beginner',
                    'duration': '30-40 minutes',
                    'equipment_needed': 'Yoga mat, foam roller (optional)',
                    'instructions': 'Move through each exercise slowly and with control. Hold static stretches for 30-60 seconds.',
                    'exercises': [
                        {
                            'name': 'World\'s Greatest Stretch',
                            'description': 'Lunge forward, place hand on ground, rotate torso upward.',
                            'sets': '2-3',
                            'reps': '5-8 per side',
                            'rest': '15 sec',
                            'notes': 'Focus on thoracic rotation.'
                        },
                        {
                            'name': 'Hip Flexor Stretch',
                            'description': 'Kneeling lunge position, tuck pelvis to stretch hip flexor.',
                            'sets': '2-3',
                            'reps': '30-45 sec per side',
                            'rest': '15 sec',
                            'notes': 'Keep torso upright.'
                        },
                        {
                            'name': 'Shoulder Dislocates',
                            'description': 'Hold band/towel with straight arms, move from front to back of body.',
                            'sets': '2-3',
                            'reps': '10-12',
                            'rest': '30 sec',
                            'notes': 'Use wider grip if needed.'
                        },
                        {
                            'name': 'Ankle Mobility',
                            'description': 'In lunge position near wall, drive knee forward over toe.',
                            'sets': '2-3',
                            'reps': '10-12 per side',
                            'rest': '15 sec',
                            'notes': 'Keep heel down throughout.'
                        },
                        {
                            'name': 'Cat-Cow',
                            'description': 'On hands and knees, alternate between arching and rounding back.',
                            'sets': '2-3',
                            'reps': '10-12 cycles',
                            'rest': '30 sec',
                            'notes': 'Move with breath - inhale for cow, exhale for cat.'
                        }
                    ]
                }
            ],
            'Strength Development Phase': [
                {
                    'title': 'Lower Body Power',
                    'description': 'A focused lower body workout to develop strength and power in the legs and posterior chain.',
                    'workout_type': 'Strength',
                    'difficulty_level': 'Intermediate',
                    'duration': '60-75 minutes',
                    'equipment_needed': 'Barbell, dumbbells, squat rack',
                    'instructions': 'Warm up thoroughly before starting. Rest 2-3 minutes between main lift sets, 60-90 seconds for accessory exercises.',
                    'exercises': [
                        {
                            'name': 'Back Squat',
                            'description': 'Barbell on upper back, squat until thighs are parallel to ground or lower.',
                            'sets': '5',
                            'reps': '5',
                            'rest': '2-3 min',
                            'notes': 'Focus on form over weight. Drive through heels.'
                        },
                        {
                            'name': 'Romanian Deadlift',
                            'description': 'Hinge at hips with soft knees, lower bar along legs until stretch in hamstrings.',
                            'sets': '3',
                            'reps': '8-10',
                            'rest': '90 sec',
                            'notes': 'Keep back flat and bar close to legs.'
                        },
                        {
                            'name': 'Walking Lunges',
                            'description': 'Step forward into lunge position, alternate legs.',
                            'sets': '3',
                            'reps': '10-12 per leg',
                            'rest': '60 sec',
                            'notes': 'Can be done with dumbbells for added resistance.'
                        },
                        {
                            'name': 'Calf Raises',
                            'description': 'Stand on edge of step, raise up onto toes and lower heels below step.',
                            'sets': '3',
                            'reps': '15-20',
                            'rest': '45 sec',
                            'notes': 'Pause at top of movement.'
                        },
                        {
                            'name': 'Plank with Leg Lift',
                            'description': 'Hold plank position while alternating leg lifts.',
                            'sets': '3',
                            'reps': '30-45 sec',
                            'rest': '45 sec',
                            'notes': 'Keep hips stable during leg lifts.'
                        }
                    ]
                }
            ],
            'Recovery/Maintenance Phase': [
                {
                    'title': 'Active Recovery Session',
                    'description': 'A low-intensity workout focused on blood flow, mobility, and recovery.',
                    'workout_type': 'Recovery',
                    'difficulty_level': 'Beginner',
                    'duration': '30-45 minutes',
                    'equipment_needed': 'Foam roller, resistance band, yoga mat',
                    'instructions': 'Move through exercises at a comfortable pace. Focus on quality movement and breathing.',
                    'exercises': [
                        {
                            'name': 'Foam Rolling (Major Muscle Groups)',
                            'description': 'Roll slowly over quads, hamstrings, calves, upper back, and lats.',
                            'sets': '1',
                            'reps': '60-90 sec per area',
                            'rest': 'None',
                            'notes': 'Pause on tender spots for 20-30 seconds.'
                        },
                        {
                            'name': 'Dynamic Stretching Circuit',
                            'description': 'Leg swings, arm circles, torso rotations, hip circles.',
                            'sets': '2',
                            'reps': '10-12 per movement',
                            'rest': 'Minimal',
                            'notes': 'Move through full range of motion.'
                        },
                        {
                            'name': 'Light Bodyweight Circuit',
                            'description': 'Air squats, push-ups, supermans, and bird-dogs.',
                            'sets': '2',
                            'reps': '10-15 per exercise',
                            'rest': '30 sec',
                            'notes': 'Focus on form and controlled movement.'
                        },
                        {
                            'name': 'Walking',
                            'description': 'Brisk walking at comfortable pace.',
                            'sets': '1',
                            'reps': '10-15 minutes',
                            'rest': 'None',
                            'notes': 'Focus on posture and breathing.'
                        }
                    ]
                }
            ],
            'Power/Speed Phase': [
                {
                    'title': 'Plyometric Power Development',
                    'description': 'A high-intensity workout focused on explosive power and quick movements.',
                    'workout_type': 'Power',
                    'difficulty_level': 'Advanced',
                    'duration': '45-60 minutes',
                    'equipment_needed': 'Plyo box, cones, medicine ball',
                    'instructions': 'Thorough warm-up is essential. Full recovery between sets is crucial for quality. Stop if form deteriorates.',
                    'exercises': [
                        {
                            'name': 'Box Jumps',
                            'description': 'Jump explosively onto box, step down carefully.',
                            'sets': '4-5',
                            'reps': '5-6',
                            'rest': '90-120 sec',
                            'notes': 'Focus on explosive takeoff and soft landing.'
                        },
                        {
                            'name': 'Depth Jumps',
                            'description': 'Step off box, land softly, immediately jump vertically.',
                            'sets': '4',
                            'reps': '5',
                            'rest': '2 min',
                            'notes': 'Minimize ground contact time.'
                        },
                        {
                            'name': 'Lateral Bounds',
                            'description': 'Jump sideways from one leg to the other, covering distance.',
                            'sets': '3',
                            'reps': '6-8 per side',
                            'rest': '90 sec',
                            'notes': 'Land softly with knee aligned over foot.'
                        },
                        {
                            'name': 'Medicine Ball Throws',
                            'description': 'Explosive chest pass against wall or with partner.',
                            'sets': '3',
                            'reps': '8-10',
                            'rest': '60 sec',
                            'notes': 'Generate power from legs and core.'
                        },
                        {
                            'name': 'Sprint-Deceleration',
                            'description': '10-yard sprint followed by controlled deceleration.',
                            'sets': '5',
                            'reps': '3',
                            'rest': '90 sec',
                            'notes': 'Focus on proper deceleration mechanics.'
                        }
                    ]
                }
            ],
            'Integration Phase': [
                {
                    'title': 'Game Simulation Circuit',
                    'description': 'A sport-specific workout that mimics the demands of ultimate frisbee gameplay.',
                    'workout_type': 'Sport-Specific',
                    'difficulty_level': 'Advanced',
                    'duration': '60-75 minutes',
                    'equipment_needed': 'Cones, discs, agility ladder',
                    'instructions': 'Complete each station for the prescribed time, then move to the next with minimal rest. Rest 2-3 minutes between full circuits.',
                    'exercises': [
                        {
                            'name': 'Cutting Pattern Drill',
                            'description': 'Set up cones in zigzag pattern, sprint to each cone with sharp cuts.',
                            'sets': '3',
                            'reps': '45 sec work',
                            'rest': '30 sec',
                            'notes': 'Focus on planting outside foot and explosive direction change.'
                        },
                        {
                            'name': 'Throwing Accuracy Under Fatigue',
                            'description': '5 burpees followed by 5 throws to target at different distances.',
                            'sets': '3',
                            'reps': '60 sec work',
                            'rest': '30 sec',
                            'notes': 'Maintain throwing mechanics despite fatigue.'
                        },
                        {
                            'name': 'Handler Defensive Footwork',
                            'description': 'Lateral shuffles with quick direction changes on command.',
                            'sets': '3',
                            'reps': '45 sec work',
                            'rest': '30 sec',
                            'notes': 'Stay low in athletic stance.'
                        },
                        {
                            'name': 'Jump and Catch',
                            'description': 'Sprint 5 yards, jump and catch disc at highest point.',
                            'sets': '3',
                            'reps': '8-10 reps',
                            'rest': '30 sec',
                            'notes': 'Focus on timing jump with disc arrival.'
                        },
                        {
                            'name': 'Conditioning Shuttle',
                            'description': 'Set up 20-yard shuttle, sprint back and forth with disc handling.',
                            'sets': '3',
                            'reps': '60 sec work',
                            'rest': '30 sec',
                            'notes': 'Maintain disc control while changing directions.'
                        }
                    ]
                }
            ]
        }
        
        # Create workouts for each phase
        for phase in phases:
            phase_name = phase.name
            if phase_name in sample_workouts:
                for workout_data in sample_workouts[phase_name]:
                    # Create workout
                    workout = OffSeasonWorkout(
                        title=workout_data['title'],
                        description=workout_data['description'],
                        workout_type=workout_data['workout_type'],
                        instructions=workout_data['instructions'],
                        duration=workout_data['duration'],
                        equipment_needed=workout_data['equipment_needed'],
                        difficulty_level=workout_data['difficulty_level'],
                        phase_id=phase.id,
                        team_organization_id=get_current_team_id()
                    )
                    db.session.add(workout)
                    db.session.flush()  # Get workout ID
                    
                    # Create exercises
                    for i, exercise_data in enumerate(workout_data['exercises'], 1):
                        exercise = OffSeasonExercise(
                            name=exercise_data['name'],
                            description=exercise_data['description'],
                            sets=exercise_data['sets'],
                            reps=exercise_data['reps'],
                            rest=exercise_data['rest'],
                            notes=exercise_data['notes'],
                            order=i,
                            workout_id=workout.id,
                            team_organization_id=get_current_team_id()
                        )
                        db.session.add(exercise)
        
        # Create sample goal templates
        goal_templates = [
            {
                'phase_name': 'Foundation Phase',
                'templates': [
                    {
                        'title': 'Mobility Improvement',
                        'description': 'Increase hip mobility range of motion by {X} by the end of the Foundation Phase',
                        'category': 'Physical',
                        'measurement_type': 'Numeric',
                        'example': 'Increase hip mobility range of motion by 20% by the end of the Foundation Phase',
                        'tips': 'Measure using the Thomas test or similar assessment. Perform mobility work 4-5 times per week.'
                    },
                    {
                        'title': 'Consistency Goal',
                        'description': 'Complete {X} Foundation Phase workouts per week',
                        'category': 'Consistency',
                        'measurement_type': 'Frequency',
                        'example': 'Complete 3 Foundation Phase workouts per week',
                        'tips': 'Schedule workouts in advance and track completion in a training log.'
                    }
                ]
            },
            {
                'phase_name': 'Strength Development Phase',
                'templates': [
                    {
                        'title': 'Strength Benchmark',
                        'description': 'Increase squat weight by {X} pounds by the end of the Strength Development Phase',
                        'category': 'Physical',
                        'measurement_type': 'Numeric',
                        'example': 'Increase squat weight by 30 pounds by the end of the Strength Development Phase',
                        'tips': 'Focus on proper form and progressive overload. Ensure adequate recovery between strength sessions.'
                    },
                    {
                        'title': 'Core Strength',
                        'description': 'Increase plank hold time to {X} seconds by the end of the Strength Development Phase',
                        'category': 'Physical',
                        'measurement_type': 'Numeric',
                        'example': 'Increase plank hold time to 120 seconds by the end of the Strength Development Phase',
                        'tips': 'Practice planks 3-4 times per week with proper form. Add small increments of time each week.'
                    }
                ]
            },
            {
                'phase_name': 'Power/Speed Phase',
                'templates': [
                    {
                        'title': 'Vertical Jump',
                        'description': 'Increase vertical jump height by {X} inches by the end of the Power/Speed Phase',
                        'category': 'Physical',
                        'measurement_type': 'Numeric',
                        'example': 'Increase vertical jump height by 2 inches by the end of the Power/Speed Phase',
                        'tips': 'Focus on plyometric exercises and proper landing mechanics. Measure consistently using the same method.'
                    },
                    {
                        'title': 'Sprint Speed',
                        'description': 'Reduce 40-yard sprint time by {X} seconds by the end of the Power/Speed Phase',
                        'category': 'Physical',
                        'measurement_type': 'Numeric',
                        'example': 'Reduce 40-yard sprint time by 0.3 seconds by the end of the Power/Speed Phase',
                        'tips': 'Work on sprint technique and acceleration mechanics. Ensure full recovery between sprint sessions.'
                    }
                ]
            },
            {
                'phase_name': 'Integration Phase',
                'templates': [
                    {
                        'title': 'Throwing Accuracy',
                        'description': 'Achieve {X}% accuracy on 30-yard hucks by the end of the Integration Phase',
                        'category': 'Technical',
                        'measurement_type': 'Percentage',
                        'example': 'Achieve 80% accuracy on 30-yard hucks by the end of the Integration Phase',
                        'tips': 'Practice throwing in various weather conditions. Track accuracy over multiple sessions.'
                    },
                    {
                        'title': 'Defensive Footwork',
                        'description': 'Reduce time in defensive footwork drill by {X} seconds by the end of the Integration Phase',
                        'category': 'Tactical',
                        'measurement_type': 'Numeric',
                        'example': 'Reduce time in defensive footwork drill by 2 seconds by the end of the Integration Phase',
                        'tips': 'Focus on proper defensive stance and efficient movement patterns. Practice footwork drills 2-3 times per week.'
                    }
                ]
            }
        ]
        
        # Create goal templates
        for template_group in goal_templates:
            phase = OffSeasonPhase.query.filter_by(
                name=template_group['phase_name'],
                team_organization_id=get_current_team_id()
            ).first()
            
            if phase:
                for template_data in template_group['templates']:
                    template = OffSeasonGoalTemplate(
                        title=template_data['title'],
                        description=template_data['description'],
                        category=template_data['category'],
                        measurement_type=template_data['measurement_type'],
                        example=template_data['example'],
                        tips=template_data['tips'],
                        phase_id=phase.id,
                        team_organization_id=get_current_team_id()
                    )
                    db.session.add(template)
        
        db.session.commit()
        flash('Sample workouts and goal templates imported successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error importing sample workouts: {str(e)}', 'danger')
    
    return redirect(url_for('off_season.admin_dashboard'))

@off_season.route('/off-season/manage-phases')
@login_required
@admin_required  # If you have this decorator, otherwise use the admin check inside the function
def manage_phases():
    """Admin interface for managing training phases"""
    if not current_user.is_admin:
        flash('You do not have permission to view this page.', 'danger')
        return redirect(url_for('off_season.index'))
    
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    today = date.today()
    
    return render_template('off_season/manage_phases.html', 
                           phases=phases,
                           today=today)

@off_season.route('/off-season/import-sample-goal-templates', methods=['POST'])
@login_required
def import_sample_goal_templates():
    """Import sample goal templates for each phase"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Get current team ID
    team_id = get_current_team_id()
    
    # Get all phases for this team
    phases = OffSeasonPhase.query.filter_by(team_organization_id=team_id).all()
    
    # If no phases exist, create them first
    if not phases:
        flash('Please create training phases first before importing goal templates.', 'warning')
        return redirect(url_for('off_season.manage_phases'))
    
    # Create a dictionary to map phase names to IDs
    phase_map = {phase.name.lower(): phase.id for phase in phases}
    
    # Sample goal templates for each phase
    sample_templates = [
        # Foundation Phase
        {
            'phase_name': 'foundation',
            'templates': [
                {
                    'title': 'Establish Consistent Training Routine',
                    'description': 'Develop a consistent training schedule to build a strong foundation.',
                    'category': 'Habit',
                    'measurement_type': 'Frequency',
                    'target_value': '4 sessions per week'
                },
                {
                    'title': 'Improve Core Stability',
                    'description': 'Strengthen core muscles to improve overall stability and prevent injuries.',
                    'category': 'Physical',
                    'measurement_type': 'Time',
                    'target_value': '3 minutes plank hold'
                },
                {
                    'title': 'Develop Aerobic Base',
                    'description': 'Build cardiovascular endurance through consistent aerobic training.',
                    'category': 'Physical',
                    'measurement_type': 'Distance',
                    'target_value': '5km continuous run'
                }
            ]
        },
        # Strength Phase
        {
            'phase_name': 'strength',
            'templates': [
                {
                    'title': 'Increase Lower Body Strength',
                    'description': 'Build leg strength to improve jumping and cutting abilities.',
                    'category': 'Physical',
                    'measurement_type': 'Weight',
                    'target_value': 'Squat 1.5x bodyweight'
                },
                {
                    'title': 'Improve Upper Body Power',
                    'description': 'Develop throwing power through upper body strength training.',
                    'category': 'Physical',
                    'measurement_type': 'Repetitions',
                    'target_value': '10 pull-ups with proper form'
                },
                {
                    'title': 'Enhance Throwing Mechanics',
                    'description': 'Refine throwing technique while building strength.',
                    'category': 'Skill',
                    'measurement_type': 'Accuracy',
                    'target_value': '80% completion rate at 40 yards'
                }
            ]
        },
        # Recovery Phase
        {
            'phase_name': 'recovery',
            'templates': [
                {
                    'title': 'Improve Sleep Quality',
                    'description': 'Establish consistent sleep patterns to enhance recovery.',
                    'category': 'Lifestyle',
                    'measurement_type': 'Time',
                    'target_value': '8 hours of quality sleep per night'
                },
                {
                    'title': 'Increase Flexibility',
                    'description': 'Improve range of motion through dedicated stretching routines.',
                    'category': 'Physical',
                    'measurement_type': 'Range',
                    'target_value': 'Touch toes with straight legs'
                },
                {
                    'title': 'Develop Mindfulness Practice',
                    'description': 'Incorporate meditation to improve mental recovery and focus.',
                    'category': 'Mental',
                    'measurement_type': 'Time',
                    'target_value': '10 minutes daily meditation'
                }
            ]
        },
        # Power/Speed Phase
        {
            'phase_name': 'power/speed',
            'templates': [
                {
                    'title': 'Improve Sprint Speed',
                    'description': 'Enhance acceleration and top speed for field coverage.',
                    'category': 'Physical',
                    'measurement_type': 'Time',
                    'target_value': 'Sub-3 second 20-yard dash'
                },
                {
                    'title': 'Develop Explosive Jumping',
                    'description': 'Build vertical leap for defensive blocks and offensive skies.',
                    'category': 'Physical',
                    'measurement_type': 'Height',
                    'target_value': 'Increase vertical jump by 3 inches'
                },
                {
                    'title': 'Enhance Cutting Agility',
                    'description': 'Improve change of direction speed for better cutting on the field.',
                    'category': 'Skill',
                    'measurement_type': 'Time',
                    'target_value': 'Complete 5-10-5 drill in under 5 seconds'
                }
            ]
        },
        # Integration Phase
        {
            'phase_name': 'integration',
            'templates': [
                {
                    'title': 'Combine Skills Under Fatigue',
                    'description': 'Maintain skill execution while physically tired.',
                    'category': 'Skill',
                    'measurement_type': 'Completion Rate',
                    'target_value': '70% throw completion after sprint intervals'
                },
                {
                    'title': 'Game-Specific Conditioning',
                    'description': 'Build stamina for full-game performance.',
                    'category': 'Physical',
                    'measurement_type': 'Time',
                    'target_value': 'Complete 10 full-field sprints with 30-second rest'
                },
                {
                    'title': 'Position-Specific Skills',
                    'description': 'Refine skills specific to your playing position.',
                    'category': 'Skill',
                    'measurement_type': 'Performance',
                    'target_value': 'Master 3 position-specific drills'
                }
            ]
        }
    ]
    
    # Import templates
    templates_added = 0
    
    for phase_data in sample_templates:
        phase_name = phase_data['phase_name'].lower()
        
        # Find matching phase ID
        phase_id = None
        for name, id in phase_map.items():
            if phase_name in name or name in phase_name:
                phase_id = id
                break
        
        if not phase_id:
            continue
            
        # Add templates for this phase
        for template_data in phase_data['templates']:
            template = OffSeasonGoalTemplate(
                title=template_data['title'],
                description=template_data['description'],
                category=template_data['category'],
                measurement_type=template_data['measurement_type'],
                example=template_data['target_value'],  # Change to example
                tips="",  # Add empty tips if needed
                phase_id=phase_id,
                team_organization_id=team_id
            )
            db.session.add(template)
            templates_added += 1
    
    db.session.commit()
    
    flash(f'Successfully imported {templates_added} goal templates!', 'success')
    return redirect(url_for('off_season.admin_dashboard'))

@off_season.route('/off-season/import-all-sample-content', methods=['POST'])
@login_required
def import_all_sample_content():
    """Import all sample content (workouts and goal templates)"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Import workouts
    import_sample_workouts()
    
    # Import goal templates
    import_sample_goal_templates()
    
    flash('All sample content has been imported successfully!', 'success')
    return redirect(url_for('off_season.admin_dashboard'))

from flask_wtf import FlaskForm

# Create a simple form class just for CSRF protection
class ScheduleTemplateForm(FlaskForm):
    pass

@off_season.route('/off-season/edit-schedule-template/<int:phase_id>/<string:template_type>', methods=['GET', 'POST'])
@login_required
@admin_required  # If you have this decorator
def edit_schedule_template(phase_id, template_type):
    """Edit or create a weekly schedule template"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.index'))
    
    # Create a form instance for CSRF protection
    form = ScheduleTemplateForm()
    
    phase = OffSeasonPhase.query.filter_by(
        id=phase_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Check if template exists
    template = WeeklyScheduleTemplate.query.filter_by(
        phase_id=phase_id,
        template_type=template_type,
        team_organization_id=get_current_team_id()
    ).first()
    
    # If no template exists, create a new one
    if not template:
        template = WeeklyScheduleTemplate(
            phase_id=phase_id,
            template_type=template_type,
            team_organization_id=get_current_team_id()
        )
        db.session.add(template)
        db.session.commit()
        flash(f'New {template_type} schedule template created. Please fill in the details.', 'info')
    
    # Use validate_on_submit() to check if the form was submitted and valid (includes CSRF check)
    if form.validate_on_submit():
        try:
            # Update template with form data
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                setattr(template, f'{day}_morning', request.form.get(f'{day}_morning', ''))
                setattr(template, f'{day}_evening', request.form.get(f'{day}_evening', ''))
                setattr(template, f'{day}_duration', request.form.get(f'{day}_duration', ''))
                setattr(template, f'{day}_description', request.form.get(f'{day}_description', ''))
            
            db.session.commit()
            flash(f'{template_type.capitalize()} schedule template updated successfully!', 'success')
            return redirect(url_for('off_season.phase_detail', phase_id=phase_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating template: {str(e)}', 'danger')
    
    return render_template('off_season/edit_schedule_template.html', 
                          phase=phase, 
                          template=template,
                          template_type=template_type,
                          form=form)  # Pass the form to the template

@off_season.route('/off-season/add-workout-form')
@login_required
def add_workout_form():
    """Display the form to add a new workout"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('off_season.admin_dashboard'))
    
    # Get phases for the form
    phases = OffSeasonPhase.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OffSeasonPhase.start_date).all()
    
    # Pre-select phase if provided in query parameter
    selected_phase_id = request.args.get('phase_id', type=int)
    
    return render_template('off_season/add_workout.html', phases=phases, selected_phase_id=selected_phase_id)
