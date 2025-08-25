from app_factory import db
from datetime import datetime
import math
from sqlalchemy.orm import validates

VALID_EVENT_TYPES = [
    'catch', 'goal', 'throwaway', 'drop',  # offensive events
    'shutdown', 'forced_turnover', 'unforced_turnover', 'block', 'callahan', 'scored_on'  # defensive events
]

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    event_type = db.Column(db.String(20), nullable=False)  # Simplified event types
    field_position_x = db.Column(db.Float, nullable=True)
    field_position_y = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_offensive = db.Column(db.Boolean, nullable=False, default=True)  # Track possession
    is_unknown_player = db.Column(db.Boolean, default=False)  # Add this line
    is_opponent = db.Column(db.Boolean, default=False)  # Add this line
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True) # Nullable for migration
    
    point = db.relationship('Point', back_populates='events')
    
    # Define valid event types
    VALID_EVENT_TYPES = [
        'catch', 'goal', 'throwaway', 'drop', 'assist', 'hockey_assist',   # offensive events
        'shutdown', 'forced_turnover', 'unforced_turnover', 'block', 'callahan', 'scored_on',  # defensive events
        'substitution'  # Add this
    ]

    # Relationships
    player = db.relationship(
        'Player', 
        foreign_keys=[player_id],
        back_populates='player_events'
    )
    receiver = db.relationship(
        'Player', 
        foreign_keys=[receiver_id],
        back_populates='receiver_events'
    )

    __table_args__ = (
        db.Index('idx_event_player', 'player_id'),
        db.Index('idx_event_point', 'point_id'),
        db.Index('idx_event_type', 'event_type'),
        db.Index('idx_event_offensive', 'is_offensive'),
    )
    
    @validates('event_type')
    def validate_event_type(self, key, event_type):
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")
        return event_type

    def __repr__(self):
        return f'<Event {self.event_type} by {self.player_id} in Point {self.point_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'event_type': self.event_type,
            'player_id': self.player_id,
            'field_position_x': self.field_position_x,
            'field_position_y': self.field_position_y,
            'timestamp': self.timestamp,
            'receiver_id': self.receiver_id,
            'is_offensive': self.is_offensive
        }


class Pull(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    is_inbounds = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True) # Nullable for migration
   
    # Relationships
    point = db.relationship('Point', back_populates='pulls')
    player = db.relationship('Player', back_populates='pulls')

    def __repr__(self):
        return f'<Pull by Player {self.player_id} in Point {self.point_id}>'


@validates('field_position_x', 'field_position_y')
def validate_field_position(self, key, value):
    if value is not None:
        if key == 'field_position_x':
            return min(max(float(value), 0), 100)
        elif key == 'field_position_y':
            return min(max(float(value), 0), 37)
    return value