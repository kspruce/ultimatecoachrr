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
    
    # Don't define relationships here - define them in their respective models
    
    def __repr__(self):
        return f'<TeamOrganization {self.name}>'
