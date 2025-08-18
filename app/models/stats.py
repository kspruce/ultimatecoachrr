from app import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

class PlayerPointStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    o_line_plus_minus = db.Column(db.Float, default=0.0)
    d_line_plus_minus = db.Column(db.Float, default=0.0)
    calculated_per = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
 
    # Use back_populates for bidirectional relationships
    player = db.relationship('Player', back_populates='point_stats')
    point = db.relationship('Point', back_populates='point_stats')

    def __repr__(self):
        return f'<PlayerPointStats {self.player_id}-{self.point_id}>'

