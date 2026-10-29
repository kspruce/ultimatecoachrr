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
            ('Strength', [
                'Twice a week: trap bar deadlift 3 × 5, rear-foot-elevated split squat 3 × 6 each leg, '
                'hip thrust 3 × 8, calf raises 3 × 12.',
            ]),
            ('Power and plyometrics', [
                'Broad jumps 4 × 3 and bounding 3 × 20 m, with full rest so every rep is fast.',
                'Wall drives and A-skips 3 × 20 s to groove a strong forward lean.',
            ]),
            ('Field session', [
                'Acceleration block at the start of training, while fresh: 2 sets of 4 × 10 to 20 m '
                'from different starts (split stance, side-on, from a jog, reacting to a call). '
                '90 s between reps, 3 minutes between sets.',
                'Finish with 3 × 15 m hill or sled sprints.',
            ]),
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
            ('Strength', [
                'Twice a week: Nordic curls 3 × 5, Copenhagen plank 3 × 20 s each side, '
                'lateral lunge 3 × 8 each side, single-leg Romanian deadlift 3 × 8. '
                'Strong hamstrings and groin also protect you when cutting.',
            ]),
            ('Agility and footwork', [
                'Deceleration: sprint 5, 10 or 15 m and stop dead within three steps, hips low. 2 × 4.',
                '5-10-5 and L-drill reps: 6 to 8 at full effort with full rest, planting on the outside foot.',
                'Lateral bounds and skater jumps 3 × 6 each side.',
            ]),
            ('Field session', [
                'Cutting session with a thrower: under-and-deep and in-out cuts, focusing on a sharp plant and first step.',
                'Mirror drill and 1v1 marking reps in pairs: 6 × 10 s, the defender reacting to the attacker.',
            ]),
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
            ('Strength', [
                'Twice a week: back or front squat 4 × 5, Romanian deadlift 3 × 8, '
                'hip thrust 3 × 8, kettlebell swings 3 × 12.',
            ]),
            ('Power and plyometrics', [
                'Box jumps 4 × 4 and broad jumps 4 × 3, sticking every landing with knees in line with toes.',
                'Single-leg hops 3 × 5 each leg. Add depth drops 3 × 5 once you have a solid strength base.',
            ]),
            ('Field session', [
                'Skying drills: pairs jump for floaty hucks at the highest point, 3 sets of 5 contested jumps.',
                'Layout practice on soft grass or crash mats once jumps feel powerful.',
            ]),
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
            ('Conditioning programme', [
                'Six weeks, twice a week, after a good warm-up:',
                'Weeks 1 and 2: 15 s hard, 15 s easy for 10 minutes. 2 sets with 3 minutes rest.',
                'Weeks 3 and 4: 40 m shuttle sprints (20 out, 20 back) with 20 s rest. 3 sets of 6 to 8.',
                'Weeks 5 and 6: 4 × 4 minutes hard (breathing heavily, can only say a few words) with 3 minutes easy jogging.',
                'Plus one easy 30 to 40 minute run, bike or swim a week to build the aerobic base that speeds up recovery.',
            ]),
            ('Field session', [
                'Small-sided games: 3v3 or 4v4 on half a pitch, 3-minute points with 1 minute rest.',
                'Point simulation: 60 to 90 s of cut, sprint and jog patterns, 60 s rest, 8 reps.',
            ]),
            ('Strength', [
                'One session a week of single-leg work and calf raises keeps your legs robust for the running.',
                'Sleep, eat and drink well before tournaments. Fitness is wasted if you turn up tired.',
            ]),
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
