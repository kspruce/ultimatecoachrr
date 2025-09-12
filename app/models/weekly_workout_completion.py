# app/models/weekly_workout_completion.py
from app import db
from datetime import datetime

class WeeklyWorkoutCompletion(db.Model):
    """Track weekly workout completion for players"""
    __tablename__ = 'weekly_workout_completion'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule_template.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Week identification
    week_number = db.Column(db.Integer, nullable=False)  # Week number within the phase
    week_start_date = db.Column(db.Date, nullable=False)  # Start date of the week
    
    # Day-specific completion tracking
    monday_morning_completed = db.Column(db.Boolean, default=False)
    monday_evening_completed = db.Column(db.Boolean, default=False)
    monday_notes = db.Column(db.Text)
    
    tuesday_morning_completed = db.Column(db.Boolean, default=False)
    tuesday_evening_completed = db.Column(db.Boolean, default=False)
    tuesday_notes = db.Column(db.Text)
    
    wednesday_morning_completed = db.Column(db.Boolean, default=False)
    wednesday_evening_completed = db.Column(db.Boolean, default=False)
    wednesday_notes = db.Column(db.Text)
    
    thursday_morning_completed = db.Column(db.Boolean, default=False)
    thursday_evening_completed = db.Column(db.Boolean, default=False)
    thursday_notes = db.Column(db.Text)
    
    friday_morning_completed = db.Column(db.Boolean, default=False)
    friday_evening_completed = db.Column(db.Boolean, default=False)
    friday_notes = db.Column(db.Text)
    
    saturday_morning_completed = db.Column(db.Boolean, default=False)
    saturday_evening_completed = db.Column(db.Boolean, default=False)
    saturday_notes = db.Column(db.Text)
    
    sunday_morning_completed = db.Column(db.Boolean, default=False)
    sunday_evening_completed = db.Column(db.Boolean, default=False)
    sunday_notes = db.Column(db.Text)
    
    # Overall tracking
    completion_percentage = db.Column(db.Float, default=0.0)  # Calculated percentage of completed workouts
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    player = db.relationship('Player', backref='weekly_completions')
    phase = db.relationship('OffSeasonPhase', backref='weekly_completions')
    template = db.relationship('WeeklyScheduleTemplate', backref='weekly_completions')
    
    def __repr__(self):
        return f'<WeeklyWorkoutCompletion Week {self.week_number} - Player {self.player_id}>'
        
    def calculate_completion_percentage(self):
        """Calculate the completion percentage based on completed workouts"""
        total_slots = 14  # 7 days * 2 slots per day
        completed_slots = 0
        
        # Count completed slots
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            morning_field = f"{day}_morning_completed"
            evening_field = f"{day}_evening_completed"
            
            if getattr(self, morning_field):
                completed_slots += 1
            if getattr(self, evening_field):
                completed_slots += 1
        
        # Calculate percentage
        self.completion_percentage = (completed_slots / total_slots) * 100
        return self.completion_percentage