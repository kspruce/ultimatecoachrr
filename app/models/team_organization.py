# app/models/team_organization.py
from app import db
from datetime import datetime

class TeamOrganization(db.Model):
    __tablename__ = 'team_organization'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    logo = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Define relationships using backref
    users = db.relationship('User', backref='team_organization')
    players = db.relationship('Player', backref='team_organization')
    drills = db.relationship('SavedDrill', backref='team_organization')
    tournaments = db.relationship('Tournament', backref='team_organization')
    games = db.relationship('Game', backref='team_organization')
    sessions = db.relationship('SessionPlan', backref='team_organization')
    fitness_metrics = db.relationship('FitnessMetric', backref='team_organization')
    fitness_records = db.relationship('FitnessRecord', backref='team_organization')
    
    # Add these new relationships
    clip_tags = db.relationship('ClipTag', backref='team_organization')
    clips = db.relationship('Clip', backref='team_organization')
    line_templates = db.relationship('LineTemplate', backref='team_organization')
    line_template_players = db.relationship('LineTemplatePlayer', backref='team_organization')
    gameday_events = db.relationship('GameDayEvent', backref='team_organization')
    gameday_player_stats = db.relationship('GameDayPlayerStats', backref='team_organization')
    attendances = db.relationship('Attendance', backref='team_organization')
    session_rsvps = db.relationship('SessionRSVP', backref='team_organization')
    session_components = db.relationship('SessionComponent', backref='team_organization')
    
    def __repr__(self):
        return f'<TeamOrganization {self.name}>'
