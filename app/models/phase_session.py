from app import db
from datetime import datetime

class PhaseSessionSuggestion(db.Model):
    """Model linking session plans to off-season phases as suggestions"""
    __tablename__ = 'phase_session_suggestions'
    
    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('off_season_phases.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    notes = db.Column(db.Text)
    order = db.Column(db.Integer, default=0)  # For ordering suggestions
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Relationships
    phase = db.relationship('OffSeasonPhase', back_populates='suggested_sessions')
    session = db.relationship('SessionPlan')
    
    def __repr__(self):
        return f'<PhaseSessionSuggestion {self.phase_id}:{self.session_id}>'
