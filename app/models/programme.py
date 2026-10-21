# app/models/programme.py
"""Training programmes any club can build on the website (Training >
Programmes): an off-season plan, a speed block, a gym cycle, ...

The pieces, and why they are kept apart:

- Programme: a club's programme (or reusable template). It only holds
  identity and scheduling: name, start date, pauses. Its content lives in
  versions.
- ProgrammeVersion: one edition of the content. Coaches edit a draft;
  publishing freezes it. A published version is never edited again, so the
  sessions players logged against stay exactly as they were.
- ProgrammeTrack / ProgrammeWeek / ProgrammeSession / ProgrammeExercise:
  the content of a version. A programme can run several tracks side by side
  (a 10-week speed block next to a 16-week conditioning plan), each with its
  own length and week numbering.
- PerformanceTest / ProgrammeMilestone: the tests a programme uses and when
  they happen (baseline, retest) plus any other dated milestones.
- ProgrammeEnrolment: a player on a programme, on a given version, starting
  at a point the coach chose.
- SessionLog / TestResult: what a player did. Each points at the exact
  session or test row it was logged against, and carries that row's `key`.

Every content row has a `key` (a uuid) that is copied unchanged into the
next draft, so "the same session" can be followed across versions without
relying on names or week numbers.

Every table carries team_organization_id so a club only ever reads its own
rows, and so a team's download/delete (app/utils/team_data.py) covers them.
Nothing points at another club's rows: a copy of a shared template records
where it came from as plain text, not as a foreign key.
"""
import uuid
from datetime import datetime

from app import db


def new_key():
    return uuid.uuid4().hex


# Kinds of session a coach can pick. 'custom' takes a free-text label.
SESSION_TYPES = [
    ('sprint', 'Sprint'),
    ('agility', 'Agility'),
    ('conditioning', 'Conditioning'),
    ('strength', 'Strength'),
    ('throwing', 'Throwing'),
    ('footwork', 'Footwork'),
    ('mobility', 'Mobility'),
    ('recovery', 'Recovery'),
    ('custom', 'Custom'),
]
SESSION_TYPE_LABELS = dict(SESSION_TYPES)

REQUIREMENTS = [
    ('required', 'Required'),
    ('optional', 'Optional'),
    ('alternative', 'Alternative (pick one of a group)'),
]

WEEK_KINDS = [('training', 'Training'), ('deload', 'Deload'), ('rest', 'Rest')]

# What a player can be asked to record when they log a session. Notes are
# always offered. Custom fields (a coach's own numbers) are on the session.
LOG_FIELDS = [
    ('duration_minutes', 'Duration (min)'),
    ('rpe', 'Effort (RPE 1-10)'),
    ('distance_m', 'Distance (m)'),
    ('soreness', 'Soreness (1-5)'),
    ('sleep_hours', 'Sleep last night (h)'),
]
LOG_FIELD_LABELS = dict(LOG_FIELDS)

MEASUREMENTS = [
    ('time', 'Time'),
    ('distance', 'Distance'),
    ('count', 'Count'),
    ('score', 'Score'),
    ('other', 'Other number'),
]
AGGREGATIONS = [
    ('best', 'Best attempt'),
    ('mean', 'Average of attempts'),
    ('last', 'Last attempt'),
]


class Programme(db.Model):
    __tablename__ = 'programme'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(32), nullable=False, unique=True, default=new_key)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # 'programme' runs with players; 'template' is a reusable starting point
    kind = db.Column(db.String(20), nullable=False, default='programme')
    # Shared templates can be copied by other clubs (published content only)
    is_shared = db.Column(db.Boolean, nullable=False, default=False)
    # Coach-only notes. Never shown to players or copied with a template.
    coach_notes = db.Column(db.Text)

    # 'calendar': weeks fall on fixed dates from start_date.
    # 'relative': each player's weeks count from their own start date.
    schedule_mode = db.Column(db.String(20), nullable=False, default='calendar')
    start_date = db.Column(db.Date)
    # Breaks that push later weeks back: [{"from": "2026-12-21", "weeks": 2, "note": "..."}]
    pauses = db.Column(db.JSON)
    archived = db.Column(db.Boolean, nullable=False, default=False)

    # What the dashboard shows beyond completion and tests
    workload_enabled = db.Column(db.Boolean, nullable=False, default=True)
    recovery_enabled = db.Column(db.Boolean, nullable=False, default=False)

    # Where it came from (plain text: the source may belong to another club)
    source_kind = db.Column(db.String(20))  # 'copy', 'template', 'import'
    source_uid = db.Column(db.String(32))
    source_name = db.Column(db.String(200))
    source_team = db.Column(db.String(100))
    source_version = db.Column(db.Integer)
    source_author = db.Column(db.String(100))
    # An import's file name and content hash, so the same file isn't imported twice
    import_filename = db.Column(db.String(200))
    import_hash = db.Column(db.String(64), index=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = db.relationship('TeamOrganization')
    created_by = db.relationship('User')
    versions = db.relationship('ProgrammeVersion', back_populates='programme',
                               order_by='ProgrammeVersion.number', cascade='all, delete-orphan')
    enrolments = db.relationship('ProgrammeEnrolment', back_populates='programme',
                                 cascade='all, delete-orphan')

    @property
    def is_template(self):
        return self.kind == 'template'

    @property
    def draft(self):
        return next((v for v in self.versions if v.status == 'draft'), None)

    @property
    def published(self):
        """The current published version, if any."""
        live = [v for v in self.versions if v.status == 'published']
        return live[-1] if live else None

    def __repr__(self):
        return f'<Programme {self.name} team={self.team_organization_id}>'


class ProgrammeVersion(db.Model):
    __tablename__ = 'programme_version'

    id = db.Column(db.Integer, primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey('programme.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    # draft -> published -> superseded. Only drafts are ever edited.
    status = db.Column(db.String(20), nullable=False, default='draft')
    change_note = db.Column(db.Text)
    published_at = db.Column(db.DateTime)
    published_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    programme = db.relationship('Programme', back_populates='versions')
    tracks = db.relationship('ProgrammeTrack', back_populates='version', order_by='ProgrammeTrack.position',
                             cascade='all, delete-orphan')
    tests = db.relationship('PerformanceTest', back_populates='version', order_by='PerformanceTest.position',
                            cascade='all, delete-orphan')
    milestones = db.relationship('ProgrammeMilestone', back_populates='version',
                                 order_by='ProgrammeMilestone.position', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('programme_id', 'number', name='uq_programme_version_number'),
    )

    @property
    def is_draft(self):
        return self.status == 'draft'

    def __repr__(self):
        return f'<ProgrammeVersion {self.programme_id} v{self.number} {self.status}>'


class ProgrammeTrack(db.Model):
    __tablename__ = 'programme_track'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key)
    version_id = db.Column(db.Integer, db.ForeignKey('programme_version.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    colour = db.Column(db.String(7))
    # The label of the first week: 1 for "Week 1, 2, ...", 0 for "Week 0, 1, ..."
    first_week_number = db.Column(db.Integer, nullable=False, default=1)
    # When the track starts, in weeks after the programme (or player) start
    start_offset_weeks = db.Column(db.Integer, nullable=False, default=0)

    version = db.relationship('ProgrammeVersion', back_populates='tracks')
    weeks = db.relationship('ProgrammeWeek', back_populates='track', order_by='ProgrammeWeek.position',
                            cascade='all, delete-orphan')

    def week_label(self, week):
        return self.first_week_number + week.position

    def __repr__(self):
        return f'<ProgrammeTrack {self.name}>'


class ProgrammeWeek(db.Model):
    __tablename__ = 'programme_week'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key)
    track_id = db.Column(db.Integer, db.ForeignKey('programme_track.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    # 0-based place in the track; the label shown is track.first_week_number + position
    position = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(200))
    kind = db.Column(db.String(20), nullable=False, default='training')
    objective = db.Column(db.Text)
    supporting_skills = db.Column(db.Text)
    notes = db.Column(db.Text)

    track = db.relationship('ProgrammeTrack', back_populates='weeks')
    sessions = db.relationship('ProgrammeSession', back_populates='week', order_by='ProgrammeSession.position',
                               cascade='all, delete-orphan')

    @property
    def number(self):
        return self.track.first_week_number + self.position

    @property
    def is_rest(self):
        return self.kind == 'rest'

    def __repr__(self):
        return f'<ProgrammeWeek {self.track_id}:{self.position}>'


class ProgrammeSession(db.Model):
    __tablename__ = 'programme_session'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key, index=True)
    week_id = db.Column(db.Integer, db.ForeignKey('programme_week.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(200), nullable=False)
    session_type = db.Column(db.String(20), nullable=False, default='custom')
    custom_type = db.Column(db.String(50))
    requirement = db.Column(db.String(20), nullable=False, default='required')
    # Alternatives with the same group in a week: doing any one of them counts
    alternative_group = db.Column(db.String(50))
    duration_minutes = db.Column(db.Integer)
    focus = db.Column(db.Text)
    warmup = db.Column(db.Text)
    cooldown = db.Column(db.Text)
    coaching_cues = db.Column(db.Text)
    video_url = db.Column(db.String(500))
    attachment_url = db.Column(db.String(500))
    # Which LOG_FIELDS a player is asked for, and the coach's own numbers:
    # [{"key": "throws_on_target", "label": "Throws on target", "unit": ""}]
    log_fields = db.Column(db.JSON)
    custom_fields = db.Column(db.JSON)

    week = db.relationship('ProgrammeWeek', back_populates='sessions')
    exercises = db.relationship('ProgrammeExercise', back_populates='session',
                                order_by='ProgrammeExercise.position', cascade='all, delete-orphan')

    @property
    def type_label(self):
        if self.session_type == 'custom' and self.custom_type:
            return self.custom_type
        return SESSION_TYPE_LABELS.get(self.session_type, self.session_type.title())

    @property
    def completion_unit(self):
        """What counts once for completion: the session, or its alternative group."""
        if self.requirement == 'alternative' and self.alternative_group:
            return f'alt:{self.week.key}:{self.alternative_group.strip().lower()}'
        return f'session:{self.key}'

    def __repr__(self):
        return f'<ProgrammeSession {self.title}>'


class ProgrammeExercise(db.Model):
    """One line of a session. Only the name is required: a throwing drill
    may have a duration and instructions but no distance or RPE."""
    __tablename__ = 'programme_exercise'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key)
    session_id = db.Column(db.Integer, db.ForeignKey('programme_session.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    block = db.Column(db.String(20))  # e.g. "A1", "Warm-up"
    name = db.Column(db.String(200), nullable=False)
    sets = db.Column(db.String(30))
    reps = db.Column(db.String(50))
    distance_m = db.Column(db.Float)
    duration_seconds = db.Column(db.Integer)
    rest = db.Column(db.String(100))
    intensity = db.Column(db.String(100))
    tempo = db.Column(db.String(30))
    instructions = db.Column(db.Text)
    video_url = db.Column(db.String(500))

    session = db.relationship('ProgrammeSession', back_populates='exercises')

    def __repr__(self):
        return f'<ProgrammeExercise {self.name}>'


class PerformanceTest(db.Model):
    __tablename__ = 'performance_test'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key, index=True)
    version_id = db.Column(db.Integer, db.ForeignKey('programme_version.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    measurement = db.Column(db.String(20), nullable=False, default='time')
    unit = db.Column(db.String(20), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=1)
    aggregation = db.Column(db.String(20), nullable=False, default='best')
    higher_is_better = db.Column(db.Boolean, nullable=False, default=False)
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    instructions = db.Column(db.Text)

    version = db.relationship('ProgrammeVersion', back_populates='tests')

    def __repr__(self):
        return f'<PerformanceTest {self.name}>'


class ProgrammeMilestone(db.Model):
    """A dated point in the programme: a baseline or retest of some (or all)
    of the programme's tests, or any other milestone a coach wants marked."""
    __tablename__ = 'programme_milestone'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), nullable=False, default=new_key)
    version_id = db.Column(db.Integer, db.ForeignKey('programme_version.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='milestone')  # baseline, retest, milestone
    # The week it falls in (any track of the same version)
    week_id = db.Column(db.Integer, db.ForeignKey('programme_week.id', ondelete='SET NULL'))
    # Keys of the tests it covers; empty means all of the version's tests
    test_keys = db.Column(db.JSON)
    notes = db.Column(db.Text)

    version = db.relationship('ProgrammeVersion', back_populates='milestones')
    week = db.relationship('ProgrammeWeek')

    @property
    def is_test(self):
        return self.kind in ('baseline', 'retest')

    def covers(self, test):
        return not self.test_keys or test.key in self.test_keys


class ProgrammeEnrolment(db.Model):
    __tablename__ = 'programme_enrolment'

    id = db.Column(db.Integer, primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey('programme.id', ondelete='CASCADE'), nullable=False, index=True)
    version_id = db.Column(db.Integer, db.ForeignKey('programme_version.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active, paused, finished, withdrawn
    # Relative programmes: the player's week 1. Calendar programmes ignore it.
    start_date = db.Column(db.Date)
    # Joining late: weeks before this one (programme weeks from the start)
    # aren't expected of the player
    start_offset_weeks = db.Column(db.Integer, nullable=False, default=0)
    # This player's own breaks, same shape as Programme.pauses
    pauses = db.Column(db.JSON)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

    programme = db.relationship('Programme', back_populates='enrolments')
    version = db.relationship('ProgrammeVersion')
    player = db.relationship('Player')
    logs = db.relationship('SessionLog', back_populates='enrolment', cascade='all, delete-orphan')
    results = db.relationship('TestResult', back_populates='enrolment', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('programme_id', 'player_id', name='uq_programme_enrolment_player'),
    )


class SessionLog(db.Model):
    """A player's record of a session. 'skipped' is only ever something a
    player or coach says; a session nobody logged has no row at all."""
    __tablename__ = 'programme_session_log'

    id = db.Column(db.Integer, primary_key=True)
    enrolment_id = db.Column(db.Integer, db.ForeignKey('programme_enrolment.id', ondelete='CASCADE'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('programme_session.id'), nullable=False)
    session_key = db.Column(db.String(32), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='completed')  # completed, partial, skipped
    completed_on = db.Column(db.Date)
    duration_minutes = db.Column(db.Integer)
    rpe = db.Column(db.Integer)
    distance_m = db.Column(db.Float)
    soreness = db.Column(db.Integer)
    sleep_hours = db.Column(db.Float)
    values = db.Column(db.JSON)  # the session's custom fields
    notes = db.Column(db.Text)
    logged_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    enrolment = db.relationship('ProgrammeEnrolment', back_populates='logs')
    session = db.relationship('ProgrammeSession')

    __table_args__ = (
        db.UniqueConstraint('enrolment_id', 'session_key', name='uq_programme_log_session'),
    )

    @property
    def workload(self):
        """Session RPE x minutes, or None when either is missing."""
        if self.rpe is None or self.duration_minutes is None:
            return None
        return self.rpe * self.duration_minutes


class TestResult(db.Model):
    __tablename__ = 'programme_test_result'
    __test__ = False  # not a pytest test class

    id = db.Column(db.Integer, primary_key=True)
    enrolment_id = db.Column(db.Integer, db.ForeignKey('programme_enrolment.id', ondelete='CASCADE'), nullable=False, index=True)
    test_id = db.Column(db.Integer, db.ForeignKey('performance_test.id'), nullable=False)
    test_key = db.Column(db.String(32), nullable=False)
    milestone_id = db.Column(db.Integer, db.ForeignKey('programme_milestone.id', ondelete='SET NULL'))
    milestone_key = db.Column(db.String(32))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    attempts = db.Column(db.JSON, nullable=False)  # [1.92, 1.88, 1.90]
    value = db.Column(db.Float, nullable=False)  # attempts combined by the test's aggregation
    recorded_on = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrolment = db.relationship('ProgrammeEnrolment', back_populates='results')
    test = db.relationship('PerformanceTest')
    milestone = db.relationship('ProgrammeMilestone')
