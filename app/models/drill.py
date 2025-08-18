from datetime import datetime
from app import db  # Import your Flask-SQLAlchemy instance
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

class Drill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_public = db.Column(db.Boolean, default=False)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    team_organization = relationship('TeamOrganization', back_populates='users')
  
    # Relationship with frames
    frames = db.relationship('DrillFrame', backref='drill', lazy=True, cascade='all, delete-orphan')

class DrillFrame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drill_id = db.Column(db.Integer, db.ForeignKey('drill.id'), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)  # Order in animation
    name = db.Column(db.String(50))  # Optional name for the frame
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    team_organization = relationship('TeamOrganization', back_populates='users')
    
    # Store all elements as JSON (players, discs, lines, text)
    # This includes positions, colors, labels, etc.
    elements = db.Column(db.JSON, nullable=False)

class SavedDrill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    setup_instructions = db.Column(db.Text, nullable=True)
    recommended_duration = db.Column(db.Integer, nullable=True)
    min_players = db.Column(db.Integer, nullable=True)
    max_players = db.Column(db.Integer, nullable=True)
    skill_level = db.Column(db.String(20), nullable=True)
    focus_area = db.Column(db.String(100), nullable=True)
    equipment_needed = db.Column(db.String(200), nullable=True)
    ultiplay_embed = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    team_organization = relationship('TeamOrganization', back_populates='users')
    
    # Relationship to SessionComponent
    components = db.relationship('SessionComponent', back_populates='saved_drill', lazy='dynamic')

    def __repr__(self):
        return f'<SavedDrill {self.title}>'