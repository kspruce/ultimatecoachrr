# app/models/off_season.py
from app import db
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, Date, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
import enum

class TrackWorkoutWeek(db.Model):
    """Model representing a week in the track workout plan"""
    __tablename__ = 'track_workout_weeks'
    
    id = db.Column(db.Integer, primary_key=True)
    week_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    session_plan_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    session_plan = db.relationship('SessionPlan')
    
    def __repr__(self):
        return f'<TrackWorkoutWeek {self.week_number}: {self.title}>'

class TrainingLevel(enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class TrainingCategory(enum.Enum):
    STRENGTH = "strength"
    SKILLS = "skills"
    CONDITIONING = "conditioning"

class ScheduleType(enum.Enum):
    STANDARD = "standard"
    MINIMAL = "minimal"
    HIGH_VOLUME = "high_volume"

class OffSeasonPhase(db.Model):
    """Model representing an off-season training phase"""
    __tablename__ = 'off_season_phases'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    primary_focus = db.Column(db.String(100))
    training_emphasis = db.Column(db.String(100))
    volume_intensity = db.Column(db.String(100))
    key_outcome = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0)  # For ordering phases
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    schedules = db.relationship('PhaseSchedule', back_populates='phase', cascade='all, delete-orphan')
    workout_plans = db.relationship('WorkoutPlan', back_populates='phase', cascade='all, delete-orphan')
    recommended_metrics = db.relationship('PhaseMetric', back_populates='phase', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<OffSeasonPhase {self.name}>'

class PhaseMetric(db.Model):
    """Model linking fitness metrics to phases"""
    __tablename__ = 'phase_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phases.id'), nullable=False)
    metric_id = db.Column(db.Integer, db.ForeignKey('fitness_metric.id'), nullable=False)
    target_value = db.Column(db.Float)  # Optional target value for this metric in this phase
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', back_populates='recommended_metrics')
    metric = db.relationship('FitnessMetric')
    
    def __repr__(self):
        return f'<PhaseMetric {self.phase_id}:{self.metric_id}>'

class PhaseSchedule(db.Model):
    """Model representing a training schedule for a phase"""
    __tablename__ = 'phase_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phases.id'), nullable=False)
    schedule_type = db.Column(db.Enum(ScheduleType), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', back_populates='schedules')
    sessions = db.relationship('ScheduleSession', back_populates='schedule', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PhaseSchedule {self.phase_id}:{self.schedule_type.value}>'

class ScheduleSession(db.Model):
    """Model representing a session within a schedule"""
    __tablename__ = 'schedule_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('phase_schedules.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    training_focus = db.Column(db.String(100))
    duration_minutes = db.Column(db.Integer)
    description = db.Column(db.Text)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    schedule = db.relationship('PhaseSchedule', back_populates='sessions')
    workout_plans = db.relationship('WorkoutPlan', secondary='session_workout_plans')
    
    def __repr__(self):
        return f'<ScheduleSession {self.schedule_id}:{self.day_of_week}>'

# Association table for sessions and workout plans
session_workout_plans = db.Table('session_workout_plans',
    db.Column('session_id', db.Integer, db.ForeignKey('schedule_sessions.id'), primary_key=True),
    db.Column('workout_plan_id', db.Integer, db.ForeignKey('workout_plans.id'), primary_key=True)
)

class WorkoutPlan(db.Model):
    """Model representing a workout plan"""
    __tablename__ = 'workout_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phases.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.Enum(TrainingCategory), nullable=False)
    level = db.Column(db.Enum(TrainingLevel), nullable=False)
    content = db.Column(db.Text)  # Markdown content with the workout details
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', back_populates='workout_plans')
    
    def __repr__(self):
        return f'<WorkoutPlan {self.name}:{self.category.value}:{self.level.value}>'

class UserSessionCompletion(db.Model):
    """Model tracking user completion of sessions"""
    __tablename__ = 'user_session_completions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('schedule_sessions.id'), nullable=False)
    completed_date = db.Column(db.Date, default=datetime.utcnow)
    notes = db.Column(db.Text)
    rating = db.Column(db.Integer)  # Optional rating (1-5)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    user = db.relationship('User')
    session = db.relationship('ScheduleSession')
    
    def __repr__(self):
        return f'<UserSessionCompletion {self.user_id}:{self.session_id}>'

class SMARTGoal(db.Model):
    """Model for SMART goals (Specific, Measurable, Achievable, Relevant, Time-bound)"""
    __tablename__ = 'smart_goals'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    specific = db.Column(db.Text)  # What exactly will be accomplished?
    measurable = db.Column(db.Text)  # How will progress be measured?
    achievable = db.Column(db.Text)  # Is it realistic?
    relevant = db.Column(db.Text)  # Why is this goal important?
    time_bound = db.Column(db.Text)  # When will it be accomplished?
    target_date = db.Column(db.Date)
    created_date = db.Column(db.Date, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_date = db.Column(db.Date)
    category = db.Column(db.String(50))  # e.g., "Fitness", "Skills", etc.
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<SMARTGoal {self.title}>'