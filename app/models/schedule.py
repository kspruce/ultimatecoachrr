# app/models/schedule.py
"""Regular training, players' usual answers, session templates and the
reminders already sent.

A TrainingSchedule is one regular session ("Saturday, 10:00-13:00, all
season, everyone"; "Tuesday, 19:00-21:00, Nov to Jan, 2s"). Its dates are
ordinary SessionPlans (schedule_id set) made ahead of time by
app.utils.schedules, so players can say whether they're coming before
anyone writes the plan.
"""
from datetime import datetime

from app import db

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Which squads a schedule is for; none means the whole club
training_schedule_squad = db.Table(
    'training_schedule_squad',
    db.Column('schedule_id', db.Integer, db.ForeignKey('training_schedule.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('squad_id', db.Integer, db.ForeignKey('squad.id', ondelete='CASCADE'), primary_key=True),
)


class TrainingSchedule(db.Model):
    __tablename__ = 'training_schedule'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    weekday = db.Column(db.Integer, nullable=False)  # 0 = Monday
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    location = db.Column(db.String(100))
    session_type = db.Column(db.String(20), default='invited_training')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)  # None: until the end of the current season
    # Players from other squads may say they're coming too
    others_welcome = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    squads = db.relationship('Squad', secondary=training_schedule_squad, order_by='Squad.sort_order')
    sessions = db.relationship('SessionPlan', back_populates='schedule', lazy='dynamic')

    @property
    def weekday_name(self):
        return WEEKDAYS[self.weekday]

    @property
    def squad_names(self):
        return ' & '.join(s.name for s in self.squads)

    @property
    def time_range(self):
        if self.start_time and self.end_time:
            return f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        return f"{self.start_time:%H:%M}" if self.start_time else ''

    def __repr__(self):
        return f'<TrainingSchedule {self.name}>'


class ScheduleAvailability(db.Model):
    """A player's usual answer for a schedule ("usually at Saturdays"). It
    stands for every date of the schedule they haven't answered themselves."""
    __tablename__ = 'schedule_availability'

    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('training_schedule.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedule = db.relationship('TrainingSchedule')
    player = db.relationship('Player')

    __table_args__ = (
        db.UniqueConstraint('schedule_id', 'player_id', name='uq_schedule_availability_player'),
    )


class SessionTemplate(db.Model):
    """A reusable set of session blocks ("standard warm-up + scrimmage")."""
    __tablename__ = 'session_template'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    # [{title, component_type, duration_minutes, description, coach_cue, notes, focus_area, drill_id}]
    blocks = db.Column(db.JSON, nullable=False, default=list)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_minutes(self):
        return sum(b.get('duration_minutes') or 0 for b in self.blocks or [])


class SessionReminder(db.Model):
    """A reminder already sent to a player about a session, so it goes once."""
    __tablename__ = 'session_reminder'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # 'answer': maybe / no answer a week ahead
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    __table_args__ = (
        db.UniqueConstraint('session_id', 'player_id', 'kind', name='uq_session_reminder'),
    )
