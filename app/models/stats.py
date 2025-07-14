from app import db
from datetime import datetime

class PlayerPointStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    o_line_plus_minus = db.Column(db.Float, default=0.0)
    d_line_plus_minus = db.Column(db.Float, default=0.0)
    calculated_per = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Update relationships to be more specific
    player = db.relationship('Player', backref=db.backref('point_stats', lazy='dynamic'))
    point = db.relationship('Point', backref=db.backref('player_stats', lazy='dynamic'))
    
    def __repr__(self):
        return f'<PlayerPointStats {self.player_id}-{self.point_id}>'
