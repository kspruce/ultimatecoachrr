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
    
    # Add scouting relationships
    scouting_reports = db.relationship('ScoutingReport', backref='team_organization')
    opponent_players = db.relationship('OpponentPlayer', backref='team_organization')
    scouting_clips = db.relationship('ScoutingClip', backref='team_organization')
    
    # Add stats relationship
    player_point_stats = db.relationship('PlayerPointStats', backref='team_organization')
    export_logs = db.relationship('ExportLog', backref='team_organization')
    tournament_rsvps = db.relationship('TournamentRSVP', backref='team_organization')
    settings = db.relationship('TeamSettings', backref='team_organization', uselist=False)
    
    def __repr__(self):
        return f'<TeamOrganization {self.name}>'
