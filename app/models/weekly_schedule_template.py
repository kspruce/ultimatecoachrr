# app/models/weekly_schedule_template.py
from app import db
from datetime import datetime

class WeeklyScheduleTemplate(db.Model):
    """Weekly schedule template for off-season training phases"""
    __tablename__ = 'weekly_schedule_template'
    
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phase.id'), nullable=False)
    template_type = db.Column(db.String(20), nullable=False)  # 'standard', 'minimal', 'high_volume'
    
    # Monday
    monday_morning = db.Column(db.String(100))
    monday_evening = db.Column(db.String(100))
    monday_duration = db.Column(db.String(50))
    monday_description = db.Column(db.Text)
    
    # Tuesday
    tuesday_morning = db.Column(db.String(100))
    tuesday_evening = db.Column(db.String(100))
    tuesday_duration = db.Column(db.String(50))
    tuesday_description = db.Column(db.Text)
    
    # Wednesday
    wednesday_morning = db.Column(db.String(100))
    wednesday_evening = db.Column(db.String(100))
    wednesday_duration = db.Column(db.String(50))
    wednesday_description = db.Column(db.Text)
    
    # Thursday
    thursday_morning = db.Column(db.String(100))
    thursday_evening = db.Column(db.String(100))
    thursday_duration = db.Column(db.String(50))
    thursday_description = db.Column(db.Text)
    
    # Friday
    friday_morning = db.Column(db.String(100))
    friday_evening = db.Column(db.String(100))
    friday_duration = db.Column(db.String(50))
    friday_description = db.Column(db.Text)
    
    # Saturday
    saturday_morning = db.Column(db.String(100))
    saturday_evening = db.Column(db.String(100))
    saturday_duration = db.Column(db.String(50))
    saturday_description = db.Column(db.Text)
    
    # Sunday
    sunday_morning = db.Column(db.String(100))
    sunday_evening = db.Column(db.String(100))
    sunday_duration = db.Column(db.String(50))
    sunday_description = db.Column(db.Text)
    
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', backref='schedule_templates')
    
    def __repr__(self):
        return f'<WeeklyScheduleTemplate {self.template_type} for Phase {self.phase_id}>'