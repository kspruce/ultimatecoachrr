from app import db
from datetime import datetime

class Player(db.Model):
    __tablename__ = 'player'  
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.String(10))
    position = db.Column(db.String(20))
    height = db.Column(db.String(20))
    weight = db.Column(db.String(20))
    gender = db.Column(db.String(20))
    gender_match = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    team = db.Column(db.String(50))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    line_preference = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    points_played = db.Column(db.Integer, default=0)
    games_played= db.Column(db.Integer, default=0)
    
    # User relationship
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Updated to 'users.id'
    user_account = db.relationship('User', back_populates='player_profile')
    
    # Other relationships
    lineups = db.relationship('LineUp', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    player_events = db.relationship(
        "Event",
        foreign_keys='Event.player_id',
        back_populates="player",
        lazy='dynamic'
    )
    receiver_events = db.relationship(
        'Event',
        foreign_keys='Event.receiver_id',
        back_populates='receiver',
        lazy='dynamic'
    )
    receptions = db.relationship('Event', foreign_keys='Event.receiver_id', backref='receiver', lazy='dynamic')
    pulls = db.relationship('Pull', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    clip_appearances = db.relationship('ClipPlayer', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', back_populates='player', lazy='dynamic')
    session_rsvps = db.relationship('SessionRSVP', back_populates='player', lazy='dynamic')

    def __repr__(self):
        return f'<Player {self.name}>'

    @property
    def receptions(self):
        # Update this to use receiver_events instead of events
        return self.receiver_events.filter_by(event_type='catch').all()


    @property
    def throws(self):
        return self.events.filter_by(event_type='throw').all()    
    
    @property
    def age(self):
        if self.birth_date:
            today = datetime.now().date()
            return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return None
