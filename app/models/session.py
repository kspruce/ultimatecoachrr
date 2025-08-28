from app.models.base import db
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.models.drill import SavedDrill
from app.models.player import Player


class SessionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    focus_area = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_pattern = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    # Relationships
    components = db.relationship('SessionComponent', back_populates='session', 
                               lazy='dynamic', cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', back_populates='session', 
                                lazy='dynamic', cascade='all, delete-orphan')
    rsvps = db.relationship('SessionRSVP', back_populates='session', 
                           lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<SessionPlan {self.title}>'
    
    @property
    def duration_minutes(self):
        """Calculate the session duration in minutes."""
        if self.start_time and self.end_time:
            start_dt = datetime.combine(datetime.today(), self.start_time)
            end_dt = datetime.combine(datetime.today(), self.end_time)
            delta = end_dt - start_dt
            return delta.seconds // 60
        return None
    
    @property
    def component_count(self):
        """Return the number of components in this session."""
        return self.components.count()
    
    @property
    def attendance_count(self):
        """Return the number of players who attended this session."""
        return self.attendances.count()
    
    @property
    def formatted_date(self):
        """Return the formatted date."""
        if self.date:
            return self.date.strftime('%B %d, %Y')
        return 'No date set'
    
    @property
    def formatted_time(self):
        """Return the formatted time range."""
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
        return 'No time set'

    # Add session_type field with choices
    session_type = db.Column(db.String(20), default='invited_training')
    
    # Define constants for session types
    SESSION_TYPE_INVITED = 'invited_training'
    SESSION_TYPE_OPEN = 'open_training'
    SESSION_TYPE_POD = 'pod_training'
    
    # Add session type choices for form selection
    SESSION_TYPE_CHOICES = [
        (SESSION_TYPE_INVITED, 'Invited Training'),
        (SESSION_TYPE_OPEN, 'Open Training'),
        (SESSION_TYPE_POD, 'Pod Training')
    ]
    
    @property
    def session_type_display(self):
        """Return the display name for the session type"""
        for value, display in self.SESSION_TYPE_CHOICES:
            if value == self.session_type:
                return display
        return 'Unknown'




# In session.py
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), default='present')  # present, absent, late, excused
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Fix this relationship - change 'attendance' to 'attendances'
    session = relationship('SessionPlan', back_populates='attendances')
    player = relationship('Player', back_populates='attendances')  # Also check this one


class SessionRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Update the relationship definition
    player = db.relationship('Player', back_populates='session_rsvps')
    session = db.relationship('SessionPlan', back_populates='rsvps')

    def __repr__(self):
        return f'<SessionRSVP {self.player_id} for {self.session_id}: {self.status}>'
    

class SessionComponent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    drill_id = db.Column(db.Integer, db.ForeignKey('saved_drill.id', ondelete='CASCADE'))
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    order = db.Column(db.Integer, nullable=False)
    component_type = db.Column(db.String(20), nullable=False)
    focus_area = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    session = db.relationship('SessionPlan', back_populates='components')
    saved_drill = db.relationship('SavedDrill', back_populates='components')

    
    def __repr__(self):
        return f'<SessionComponent {self.title}>'