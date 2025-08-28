from app.models.base import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

class ScoutingReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    offense_strategy = db.Column(db.Text, nullable=True)
    defense_strategy = db.Column(db.Text, nullable=True)
    strengths = db.Column(db.Text, nullable=True)
    weaknesses = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    # Remove this line:
    # team_organization = relationship('TeamOrganization', back_populates='users')
    # The backref in TeamOrganization will handle this relationship
  
    # Relationships
    tournament = db.relationship('Tournament', backref='scouting_reports')
    game = db.relationship('Game', backref='scouting_report', uselist=False)
    players = db.relationship('OpponentPlayer', backref='scouting_report', lazy='dynamic', cascade='all, delete-orphan')
    clips = db.relationship('ScoutingClip', backref='scouting_report', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ScoutingReport {self.team_name}>'

class OpponentPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scouting_report_id = db.Column(db.Integer, db.ForeignKey('scouting_report.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.String(10), nullable=True)
    position = db.Column(db.String(20), nullable=True)  # handler, cutter, hybrid
    height = db.Column(db.String(20), nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    throwing_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    cutting_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    defensive_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    athletic_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    preferred_throws = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    # Remove this line:
    # team_organization = relationship('TeamOrganization', back_populates='users')
    # The backref in TeamOrganization will handle this relationship
    
    def __repr__(self):
        return f'<OpponentPlayer {self.name}>'

class ScoutingClip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scouting_report_id = db.Column(db.Integer, db.ForeignKey('scouting_report.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    youtube_link = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.Integer, nullable=True)  # in seconds
    end_time = db.Column(db.Integer, nullable=True)  # in seconds
    clip_type = db.Column(db.String(50), nullable=True)  # offense, defense, set play
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    # Remove this line:
    # team_organization = relationship('TeamOrganization', back_populates='users')
    # The backref in TeamOrganization will handle this relationship
    
    def __repr__(self):
        return f'<ScoutingClip {self.title}>'
    
    @property
    def youtube_embed_url(self):
        """Return the YouTube embed URL for this clip."""
        if not self.youtube_link:
            return None
        
        # Extract video ID from YouTube link
        if 'youtube.com/watch?v=' in self.youtube_link:
            video_id = self.youtube_link.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in self.youtube_link:
            video_id = self.youtube_link.split('youtu.be/')[1].split('?')[0]
        else:
            return None
        
        # Create embed URL with start time if available
        embed_url = f'https://www.youtube.com/embed/{video_id}'
        if self.start_time:
            embed_url += f'?start={self.start_time}'
            if self.end_time:
                embed_url += f'&end={self.end_time}'
        elif self.end_time:
            embed_url += f'?end={self.end_time}'
        
        return embed_url
