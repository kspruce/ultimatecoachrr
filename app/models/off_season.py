# app/models/off_season.py
from app import db
from datetime import datetime

class OffSeasonPhase(db.Model):
    __tablename__ = 'off_season_phase'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    primary_focus = db.Column(db.String(255))
    training_emphasis = db.Column(db.String(255))
    volume_intensity = db.Column(db.String(255))
    key_outcome = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    workouts = db.relationship('OffSeasonWorkout', back_populates='phase', lazy='dynamic')
    
    def __repr__(self):
        return f'<OffSeasonPhase {self.name}>'


class OffSeasonWorkout(db.Model):
    __tablename__ = 'off_season_workout'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    workout_type = db.Column(db.String(50))  # Strength, Speed, Endurance, etc.
    instructions = db.Column(db.Text)
    duration = db.Column(db.String(50))  # e.g., "45-60 minutes"
    equipment_needed = db.Column(db.Text)
    difficulty_level = db.Column(db.String(20))  # Beginner, Intermediate, Advanced
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign keys
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', back_populates='workouts')
    exercises = db.relationship('OffSeasonExercise', back_populates='workout', lazy='dynamic')
    
    def __repr__(self):
        return f'<OffSeasonWorkout {self.title}>'


class OffSeasonExercise(db.Model):
    __tablename__ = 'off_season_exercise'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    sets = db.Column(db.String(50))  # e.g., "3-4" or "AMRAP"
    reps = db.Column(db.String(50))  # e.g., "8-12" or "30 seconds"
    rest = db.Column(db.String(50))  # e.g., "60-90 seconds"
    notes = db.Column(db.Text)
    order = db.Column(db.Integer)  # For ordering exercises within a workout
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign keys
    workout_id = db.Column(db.Integer, db.ForeignKey('off_season_workout.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    workout = db.relationship('OffSeasonWorkout', back_populates='exercises')
    
    def __repr__(self):
        return f'<OffSeasonExercise {self.name}>'


class PlayerOffSeasonProgress(db.Model):
    __tablename__ = 'player_off_season_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey('off_season_workout.id'), nullable=False)
    completion_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    rating = db.Column(db.Integer)  # Player's rating of the workout (1-5)
    difficulty_feedback = db.Column(db.String(50))  # Too Easy, Just Right, Too Hard
    
    # Foreign key for team organization
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    player = db.relationship('Player')
    phase = db.relationship('OffSeasonPhase')
    workout = db.relationship('OffSeasonWorkout')
    
    def __repr__(self):
        return f'<PlayerOffSeasonProgress {self.player.name} - {self.workout.title}>'


# Define the default phases based on the off-season guide
DEFAULT_PHASES = [
    {
        'name': 'Foundation Phase',
        'description': 'Establishing the fundamental physical and technical foundation upon which the rest of your off-season training will build.',
        'start_date': '2025-09-15',  # These dates would be adjusted based on the current year
        'end_date': '2025-10-31',
        'primary_focus': 'General strength, mobility, aerobic capacity, fundamental skills',
        'training_emphasis': 'Movement quality, technique development, work capacity',
        'volume_intensity': 'Moderate volume, lower intensity',
        'key_outcome': 'Establishing physical and technical foundation for later phases'
    },
    {
        'name': 'Strength Development Phase',
        'description': 'Building upon the foundation established in Phase 1, with a primary focus on developing maximal strength and power.',
        'start_date': '2025-11-01',
        'end_date': '2025-12-15',
        'primary_focus': 'Maximal strength, power development, intermediate skills',
        'training_emphasis': 'Progressive overload, technical refinement',
        'volume_intensity': 'Moderate-high volume, moderate-high intensity',
        'key_outcome': 'Significant strength gains and technical skill improvement'
    },
    {
        'name': 'Recovery/Maintenance Phase',
        'description': 'A strategic deload period during the holiday season, allowing for physical and mental refreshment while maintaining adaptations.',
        'start_date': '2025-12-16',
        'end_date': '2026-01-05',
        'primary_focus': 'Active recovery, skill maintenance, mental preparation',
        'training_emphasis': 'Regeneration, technical refinement, reduced volume',
        'volume_intensity': 'Low volume, low intensity',
        'key_outcome': 'Physical and mental refreshment while maintaining adaptations'
    },
    {
        'name': 'Power/Speed Phase',
        'description': 'Building upon the strength foundation, focusing on converting raw strength into explosive power and speed.',
        'start_date': '2026-01-06',
        'end_date': '2026-01-31',
        'primary_focus': 'Power, speed, agility, advanced skills',
        'training_emphasis': 'Explosive movements, high-velocity training',
        'volume_intensity': 'Lower volume, high intensity',
        'key_outcome': 'Conversion of strength gains to sport-specific power and speed'
    },
    {
        'name': 'Integration Phase',
        'description': 'The bridge between off-season training and competitive play, applying physical and technical developments to game-specific scenarios.',
        'start_date': '2026-02-01',
        'end_date': '2026-02-28',
        'primary_focus': 'Sport-specific conditioning, skill integration, tactical awareness',
        'training_emphasis': 'Game-like scenarios, position-specific development',
        'volume_intensity': 'Moderate volume, varied intensity',
        'key_outcome': 'Integration of physical and technical development into game performance'
    }
]