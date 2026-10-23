# app/models/season.py
"""Seasons, squads and who played for which squad in which season.

A club (TeamOrganization) runs one season per year and can have several
squads (e.g. 1s and 2s) that share its playbook, theory and drills but keep
their own rosters. A Player is the person; SeasonRoster says they were on a
squad that season, with that season's shirt number and position. Nothing is
deleted when a new season starts: last season's games, tournaments,
sessions and roster stay as they were.
"""
from datetime import date, datetime

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
        return str(self.year)

    def contains(self, day):
        return day is not None and self.start_date <= day <= self.end_date

    @staticmethod
    def default_dates(year):
        return date(year, 1, 1), date(year, 12, 31)

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
