from app_factory import db
from datetime import datetime
from sqlalchemy.orm import validates

class CuttingSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True) # Nullable for migration
    
    # Cutting type (2x2 grid options)
    cutting_type = db.Column(db.String(20), nullable=False)  # 'open_deep', 'open_under', 'break_deep', 'break_under'
    
    # Outcome
    outcome = db.Column(db.String(20), nullable=False)  # 'open_looked_off', 'guarded_looked_off', 'open_thrown_to', 'guarded_thrown_to'
    
    # Field position where the cut was made
    field_position_x = db.Column(db.Float, nullable=True)
    field_position_y = db.Column(db.Float, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    point = db.relationship('Point', back_populates='cutting_skills')
    # Use foreign_keys to specify which column to use for the relationship
    # and backref instead of back_populates since we don't have direct access to the Player model
    player = db.relationship('Player', 
                           foreign_keys=[player_id],
                           backref=db.backref('cutting_skills', lazy='dynamic'))
    
    # Define valid cutting types and outcomes
    VALID_CUTTING_TYPES = ['open_deep', 'open_under', 'break_deep', 'break_under']
    VALID_OUTCOMES = ['open_looked_off', 'guarded_looked_off', 'open_thrown_to', 'guarded_thrown_to']
    
    @validates('cutting_type')
    def validate_cutting_type(self, key, cutting_type):
        if cutting_type not in self.VALID_CUTTING_TYPES:
            raise ValueError(f"Invalid cutting type: {cutting_type}")
        return cutting_type
    
    @validates('outcome')
    def validate_outcome(self, key, outcome):
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome}")
        return outcome
    
    def __repr__(self):
        return f'<CuttingSkill {self.cutting_type} by {self.player_id} in Point {self.point_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'cutting_type': self.cutting_type,
            'outcome': self.outcome,
            'player_id': self.player_id,
            'field_position_x': self.field_position_x,
            'field_position_y': self.field_position_y,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }