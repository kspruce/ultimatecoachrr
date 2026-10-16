# app/models/season_plan.py
"""A team's season plan: phases, a week-by-week calendar, milestones and
long-form pages. Filled by `flask import-season-plan`; shown under
/season-plan when the team has the Season plan feature switched on."""
from datetime import datetime, timedelta

from app import db


class SeasonPlan(db.Model):
    __tablename__ = 'season_plan'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    season = db.Column(db.String(20), nullable=False)  # e.g. "2027/28"
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    source = db.Column(db.String(200))
    imported_at = db.Column(db.DateTime)

    # What players (below captain) may see; captains and up see everything.
    players_see_overview = db.Column(db.Boolean, default=False, nullable=False)
    players_see_weeks = db.Column(db.Boolean, default=False, nullable=False)
    players_see_session_notes = db.Column(db.Boolean, default=False, nullable=False)
    players_see_phases = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    phases = db.relationship('SeasonPhase', back_populates='plan', order_by='SeasonPhase.number',
                             cascade='all, delete-orphan')
    weeks = db.relationship('SeasonWeek', back_populates='plan', order_by='SeasonWeek.week_number',
                            cascade='all, delete-orphan')
    pages = db.relationship('SeasonPage', back_populates='plan', order_by='SeasonPage.order',
                            cascade='all, delete-orphan')
    milestones = db.relationship('SeasonMilestone', back_populates='plan',
                                 order_by='SeasonMilestone.order', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'season', name='uq_season_plan_team_season'),
    )

    def week_for(self, day):
        """The week whose Monday-to-Sunday span contains `day`, if any."""
        for week in self.weeks:
            if week.week_commencing and week.week_commencing <= day <= week.week_commencing + timedelta(days=6):
                return week
        return None

    def __repr__(self):
        return f'<SeasonPlan {self.season} team={self.team_organization_id}>'


class SeasonPhase(db.Model):
    __tablename__ = 'season_phase'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('season_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    start_week = db.Column(db.Integer)
    end_week = db.Column(db.Integer)
    aim = db.Column(db.Text)
    training_focus = db.Column(db.Text)
    events = db.Column(db.Text)
    classroom_refs = db.Column(db.String(200))
    strategic_anchor = db.Column(db.Text)
    colour = db.Column(db.String(7))  # #RRGGBB
    # What each squad can do by the end of the phase: {"1s offence": "...", ...}
    progression = db.Column(db.JSON)

    plan = db.relationship('SeasonPlan', back_populates='phases')
    weeks = db.relationship('SeasonWeek', back_populates='phase', order_by='SeasonWeek.week_number')

    __table_args__ = (
        db.UniqueConstraint('plan_id', 'number', name='uq_season_phase_plan_number'),
    )

    @property
    def week_count(self):
        if self.start_week and self.end_week:
            return self.end_week - self.start_week + 1
        return len(self.weeks) or 1

    def __repr__(self):
        return f'<SeasonPhase {self.number} {self.name}>'


class SeasonWeek(db.Model):
    __tablename__ = 'season_week'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('season_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('season_phase.id', ondelete='SET NULL'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    week_commencing = db.Column(db.Date)
    block = db.Column(db.String(200))
    joint_theme = db.Column(db.Text)
    firsts_theme = db.Column(db.Text)
    seconds_theme = db.Column(db.Text)
    classroom = db.Column(db.String(200))
    off_pitch = db.Column(db.Text)
    notes = db.Column(db.Text)  # coaches' own notes; never overwritten by an import
    session_title = db.Column(db.String(200))  # from the "## Week N · date · title" heading
    session_detail_md = db.Column(db.Text)
    is_event = db.Column(db.Boolean, default=False, nullable=False)
    is_break = db.Column(db.Boolean, default=False, nullable=False)
    # Optional link to a full SessionPlan, set by hand later
    session_plan_id = db.Column(db.Integer, db.ForeignKey('session_plan.id', ondelete='SET NULL'), nullable=True)

    plan = db.relationship('SeasonPlan', back_populates='weeks')
    phase = db.relationship('SeasonPhase', back_populates='weeks')
    session_plan = db.relationship('SessionPlan')

    __table_args__ = (
        db.UniqueConstraint('plan_id', 'week_number', name='uq_season_week_plan_number'),
    )

    @property
    def week_ending(self):
        return self.week_commencing + timedelta(days=6) if self.week_commencing else None

    def __repr__(self):
        return f'<SeasonWeek {self.week_number}>'


class SeasonPage(db.Model):
    __tablename__ = 'season_page'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('season_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    slug = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    body_markdown = db.Column(db.Text)
    players_can_view = db.Column(db.Boolean, default=False, nullable=False)

    plan = db.relationship('SeasonPlan', back_populates='pages')

    __table_args__ = (
        db.UniqueConstraint('plan_id', 'slug', name='uq_season_page_plan_slug'),
    )

    def __repr__(self):
        return f'<SeasonPage {self.slug}>'


class SeasonMilestone(db.Model):
    __tablename__ = 'season_milestone'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('season_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    when_label = db.Column(db.String(100), nullable=False)  # "Week 1", "Weeks 18-20", "After every event"
    what = db.Column(db.Text, nullable=False)
    start_week = db.Column(db.Integer)  # null when not tied to a week
    end_week = db.Column(db.Integer)

    plan = db.relationship('SeasonPlan', back_populates='milestones')

    def __repr__(self):
        return f'<SeasonMilestone {self.when_label}>'
