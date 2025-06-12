from app import db
from datetime import datetime

# Association table must be defined before the models that use it
play_tag_association = db.Table('play_tag_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('play_tag.id'))
)

class PlayTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True)

class Formation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Play(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    formation_id = db.Column(db.Integer, db.ForeignKey('formation.id'))
    notes = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    formation = db.relationship('Formation', backref='plays')
    tags = db.relationship('PlayTag', secondary=play_tag_association)