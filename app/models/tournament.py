from app import db
from datetime import datetime


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    # Shown to players on the tournament page
    notes = db.Column(db.Text, nullable=True)
    # Players are asked to reply by this day; later replies are flagged
    rsvp_deadline = db.Column(db.Date, nullable=True)
    squad_size_target = db.Column(db.Integer, nullable=True)
    # Players see whether they're picked only once the coach publishes it
    selection_published = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Last automatic "please reply" reminder, so it's sent once
    reminder_sent_at = db.Column(db.DateTime, nullable=True)
    season = db.Column(db.String(20), nullable=True)  # label, kept in step with season_id
    season_id = db.Column(db.Integer, db.ForeignKey('season.id', ondelete='SET NULL'), nullable=True, index=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Use back_populates instead of backref
    season_obj = db.relationship('Season')
    squad = db.relationship('Squad')
    games = db.relationship('Game', back_populates='tournament', lazy='dynamic')
    # Add relationship with TournamentRSVP
    rsvps = db.relationship('TournamentRSVP', back_populates='tournament', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Tournament {self.name}>'
    
    @property
    def game_count(self):
        """Return the number of games in this tournament."""
        return self.games.count()
    
    @property
    def win_count(self):
        """Return the number of games won in this tournament."""
        from app.models.game import Game  # Import here to avoid circular imports
        return self.games.filter(Game.our_score > Game.their_score).count()
    
    @property
    def loss_count(self):
        """Return the number of games lost in this tournament."""
        from app.models.game import Game  # Import here to avoid circular imports
        return self.games.filter(Game.our_score < Game.their_score).count()
    
    @property
    def formatted_date_range(self):
        """Return a formatted date range for the tournament."""
        if self.start_date and self.end_date:
            if self.start_date == self.end_date:
                return self.start_date.strftime('%B %d, %Y')
            elif self.start_date.month == self.end_date.month and self.start_date.year == self.end_date.year:
                return f"{self.start_date.strftime('%B %d')} - {self.end_date.strftime('%d, %Y')}"
            else:
                return f"{self.start_date.strftime('%B %d, %Y')} - {self.end_date.strftime('%B %d, %Y')}"
        elif self.start_date:
            return self.start_date.strftime('%B %d, %Y')
        else:
            return 'No date set'
    
    @property
    def rsvp_count(self):
        """Return the number of RSVPs for this tournament."""
        return self.rsvps.count()
    
    @property
    def attending_count(self):
        """Return the number of players attending this tournament."""
        return self.rsvps.filter_by(status='attending').count()
    
    @property
    def selected_players_count(self):
        """Return the number of players the coach has picked for this tournament."""
        return self.rsvps.filter_by(selection='picked').count()

    @property
    def end_or_start(self):
        return self.end_date or self.start_date

    @property
    def deadline_passed(self):
        from datetime import date
        return self.rsvp_deadline is not None and date.today() > self.rsvp_deadline
