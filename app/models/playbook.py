from app import db  # Add this import at the top
from datetime import datetime

class Play(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    formation_id = db.Column(db.Integer, db.ForeignKey('formation.id'))
    notes = db.Column(db.Text)
    # Replace diagram_url and s3_key with ultiplay_embed
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    formation = db.relationship('Formation', backref='plays')
    tags = db.relationship('PlayTag', secondary='play_tag_association')

class Formation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    # Replace diagram_url with ultiplay_embed
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
