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
    players_see_classroom = db.Column(db.Boolean, default=False, nullable=False)

    # When the sessions built from the plan happen (Season plan > Sessions).
    # Weekdays are 0 = Monday ... 6 = Sunday, counted from each week's w/c.
    joint_weekday = db.Column(db.Integer)
    joint_start = db.Column(db.Time)
    joint_end = db.Column(db.Time)
    split_weekday = db.Column(db.Integer)
    split_start = db.Column(db.Time)
    split_end = db.Column(db.Time)
    session_location = db.Column(db.String(100))
    # Set once sessions have been built; from then on editing a week or
    # re-importing the plan keeps them in step.
    sessions_built_at = db.Column(db.DateTime)

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
    classroom_sessions = db.relationship('ClassroomSession', back_populates='plan',
                                         order_by='ClassroomSession.number',
                                         cascade='all, delete-orphan')

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
    classroom_sessions = db.relationship('ClassroomSession', back_populates='week',
                                         order_by='ClassroomSession.number')

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


class ClassroomSession(db.Model):
    """An off-pitch session (C1, C2, ...): when and how to join beforehand;
    the recording, slides, summary and commitments afterwards."""
    __tablename__ = 'classroom_session'

    DEFAULT_MINUTES = 60

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('season_plan.id', ondelete='CASCADE'), nullable=False, index=True)
    week_id = db.Column(db.Integer, db.ForeignKey('season_week.id', ondelete='SET NULL'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    code = db.Column(db.String(10), nullable=False)  # "C4"
    number = db.Column(db.Integer, nullable=False)   # 4, for ordering
    title = db.Column(db.String(200), nullable=False)
    format = db.Column(db.String(100))      # "Online", "In person, by squad"
    audience = db.Column(db.String(200))    # "All", "1s", "Captains, player leaders and anyone interested"
    main_source = db.Column(db.String(200))
    goal = db.Column(db.Text)
    starts_at = db.Column(db.DateTime)      # local time; null until a coach sets it
    duration_minutes = db.Column(db.Integer)
    join_url = db.Column(db.String(500))
    plan_md = db.Column(db.Text)            # the facilitator's plan (coaches and captains only)
    prep_md = db.Column(db.Text)            # what players see beforehand
    summary_md = db.Column(db.Text)
    commitments_md = db.Column(db.Text)
    summary_published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = db.relationship('SeasonPlan', back_populates='classroom_sessions')
    week = db.relationship('SeasonWeek', back_populates='classroom_sessions')
    resources = db.relationship('ClassroomResource', back_populates='session',
                                order_by='ClassroomResource.order', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('plan_id', 'code', name='uq_classroom_session_plan_code'),
    )

    @property
    def has_coach_content(self):
        """True once a coach has added anything an import doesn't provide."""
        return bool(self.resources or self.summary_md or self.commitments_md
                    or self.join_url or self.starts_at)

    def ends_at(self):
        """When the session is over: start + duration, or the end of its week."""
        if self.starts_at:
            return self.starts_at + timedelta(minutes=self.duration_minutes or self.DEFAULT_MINUTES)
        if self.week and self.week.week_commencing:
            return datetime.combine(self.week.week_ending, datetime.max.time())
        return None

    def __repr__(self):
        return f'<ClassroomSession {self.code}>'


class ClassroomResource(db.Model):
    """A link attached to a classroom session: a recording, slides, a document."""
    __tablename__ = 'classroom_resource'

    KINDS = [('video', 'Recording'), ('slides', 'Slides'), ('document', 'Document'), ('link', 'Link')]

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('classroom_session.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='link')
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    coaches_only = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship('ClassroomSession', back_populates='resources')

    @property
    def kind_label(self):
        return dict(self.KINDS).get(self.kind, 'Link')

    def __repr__(self):
        return f'<ClassroomResource {self.kind} {self.title}>'
