# app/routes/off_season.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models.off_season import (
    OffSeasonPhase, PhaseSchedule, ScheduleSession, WorkoutPlan, 
    UserSessionCompletion, SMARTGoal, TrainingCategory, TrainingLevel, ScheduleType,
    PhaseMetric
)
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.player import Player
from app.utils.utils import admin_required
from sqlalchemy import func, and_
from datetime import datetime, timedelta, date
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SubmitField, SelectField, DateField, 
    IntegerField, FloatField, BooleanField, SelectMultipleField
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange
import markdown

bp = Blueprint('off_season', __name__, url_prefix='/off-season')

# Helper function to get current team ID
def get_current_team_id():
    """Get the current team ID based on user role."""
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

# Forms
class PhaseForm(FlaskForm):
    name = StringField('Phase Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    primary_focus = StringField('Primary Focus', validators=[DataRequired(), Length(max=100)])
    training_emphasis = StringField('Training Emphasis', validators=[DataRequired(), Length(max=100)])
    volume_intensity = StringField('Volume/Intensity', validators=[DataRequired(), Length(max=100)])
    key_outcome = StringField('Key Outcome', validators=[DataRequired(), Length(max=200)])
    order = IntegerField('Order', validators=[Optional()])
    submit = SubmitField('Save Phase')

class ScheduleForm(FlaskForm):
    schedule_type = SelectField('Schedule Type', choices=[
        (ScheduleType.STANDARD.value, 'Standard'),
        (ScheduleType.MINIMAL.value, 'Minimal'),
        (ScheduleType.HIGH_VOLUME.value, 'High Volume')
    ], validators=[DataRequired()])
    submit = SubmitField('Save Schedule')

class SessionForm(FlaskForm):
    day_of_week = SelectField('Day of Week', choices=[
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday')
    ], coerce=int, validators=[DataRequired()])
    training_focus = StringField('Training Focus', validators=[DataRequired(), Length(max=100)])
    duration_minutes = IntegerField('Duration (minutes)', validators=[DataRequired(), NumberRange(min=1)])
    description = TextAreaField('Description', validators=[Optional()])
    workout_plans = SelectMultipleField('Workout Plans', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Session')

class WorkoutPlanForm(FlaskForm):
    name = StringField('Workout Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    category = SelectField('Category', choices=[
        (TrainingCategory.STRENGTH.value, 'Strength'),
        (TrainingCategory.SKILLS.value, 'Skills'),
        (TrainingCategory.CONDITIONING.value, 'Conditioning')
    ], validators=[DataRequired()])
    level = SelectField('Level', choices=[
        (TrainingLevel.BEGINNER.value, 'Beginner'),
        (TrainingLevel.INTERMEDIATE.value, 'Intermediate'),
        (TrainingLevel.ADVANCED.value, 'Advanced')
    ], validators=[DataRequired()])
    content = TextAreaField('Workout Content (Markdown)', validators=[DataRequired()])
    submit = SubmitField('Save Workout Plan')

class PhaseMetricForm(FlaskForm):
    metric_id = SelectField('Fitness Metric', coerce=int, validators=[DataRequired()])
    target_value = FloatField('Target Value', validators=[Optional()])
    submit = SubmitField('Add Metric')

class SMARTGoalForm(FlaskForm):
    title = StringField('Goal Title', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    specific = TextAreaField('Specific: What exactly will be accomplished?', validators=[DataRequired()])
    measurable = TextAreaField('Measurable: How will progress be measured?', validators=[DataRequired()])
    achievable = TextAreaField('Achievable: Is it realistic?', validators=[DataRequired()])
    relevant = TextAreaField('Relevant: Why is this goal important?', validators=[DataRequired()])
    time_bound = TextAreaField('Time-bound: When will it be accomplished?', validators=[DataRequired()])
    target_date = DateField('Target Date', validators=[DataRequired()])
    category = SelectField('Category', choices=[
        ('Fitness', 'Fitness'),
        ('Skills', 'Skills'),
        ('Mental', 'Mental'),
        ('Team', 'Team'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    submit = SubmitField('Save Goal')

class SessionCompletionForm(FlaskForm):
    notes = TextAreaField('Notes', validators=[Optional()])
    rating = SelectField('Rating', choices=[
        (1, '1 - Poor'),
        (2, '2 - Below Average'),
        (3, '3 - Average'),
        (4, '4 - Good'),
        (5, '5 - Excellent')
    ], coerce=int, validators=[Optional()])
    submit = SubmitField('Mark as Completed')

# Routes
@bp.route('/')
@login_required
def index():
    """Main off-season dashboard"""
    team_id = get_current_team_id()
    
    # Get all phases ordered by start date
    phases = OffSeasonPhase.query.filter_by(team_organization_id=team_id).order_by(OffSeasonPhase.start_date).all()
    
    # Find the current phase
    today = date.today()
    current_phase = None
    for phase in phases:
        if phase.start_date <= today <= phase.end_date:
            current_phase = phase
            break
    
    # If no current phase, find the next upcoming phase
    if not current_phase and phases:
        upcoming_phases = [p for p in phases if p.start_date > today]
        if upcoming_phases:
            current_phase = min(upcoming_phases, key=lambda p: p.start_date)
    
    # Get user's preferred schedule type (default to standard)
    preferred_schedule_type = ScheduleType.STANDARD
    
    # Get user's SMART goals
    goals = SMARTGoal.query.filter_by(
        user_id=current_user.id,
        team_organization_id=team_id,
        completed=False
    ).order_by(SMARTGoal.target_date).all()
    
    # Get user's completed sessions in the last 30 days
    thirty_days_ago = today - timedelta(days=30)
    completed_sessions = UserSessionCompletion.query.filter(
        UserSessionCompletion.user_id == current_user.id,
        UserSessionCompletion.team_organization_id == team_id,
        UserSessionCompletion.completed_date >= thirty_days_ago
    ).all()
    
    # Get today's schedule if current phase exists
    today_schedule = None
    if current_phase:
        # Find the schedule for the user's preferred type
        schedule = PhaseSchedule.query.filter_by(
            phase_id=current_phase.id,
            schedule_type=preferred_schedule_type,
            team_organization_id=team_id
        ).first()
        
        if schedule:
            # Get today's session
            today_day_of_week = today.weekday()  # 0=Monday, 6=Sunday
            today_session = ScheduleSession.query.filter_by(
                schedule_id=schedule.id,
                day_of_week=today_day_of_week,
                team_organization_id=team_id
            ).first()
            
            if today_session:
                # Check if user has completed this session today
                completion = UserSessionCompletion.query.filter_by(
                    user_id=current_user.id,
                    session_id=today_session.id,
                    completed_date=today,
                    team_organization_id=team_id
                ).first()
                
                today_schedule = {
                    'session': today_session,
                    'completed': completion is not None
                }
    
    return render_template(
        'off_season/index.html',
        phases=phases,
        current_phase=current_phase,
        goals=goals,
        completed_sessions=completed_sessions,
        today_schedule=today_schedule,
        today=today  # Add this line
    )

@bp.route('/phases')
@login_required
@admin_required
def phases():
    """List all phases"""
    team_id = get_current_team_id()
    phases = OffSeasonPhase.query.filter_by(team_organization_id=team_id).order_by(OffSeasonPhase.start_date).all()
    return render_template('off_season/phases.html', phases=phases)

@bp.route('/phases/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_phase():
    """Add a new phase"""
    team_id = get_current_team_id()
    form = PhaseForm()
    
    if form.validate_on_submit():
        phase = OffSeasonPhase(
            name=form.name.data,
            description=form.description.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            primary_focus=form.primary_focus.data,
            training_emphasis=form.training_emphasis.data,
            volume_intensity=form.volume_intensity.data,
            key_outcome=form.key_outcome.data,
            order=form.order.data or 0,
            team_organization_id=team_id
        )
        
        db.session.add(phase)
        db.session.commit()
        
        flash(f'Phase "{phase.name}" added successfully!', 'success')
        return redirect(url_for('off_season.phases'))
    
    return render_template('off_season/phase_form.html', form=form, title='Add Phase')

@bp.route('/phases/<int:phase_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_phase(phase_id):
    """Edit an existing phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    form = PhaseForm(obj=phase)
    
    if form.validate_on_submit():
        phase.name = form.name.data
        phase.description = form.description.data
        phase.start_date = form.start_date.data
        phase.end_date = form.end_date.data
        phase.primary_focus = form.primary_focus.data
        phase.training_emphasis = form.training_emphasis.data
        phase.volume_intensity = form.volume_intensity.data
        phase.key_outcome = form.key_outcome.data
        phase.order = form.order.data or 0
        
        db.session.commit()
        
        flash(f'Phase "{phase.name}" updated successfully!', 'success')
        return redirect(url_for('off_season.phases'))
    
    return render_template('off_season/phase_form.html', form=form, phase=phase, title='Edit Phase')

@bp.route('/phases/<int:phase_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_phase(phase_id):
    """Delete a phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    
    db.session.delete(phase)
    db.session.commit()
    
    flash(f'Phase "{phase.name}" deleted successfully!', 'success')
    return redirect(url_for('off_season.phases'))

@bp.route('/phases/<int:phase_id>')
@login_required
def view_phase(phase_id):
    """View a specific phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    
    # Get schedules for this phase
    schedules = PhaseSchedule.query.filter_by(phase_id=phase.id, team_organization_id=team_id).all()
    
    # Get workout plans for this phase
    workout_plans = WorkoutPlan.query.filter_by(phase_id=phase.id, team_organization_id=team_id).all()
    
    # Get recommended metrics for this phase
    metrics = PhaseMetric.query.filter_by(phase_id=phase.id, team_organization_id=team_id).all()
    
    return render_template(
        'off_season/view_phase.html',
        phase=phase,
        schedules=schedules,
        workout_plans=workout_plans,
        metrics=metrics
    )

@bp.route('/phases/<int:phase_id>/schedules/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_schedule(phase_id):
    """Add a new schedule to a phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    form = ScheduleForm()
    
    if form.validate_on_submit():
        schedule_type = ScheduleType(form.schedule_type.data)
        
        # Check if this schedule type already exists for this phase
        existing = PhaseSchedule.query.filter_by(
            phase_id=phase.id,
            schedule_type=schedule_type,
            team_organization_id=team_id
        ).first()
        
        if existing:
            flash(f'A {schedule_type.value} schedule already exists for this phase!', 'danger')
            return redirect(url_for('off_season.view_phase', phase_id=phase.id))
        
        schedule = PhaseSchedule(
            phase_id=phase.id,
            schedule_type=schedule_type,
            team_organization_id=team_id
        )
        
        db.session.add(schedule)
        db.session.commit()
        
        flash(f'{schedule_type.value.capitalize()} schedule added successfully!', 'success')
        return redirect(url_for('off_season.view_schedule', schedule_id=schedule.id))
    
    return render_template('off_season/schedule_form.html', form=form, phase=phase)

@bp.route('/schedules/<int:schedule_id>')
@login_required
def view_schedule(schedule_id):
    """View a specific schedule"""
    team_id = get_current_team_id()
    schedule = PhaseSchedule.query.filter_by(id=schedule_id, team_organization_id=team_id).first_or_404()
    phase = schedule.phase
    
    # Get sessions for this schedule
    sessions = ScheduleSession.query.filter_by(schedule_id=schedule.id, team_organization_id=team_id).order_by(ScheduleSession.day_of_week).all()
    
    # Organize sessions by day of week
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    sessions_by_day = {i: None for i in range(7)}
    
    for session in sessions:
        sessions_by_day[session.day_of_week] = session
    

    return render_template(
        'off_season/view_schedule.html',
        schedule=schedule,
        phase=phase,
        sessions=sessions,
        sessions_by_day=sessions_by_day,
        days=days,
        enumerated_days=enumerate(days)  # Add this line
    )

@bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_schedule(schedule_id):
    """Delete a schedule"""
    team_id = get_current_team_id()
    schedule = PhaseSchedule.query.filter_by(id=schedule_id, team_organization_id=team_id).first_or_404()
    phase_id = schedule.phase_id
    
    db.session.delete(schedule)
    db.session.commit()
    
    flash(f'{schedule.schedule_type.value.capitalize()} schedule deleted successfully!', 'success')
    return redirect(url_for('off_season.view_phase', phase_id=phase_id))

@bp.route('/schedules/<int:schedule_id>/sessions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_session(schedule_id):
    """Add a new session to a schedule"""
    team_id = get_current_team_id()
    schedule = PhaseSchedule.query.filter_by(id=schedule_id, team_organization_id=team_id).first_or_404()
    form = SessionForm()
    
    # Populate workout plans choices
    workout_plans = WorkoutPlan.query.filter_by(
        phase_id=schedule.phase_id,
        team_organization_id=team_id
    ).all()
    form.workout_plans.choices = [(wp.id, f"{wp.name} ({wp.category.value.capitalize()} - {wp.level.value.capitalize()})") for wp in workout_plans]
    
    if form.validate_on_submit():
        # Check if a session already exists for this day
        existing = ScheduleSession.query.filter_by(
            schedule_id=schedule.id,
            day_of_week=form.day_of_week.data,
            team_organization_id=team_id
        ).first()
        
        if existing:
            flash(f'A session already exists for this day!', 'danger')
            return redirect(url_for('off_season.view_schedule', schedule_id=schedule.id))
        
        session = ScheduleSession(
            schedule_id=schedule.id,
            day_of_week=form.day_of_week.data,
            training_focus=form.training_focus.data,
            duration_minutes=form.duration_minutes.data,
            description=form.description.data,
            team_organization_id=team_id
        )
        
        db.session.add(session)
        db.session.flush()  # Get the session ID
        
        # Add workout plans
        if form.workout_plans.data:
            for wp_id in form.workout_plans.data:
                wp = WorkoutPlan.query.get(wp_id)
                if wp and wp.team_organization_id == team_id:
                    session.workout_plans.append(wp)
        
        db.session.commit()
        
        flash('Session added successfully!', 'success')
        return redirect(url_for('off_season.view_schedule', schedule_id=schedule.id))
    
    return render_template('off_season/session_form.html', form=form, schedule=schedule)


@bp.route('/sessions/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_session(session_id):
    """Edit a session"""
    team_id = get_current_team_id()
    session = ScheduleSession.query.filter_by(id=session_id, team_organization_id=team_id).first_or_404()
    form = SessionForm(obj=session)
    
    # Populate workout plans choices
    workout_plans = WorkoutPlan.query.filter_by(
        phase_id=session.schedule.phase_id,
        team_organization_id=team_id
    ).all()
    form.workout_plans.choices = [(wp.id, f"{wp.name} ({wp.category.value.capitalize()} - {wp.level.value.capitalize()})") for wp in workout_plans]
    
    # Set current workout plans
    if request.method == 'GET':
        form.workout_plans.data = [wp.id for wp in session.workout_plans]
    
    if form.validate_on_submit():
        # Check if moving to a day that already has a session
        if form.day_of_week.data != session.day_of_week:
            existing = ScheduleSession.query.filter_by(
                schedule_id=session.schedule_id,
                day_of_week=form.day_of_week.data,
                team_organization_id=team_id
            ).first()
            
            if existing and existing.id != session.id:
                flash(f'A session already exists for this day!', 'danger')
                return redirect(url_for('off_season.view_schedule', schedule_id=session.schedule_id))
        
        session.day_of_week = form.day_of_week.data
        session.training_focus = form.training_focus.data
        session.duration_minutes = form.duration_minutes.data
        session.description = form.description.data
        
        # Update workout plans
        session.workout_plans = []
        if form.workout_plans.data:
            for wp_id in form.workout_plans.data:
                wp = WorkoutPlan.query.get(wp_id)
                if wp and wp.team_organization_id == team_id:
                    session.workout_plans.append(wp)
        
        db.session.commit()
        
        flash('Session updated successfully!', 'success')
        return redirect(url_for('off_season.view_schedule', schedule_id=session.schedule_id))
    
    return render_template('off_season/session_form.html', form=form, session=session)

@bp.route('/sessions/<int:session_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_session(session_id):
    """Delete a session"""
    team_id = get_current_team_id()
    session = ScheduleSession.query.filter_by(id=session_id, team_organization_id=team_id).first_or_404()
    schedule_id = session.schedule_id
    
    db.session.delete(session)
    db.session.commit()
    
    flash('Session deleted successfully!', 'success')
    return redirect(url_for('off_season.view_schedule', schedule_id=schedule_id))

@bp.route('/phases/<int:phase_id>/workouts/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_workout(phase_id):
    """Add a new workout plan to a phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    form = WorkoutPlanForm()
    
    if form.validate_on_submit():
        workout = WorkoutPlan(
            phase_id=phase.id,
            name=form.name.data,
            description=form.description.data,
            category=TrainingCategory(form.category.data),
            level=TrainingLevel(form.level.data),
            content=form.content.data,
            team_organization_id=team_id
        )
        
        db.session.add(workout)
        db.session.commit()
        
        flash(f'Workout plan "{workout.name}" added successfully!', 'success')
        return redirect(url_for('off_season.view_phase', phase_id=phase.id))
    
    return render_template('off_season/workout_form.html', form=form, phase=phase)

@bp.route('/workouts/<int:workout_id>')
@login_required
def view_workout(workout_id):
    """View a specific workout plan"""
    team_id = get_current_team_id()
    workout = WorkoutPlan.query.filter_by(id=workout_id, team_organization_id=team_id).first_or_404()
    
    # Convert markdown content to HTML
    content_html = markdown.markdown(workout.content)
    
    return render_template(
        'off_season/view_workout.html',
        workout=workout,
        content_html=content_html
    )

@bp.route('/workouts/<int:workout_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_workout(workout_id):
    """Edit a workout plan"""
    team_id = get_current_team_id()
    workout = WorkoutPlan.query.filter_by(id=workout_id, team_organization_id=team_id).first_or_404()
    form = WorkoutPlanForm(obj=workout)
    
    if form.validate_on_submit():
        workout.name = form.name.data
        workout.description = form.description.data
        workout.category = TrainingCategory(form.category.data)
        workout.level = TrainingLevel(form.level.data)
        workout.content = form.content.data
        
        db.session.commit()
        
        flash(f'Workout plan "{workout.name}" updated successfully!', 'success')
        return redirect(url_for('off_season.view_workout', workout_id=workout.id))
    
    return render_template('off_season/workout_form.html', form=form, workout=workout)

@bp.route('/workouts/<int:workout_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_workout(workout_id):
    """Delete a workout plan"""
    team_id = get_current_team_id()
    workout = WorkoutPlan.query.filter_by(id=workout_id, team_organization_id=team_id).first_or_404()
    phase_id = workout.phase_id
    
    db.session.delete(workout)
    db.session.commit()
    
    flash(f'Workout plan "{workout.name}" deleted successfully!', 'success')
    return redirect(url_for('off_season.view_phase', phase_id=phase_id))

@bp.route('/phases/<int:phase_id>/metrics/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_phase_metric(phase_id):
    """Add a recommended metric to a phase"""
    team_id = get_current_team_id()
    phase = OffSeasonPhase.query.filter_by(id=phase_id, team_organization_id=team_id).first_or_404()
    form = PhaseMetricForm()
    
    # Populate metrics choices
    metrics = FitnessMetric.query.filter_by(team_organization_id=team_id, active=True).all()
    form.metric_id.choices = [(m.id, f"{m.name} ({m.unit})") for m in metrics]
    
    if form.validate_on_submit():
        # Check if this metric is already added to this phase
        existing = PhaseMetric.query.filter_by(
            phase_id=phase.id,
            metric_id=form.metric_id.data,
            team_organization_id=team_id
        ).first()
        
        if existing:
            flash(f'This metric is already added to this phase!', 'danger')
            return redirect(url_for('off_season.view_phase', phase_id=phase.id))
        
        phase_metric = PhaseMetric(
            phase_id=phase.id,
            metric_id=form.metric_id.data,
            target_value=form.target_value.data,
            team_organization_id=team_id
        )
        
        db.session.add(phase_metric)
        db.session.commit()
        
        flash('Metric added to phase successfully!', 'success')
        return redirect(url_for('off_season.view_phase', phase_id=phase.id))
    
    return render_template('off_season/phase_metric_form.html', form=form, phase=phase)

@bp.route('/phase-metrics/<int:metric_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_phase_metric(metric_id):
    """Delete a phase metric"""
    team_id = get_current_team_id()
    phase_metric = PhaseMetric.query.filter_by(id=metric_id, team_organization_id=team_id).first_or_404()
    phase_id = phase_metric.phase_id
    
    db.session.delete(phase_metric)
    db.session.commit()
    
    flash('Metric removed from phase successfully!', 'success')
    return redirect(url_for('off_season.view_phase', phase_id=phase_id))

@bp.route('/goals')
@login_required
def goals():
    """View user's SMART goals"""
    team_id = get_current_team_id()
    
    # Get active goals
    active_goals = SMARTGoal.query.filter_by(
        user_id=current_user.id,
        team_organization_id=team_id,
        completed=False
    ).order_by(SMARTGoal.target_date).all()
    
    # Get completed goals
    completed_goals = SMARTGoal.query.filter_by(
        user_id=current_user.id,
        team_organization_id=team_id,
        completed=True
    ).order_by(SMARTGoal.completed_date.desc()).all()
    
    return render_template(
        'off_season/goals.html',
        active_goals=active_goals,
        completed_goals=completed_goals
    )

@bp.route('/goals/add', methods=['GET', 'POST'])
@login_required
def add_goal():
    """Add a new SMART goal"""
    team_id = get_current_team_id()
    form = SMARTGoalForm()
    
    if form.validate_on_submit():
        goal = SMARTGoal(
            user_id=current_user.id,
            title=form.title.data,
            description=form.description.data,
            specific=form.specific.data,
            measurable=form.measurable.data,
            achievable=form.achievable.data,
            relevant=form.relevant.data,
            time_bound=form.time_bound.data,
            target_date=form.target_date.data,
            category=form.category.data,
            created_date=datetime.utcnow(),
            completed=False,
            team_organization_id=team_id
        )
        
        db.session.add(goal)
        db.session.commit()
        
        flash(f'Goal "{goal.title}" added successfully!', 'success')
        return redirect(url_for('off_season.goals'))
    
    return render_template('off_season/goal_form.html', form=form)

@bp.route('/goals/<int:goal_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_goal(goal_id):
    """Edit a SMART goal"""
    team_id = get_current_team_id()
    goal = SMARTGoal.query.filter_by(id=goal_id, user_id=current_user.id, team_organization_id=team_id).first_or_404()
    form = SMARTGoalForm(obj=goal)
    
    if form.validate_on_submit():
        goal.title = form.title.data
        goal.description = form.description.data
        goal.specific = form.specific.data
        goal.measurable = form.measurable.data
        goal.achievable = form.achievable.data
        goal.relevant = form.relevant.data
        goal.time_bound = form.time_bound.data
        goal.target_date = form.target_date.data
        goal.category = form.category.data
        
        db.session.commit()
        
        flash(f'Goal "{goal.title}" updated successfully!', 'success')
        return redirect(url_for('off_season.goals'))
    
    return render_template('off_season/goal_form.html', form=form, goal=goal)

@bp.route('/goals/<int:goal_id>/complete', methods=['POST'])
@login_required
def complete_goal(goal_id):
    """Mark a goal as completed"""
    team_id = get_current_team_id()
    goal = SMARTGoal.query.filter_by(id=goal_id, user_id=current_user.id, team_organization_id=team_id).first_or_404()
    
    goal.completed = True
    goal.completed_date = datetime.utcnow()
    db.session.commit()
    
    flash(f'Goal "{goal.title}" marked as completed!', 'success')
    return redirect(url_for('off_season.goals'))

@bp.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a goal"""
    team_id = get_current_team_id()
    goal = SMARTGoal.query.filter_by(id=goal_id, user_id=current_user.id, team_organization_id=team_id).first_or_404()
    
    db.session.delete(goal)
    db.session.commit()
    
    flash(f'Goal "{goal.title}" deleted successfully!', 'success')
    return redirect(url_for('off_season.goals'))

@bp.route('/sessions/<int:session_id>/complete', methods=['GET', 'POST'])
@login_required
def complete_session(session_id):
    """Mark a session as completed"""
    team_id = get_current_team_id()
    session = ScheduleSession.query.filter_by(id=session_id, team_organization_id=team_id).first_or_404()
    form = SessionCompletionForm()
    
    if form.validate_on_submit():
        # Check if already completed today
        existing = UserSessionCompletion.query.filter_by(
            user_id=current_user.id,
            session_id=session.id,
            completed_date=date.today(),
            team_organization_id=team_id
        ).first()
        
        if existing:
            flash('You have already completed this session today!', 'info')
            return redirect(url_for('off_season.index'))
        
        completion = UserSessionCompletion(
            user_id=current_user.id,
            session_id=session.id,
            completed_date=date.today(),
            notes=form.notes.data,
            rating=form.rating.data,
            team_organization_id=team_id
        )
        
        db.session.add(completion)
        db.session.commit()
        
        flash('Session marked as completed!', 'success')
        return redirect(url_for('off_season.index'))
    
    return render_template('off_season/complete_session.html', form=form, session=session)

@bp.route('/progress')
@login_required
def progress():
    """View user's progress"""
    team_id = get_current_team_id()
    
    # Get all completed sessions
    completions = UserSessionCompletion.query.filter_by(
        user_id=current_user.id,
        team_organization_id=team_id
    ).order_by(UserSessionCompletion.completed_date.desc()).all()
    
    # Get completed goals
    completed_goals = SMARTGoal.query.filter_by(
        user_id=current_user.id,
        team_organization_id=team_id,
        completed=True
    ).order_by(SMARTGoal.completed_date.desc()).all()
    
    # Get fitness records
    # This assumes the user has a player record linked to their account
    player = None
    fitness_records = []
    
    if hasattr(current_user, 'player') and current_user.player:
        player = current_user.player
        fitness_records = FitnessRecord.query.filter_by(
            player_id=player.id,
            team_organization_id=team_id
        ).order_by(FitnessRecord.date_recorded.desc()).all()
    
    return render_template(
        'off_season/progress.html',
        completions=completions,
        completed_goals=completed_goals,
        fitness_records=fitness_records,
        player=player
    )

@bp.route('/timeline')
@login_required
def timeline():
    """View the phase timeline"""
    team_id = get_current_team_id()
    
    # Get all phases ordered by start date
    phases = OffSeasonPhase.query.filter_by(team_organization_id=team_id).order_by(OffSeasonPhase.start_date).all()
    
    # Find the current phase
    today = date.today()
    current_phase = None
    for phase in phases:
        if phase.start_date <= today <= phase.end_date:
            current_phase = phase
            break
    
    return render_template(
        'off_season/timeline.html',
        phases=phases,
        current_phase=current_phase,
        today=today
    )

@bp.route('/guide')
@login_required
def guide():
    """View the off-season guide"""
    # This route would display the off-season guide content
    return render_template('off_season/guide.html')