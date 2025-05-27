from app import db
from datetime import datetime
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





class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Remove the conflicting backref here
    player = db.relationship('Player', back_populates='attendances')
    session = db.relationship('SessionPlan', back_populates='attendances')

    def __repr__(self):
        return f'<Attendance {self.player_id} for {self.session_id}>'

class SessionRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    
    session = db.relationship('SessionPlan', back_populates='components')
    saved_drill = db.relationship('SavedDrill', back_populates='components')

    
    def __repr__(self):
        return f'<SessionComponent {self.title}>'