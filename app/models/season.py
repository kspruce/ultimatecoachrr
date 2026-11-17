# app/models/season.py
"""Seasons, squads and who played for which squad in which season.

A club (TeamOrganization) runs one season per year and can have several
squads (e.g. 1s and 2s) that share its playbook, theory and drills but keep
their own rosters. A Player is the person; SeasonRoster says they were on a
squad that season, with that season's shirt number and position. Nothing is
deleted when a new season starts: last season's games, tournaments,
sessions and roster stay as they were.
"""
from datetime import date, datetime, timedelta

from app import db


class Squad(db.Model):
    __tablename__ = 'squad'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'name', name='uq_squad_team_name'),
    )

    def __repr__(self):
        return f'<Squad {self.name}>'


def _same_day(day, year):
    """`day`'s month and day in another year (29 February -> 28th)."""
    try:
        return day.replace(year=year)
    except ValueError:
        return day.replace(year=year, day=28)


class Season(db.Model):
    __tablename__ = 'season'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # Exactly one season per team is current: the one new games, sessions
    # and tournaments go into and the one pages show unless told otherwise
    is_current = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    roster = db.relationship('SeasonRoster', back_populates='season', lazy='dynamic',
                             cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'year', name='uq_season_team_year'),
        db.Index('uq_season_one_current', 'team_organization_id', unique=True,
                 sqlite_where=db.text('is_current = 1'), postgresql_where=db.text('is_current')),
    )

    @property
    def name(self):
        """'2026' for a calendar-year season, '2027/28' for one that runs
        across new year (October to September, say)."""
        if self.start_date and self.end_date and self.end_date.year > self.start_date.year:
            return f'{self.start_date.year}/{self.end_date.year % 100:02d}'
        return str(self.year)

    def contains(self, day):
        return day is not None and self.start_date <= day <= self.end_date

    @staticmethod
    def default_dates(year, like=None):
        """A year's season dates: 1 January to 31 December, or the same
        start day as `like` (another season) and running a full year, so a
        club whose seasons run October to September keeps doing so."""
        if like is None or (like.start_date.month, like.start_date.day) == (1, 1):
            return date(year, 1, 1), date(year, 12, 31)
        start = _same_day(like.start_date, year)
        return start, _same_day(like.start_date, year + 1) - timedelta(days=1)

    def year_for(self, day):
        """The season year a date would belong to in seasons shaped like
        this one: 2027 for February 2028 when seasons start in October."""
        return day.year if day >= _same_day(self.start_date, day.year) else day.year - 1

    def __repr__(self):
        return f'<Season {self.year}>'


class SeasonRoster(db.Model):
    """A player on the team (and squad) for one season."""
    __tablename__ = 'season_roster'

    STATUSES = [('active', 'Active'), ('injured', 'Injured'), ('left', 'Left')]

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id', ondelete='CASCADE'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id', ondelete='SET NULL'), nullable=True)
    jersey_number = db.Column(db.Integer)
    position = db.Column(db.String(20))
    status = db.Column(db.String(20), nullable=False, default='active')
    joined_date = db.Column(db.Date)
    left_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    season = db.relationship('Season', back_populates='roster')
    player = db.relationship('Player', back_populates='season_entries')
    squad = db.relationship('Squad')

    __table_args__ = (
        db.UniqueConstraint('season_id', 'player_id', name='uq_season_roster_player'),
    )

    @property
    def on_team(self):
        return self.status != 'left'

    def __repr__(self):
        return f'<SeasonRoster season={self.season_id} player={self.player_id}>'
