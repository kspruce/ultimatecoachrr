from app import db
from datetime import datetime


class PlayerPointStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    o_line_plus_minus = db.Column(db.Float, default=0.0)
    d_line_plus_minus = db.Column(db.Float, default=0.0)
    calculated_per = db.Column(db.Float, default=0.0)
    
    # New O-line statistics
    o_line_clean_holds = db.Column(db.Boolean, default=False)  # True if O-line scored with zero turnovers
    o_line_turnovers = db.Column(db.Integer, default=0)  # Number of turnovers on O-line points
    o_line_got_back = db.Column(db.Boolean, default=False)  # True if O-line regained possession after turnover
    
    # New D-line statistics
    d_line_break_opportunity = db.Column(db.Boolean, default=False)  # True if D-line generated a turnover
    d_line_break_conversion = db.Column(db.Boolean, default=False)  # True if D-line scored after generating a turnover
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Use back_populates for bidirectional relationships
    player = db.relationship('Player', back_populates='point_stats')
    point = db.relationship('Point', back_populates='point_stats')

    def __repr__(self):
        return f'<PlayerPointStats {self.player_id}-{self.point_id}>'