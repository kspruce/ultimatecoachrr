# app/models/fitness.py
from app import db
from datetime import datetime

from sqlalchemy.exc import IntegrityError

# The club's fitness tests. Four tests, one each for acceleration, change of
# direction, power and the engine to keep doing it point after point. They
# need cones, a tape measure, a stopwatch and a speaker, and the whole squad
# can do all four in one session.
STANDARD_TESTS = [
    {
        'key': 'sprint_10m',
        'name': '10 m Sprint',
        'unit': 's',
        'higher_is_better': False,
        'decimals': 2,
        'icon': 'bi-lightning-charge-fill',
        'quality': 'Acceleration',
        'why': 'Most cuts are won in the first two or three steps. A quick 10 m '
               'is what gets you open underneath and away from your mark.',
        'kit': 'Two cones 10 m apart, a stopwatch (or a phone filming in slow motion).',
        'how': [
            'Start from a standing split stance with your front foot just behind the line.',
            'The timer starts on your first movement and stops when your chest crosses 10 m.',
            'Three runs with 2 to 3 minutes walking rest between them. Record the best.',
        ],
        'improve': [
            'Short sprints of 10 to 20 m with full rest: 6 to 8 reps, twice a week. Quality over volume.',
            'Hill sprints or sled pushes of 10 to 15 m to drive a powerful forward lean.',
            'Start from different positions (side-on, backpedalling, lying down) to practise reacting.',
            'Get stronger through the legs: split squats, trap bar deadlifts and step-ups.',
        ],
    },
    {
        'key': 'pro_agility',
        'name': '5-10-5 Pro Agility',
        'unit': 's',
        'higher_is_better': False,
        'decimals': 2,
        'icon': 'bi-shuffle',
        'quality': 'Change of direction',
        'why': 'Breaking on an in-cut, changing direction on the mark and recovering '
               'on defence all come down to how fast you stop and go again.',
        'kit': 'Three cones in a line, 5 yards (4.6 m) apart, and a stopwatch.',
        'how': [
            'Straddle the middle cone. Sprint 5 yards to one side and touch the line with your hand.',
            'Turn, sprint 10 yards to the far line and touch it, then sprint back through the middle.',
            'Two runs each way with full rest. Record the best time.',
        ],
        'improve': [
            'Deceleration drills: sprint 10 m and stop dead within three steps, staying low.',
            'Cone drills with sharp 90° and 180° cuts, planting on the outside foot.',
            'Lateral bounds and skater jumps to build side-to-side power.',
            'Strong hamstrings and groin protect you when cutting: Nordics and Copenhagen planks.',
        ],
    },
    {
        'key': 'broad_jump',
        'name': 'Standing Broad Jump',
        'unit': 'cm',
        'higher_is_better': True,
        'decimals': 0,
        'icon': 'bi-arrows-expand',
        'quality': 'Power',
        'why': 'Explosive leg power drives your first step, your skies and your '
               'layouts, and it is quick and simple to measure.',
        'kit': 'A line on the ground and a tape measure.',
        'how': [
            'Toes behind the line, feet about hip-width apart.',
            'Swing your arms and jump forward off both feet, landing on both feet.',
            'Hold the landing without stepping or falling back. Measure from the line to the back of the nearest heel.',
            'Three jumps. Record the best.',
        ],
        'improve': [
            'Broad jumps and box jumps: 3 to 5 sets of 3 to 5 full-effort jumps with full rest.',
            'Heavy-ish strength work twice a week: squats, deadlifts and hip thrusts.',
            'Kettlebell swings to train a fast, powerful hip drive.',
            'Practise landings: stick every jump softly with knees in line with your toes.',
        ],
    },
    {
        'key': 'yoyo_ir1',
        'name': 'Yo-Yo Intermittent Recovery (Level 1)',
        'unit': 'm',
        'higher_is_better': True,
        'decimals': 0,
        'icon': 'bi-heart-pulse-fill',
        'quality': 'Repeat-sprint fitness',
        'why': 'A point is bursts of hard running with short breaks, and so is this '
               'test. It shows whether you can still cut hard at the end of a long point and on the last game of the day.',
        'kit': 'Cones marking a 20 m lane with a 5 m recovery zone behind the start, '
               'a speaker and the Yo-Yo IR1 audio (free apps and videos have it).',
        'how': [
            'Run 20 m out and 20 m back, arriving on each beep.',
            'After each shuttle you get 10 seconds to jog round the cone 5 m behind the start and back.',
            'The beeps speed up. Miss the line twice and you are out.',
            'Record the total distance covered (every shuttle is 40 m).',
        ],
        'improve': [
            'Intervals that look like points: 15 s hard, 15 s easy for 8 to 10 minutes.',
            'Shuttle repeats: 6 to 10 × 40 m with 20 s rest, building up the sets over a few weeks.',
            'One longer, steady run or cycle a week to build an aerobic base that speeds up recovery.',
            'Sleep, eat and drink well before tournaments. Fitness is wasted if you turn up tired.',
        ],
    },
]

STANDARD_TEST_KEYS = [t['key'] for t in STANDARD_TESTS]


def standard_test(key):
    return next((t for t in STANDARD_TESTS if t['key'] == key), None)


def format_value(value, decimals):
    if value is None:
        return '-'
    return f'{value:.{decimals}f}'


class FitnessMetric(db.Model):
    __tablename__ = 'fitness_metric'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    unit = db.Column(db.String(20), nullable=False)
    higher_is_better = db.Column(db.Boolean, default=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Set on the shared rows behind STANDARD_TESTS
    key = db.Column(db.String(40), unique=True)

    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Use string reference for the relationship
    records = db.relationship('FitnessRecord', back_populates='metric', lazy='dynamic')
    phase_metrics = db.relationship('PhaseMetric', back_populates='metric')
    
    def __repr__(self):
        return f'<FitnessMetric {self.name}>'

    @property
    def test(self):
        """The STANDARD_TESTS entry this metric stands for, if any."""
        return standard_test(self.key) if self.key else None

    @property
    def decimals(self):
        return self.test['decimals'] if self.test else 2

    def format(self, value):
        return format_value(value, self.decimals)

    @classmethod
    def standard(cls):
        """The shared metrics behind STANDARD_TESTS, created on first use,
        in STANDARD_TESTS order."""
        rows = {m.key: m for m in cls.query.filter(cls.key.in_(STANDARD_TEST_KEYS))}
        missing = [t for t in STANDARD_TESTS if t['key'] not in rows]
        for test in missing:
                metric = cls(key=test['key'], name=test['name'], unit=test['unit'],
                             higher_is_better=test['higher_is_better'], active=True,
                             team_organization_id=None)
                db.session.add(metric)
                rows[test['key']] = metric
        if missing:
            try:
                db.session.commit()
            except IntegrityError:  # another request created them first
                db.session.rollback()
                return cls.standard()
        return [rows[key] for key in STANDARD_TEST_KEYS]


class TestingPhase(db.Model):
    """A named testing block, e.g. 'Pre-Season 2025' or 'Mid-Season Check-In'."""
    __tablename__ = 'testing_phase'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phase_type = db.Column(db.String(30), default='custom')   # pre_season | mid_season | post_season | custom
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    records = db.relationship('FitnessRecord', back_populates='testing_phase', lazy='dynamic')

    PHASE_LABELS = {
        'pre_season':  ('Pre-Season',  'var(--uc-blue)'),
        'mid_season':  ('Mid-Season',  'var(--uc-amber)'),
        'post_season': ('Post-Season', 'var(--uc-green)'),
        'custom':      ('Custom',      'var(--uc-purple)'),
    }

    @property
    def label(self):
        return self.PHASE_LABELS.get(self.phase_type, ('Custom', 'var(--uc-purple)'))[0]

    @property
    def colour(self):
        return self.PHASE_LABELS.get(self.phase_type, ('Custom', 'var(--uc-purple)'))[1]

    def __repr__(self):
        return f'<TestingPhase {self.name}>'


class FitnessRecord(db.Model):
    __tablename__ = 'fitness_record'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    metric_id = db.Column(db.Integer, db.ForeignKey('fitness_metric.id'), nullable=False)
    value = db.Column(db.Float, nullable=False)
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    testing_phase_id = db.Column(db.Integer, db.ForeignKey('testing_phase.id'), nullable=True)

    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    # Relationships
    player = db.relationship('Player', back_populates='fitness_records')
    metric = db.relationship('FitnessMetric', back_populates='records')
    testing_phase = db.relationship('TestingPhase', back_populates='records')



class FitnessGoal(db.Model):
    """A target a player is working towards on one metric, e.g. a 40-yard
    sprint under 5.2 seconds by the start of the season."""
    __tablename__ = 'fitness_goal'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('fitness_metric.id', ondelete='CASCADE'),
                          nullable=False)
    target_value = db.Column(db.Float, nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    completed = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    completed_date = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), index=True)

    player = db.relationship('Player')
    metric = db.relationship('FitnessMetric')

    def is_met_by(self, value):
        if value is None:
            return False
        if self.metric.higher_is_better:
            return value >= self.target_value
        return value <= self.target_value

    def progress(self, value):
        """0-100: how close the value is to the target."""
        if value is None or not self.target_value:
            return 0
        if self.metric.higher_is_better:
            pct = value / self.target_value * 100
        else:
            pct = self.target_value / value * 100 if value > 0 else 0
        return int(max(0, min(100, pct)))

    def __repr__(self):
        return f'<FitnessGoal player={self.player_id} metric={self.metric_id}>'
