# models/throw.py
from app import db
from datetime import datetime
import math

class Throw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    thrower_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    
    # Keep team relationships but make them work with Player.team string
    team = db.Column(db.String(50))  # Match Player.team string field
    opposition_team = db.Column(db.String(50))  # Store opposition team name
    
    # Event IDs to link the throw to its related events
    throwing_event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    receiving_event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    
    # Positions
    x_start = db.Column(db.Float)
    y_start = db.Column(db.Float)
    x_end = db.Column(db.Float)
    y_end = db.Column(db.Float)
    
    # Additional attributes
    distance = db.Column(db.Float)
    is_completion = db.Column(db.Boolean, default=True)
    throw_type = db.Column(db.String(20))  # 'assist', 'hockey_assist', 'regular'
    is_offensive = db.Column(db.Boolean, default=True)
    
    # Future additions
    break_throw = db.Column(db.Boolean)
    force_direction = db.Column(db.String(20))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    point = db.relationship('Point', back_populates='throws')
    thrower = db.relationship('Player', 
                            foreign_keys=[thrower_id], 
                            back_populates='throws_made')  # Change backref to back_populates
    receiver = db.relationship('Player', 
                             foreign_keys=[receiver_id], 
                             back_populates='throws_received')  # Change backref to back_populates
    throwing_event = db.relationship('Event', foreign_keys=[throwing_event_id])
    receiving_event = db.relationship('Event', foreign_keys=[receiving_event_id])
    
    def calculate_distance(self):
        """Calculate the distance of the throw"""
        if (self.x_start is not None and self.y_start is not None and 
            self.x_end is not None and self.y_end is not None):
            return math.sqrt(
                (self.x_end - self.x_start) ** 2 + 
                (self.y_end - self.y_start) ** 2
            )
        return None
    
    def to_vector(self, normalize=False):
        """Convert throw to vector format for visualization"""
        if normalize:
            # Use center point as starting point for normalized vectors
            center_x, center_y = 50, 18.5  # Center of field
            
            # Calculate vector components
            dx = self.x_end - self.x_start
            dy = self.y_end - self.y_start
            
            # Scale vector to maintain direction but standardize length
            distance = self.calculate_distance()
            if distance:
                scale = 20 / distance  # Standardize to 20 meters length
                return {
                    'start_x': center_x,
                    'start_y': center_y,
                    'end_x': center_x + (dx * scale),
                    'end_y': center_y + (dy * scale),
                    'type': self.throw_type,
                    'distance': distance
                }
        return None

    def __repr__(self):
        return f'<Throw {self.id} by {self.thrower_id} to {self.receiver_id}>'
