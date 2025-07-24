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
    games_played = db.Column(db.Integer, default=0)
    short_term_goals = db.Column(db.Text)
    mid_term_goals = db.Column(db.Text)
    long_term_goals = db.Column(db.Text)
    skills_to_develop = db.Column(db.Text)
    coach_feedback = db.Column(db.Text) 


    # Relationships
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    user_account = db.relationship('User', back_populates='player_profile', uselist=False)
    lineups = db.relationship('LineUp', back_populates='player', lazy='dynamic', cascade='all, delete-orphan')
    player_events = db.relationship('Event', 
                                  foreign_keys='Event.player_id',
                                  back_populates='player',
                                  lazy='dynamic')
    receiver_events = db.relationship('Event',
                                    foreign_keys='Event.receiver_id',
                                    back_populates='receiver',
                                    lazy='dynamic')
    pulls = db.relationship('Pull', back_populates='player', lazy='dynamic', cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', back_populates='player', lazy='dynamic')
    session_rsvps = db.relationship('SessionRSVP', back_populates='player', lazy='dynamic')
    # Add relationship with TournamentRSVP
    tournament_rsvps = db.relationship('TournamentRSVP', back_populates='player', lazy='dynamic')
    point_stats = db.relationship('PlayerPointStats', back_populates='player', cascade='all, delete-orphan')
    throws_made = db.relationship('Throw',
                                foreign_keys='Throw.thrower_id',
                                back_populates='thrower',
                                lazy='dynamic')
    throws_received = db.relationship('Throw',
                                    foreign_keys='Throw.receiver_id',
                                    back_populates='receiver',
                                    lazy='dynamic')
    fitness_records = db.relationship('FitnessRecord', back_populates='player', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Player {self.name}>'

    @property
    def receptions(self):
        return self.receiver_events.filter_by(event_type='catch').all()

    @property
    def throws(self):
        return self.player_events.filter_by(event_type='throw').all()

    @property
    def age(self):
        if self.birth_date:
            today = datetime.now().date()
            return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return None