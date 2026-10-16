# app/models/team_organization.py
import secrets
from datetime import datetime

from app import db

class TeamOrganization(db.Model):
    __tablename__ = 'team_organization'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    logo = db.Column(db.String(255))
    division = db.Column(db.String(20), nullable=False, default="mixed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Reusable join link (/auth/join/<code>) a coach shares so players can
    # create their own accounts on this team. Off until a coach turns it on.
    join_code = db.Column(db.String(16), unique=True, nullable=True)
    join_enabled = db.Column(db.Boolean, default=False, nullable=False)

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


# No 0/O or 1/I/L, so codes read out loud or copied by hand still work
JOIN_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
JOIN_CODE_LENGTH = 8


def generate_join_code():
    """A join code no other team is using."""
    while True:
        code = ''.join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        if not TeamOrganization.query.filter_by(join_code=code).first():
            return code


def normalize_join_code(code):
    """Accept codes typed with spaces, dashes or lower case."""
    return ''.join(ch for ch in (code or '').upper() if ch.isalnum())
