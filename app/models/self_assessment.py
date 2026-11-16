# app/models/self_assessment.py
"""Player self-assessment ("check-ins"): a quick tap-through rubric a player
fills in about how they've been going, plus their own notes.

Each team has its own rubric statements (seeded from DEFAULT_ITEMS and then
editable by coaches). Coaches can nudge the team to fill one in (after a
tournament, monthly, mid-season). Coaches always see every check-in."""
from datetime import datetime

from app import db


SECTIONS = [
    ('offence', 'Offence'),
    ('cutting', 'Cutting'),
    ('handling', 'Handling'),
    ('defence', 'Defence'),
    ('mental', 'Mental & spirit'),
]
SECTION_LABELS = dict(SECTIONS)

# How often, not how good: easier to answer honestly. No middle option.
SCALE = [(1, 'Rarely'), (2, 'Sometimes'), (3, 'Mostly'), (4, 'Always')]
SCALE_LABELS = dict(SCALE)

# The base statements every team starts with (coaches can change them).
DEFAULT_ITEMS = {
    'offence': [
        'I knew my job in the set (stack, ho-stack, play call)',
        'I kept my spacing and kept lanes open',
        'I took the open option instead of forcing a hero throw',
        'I talked: spacing calls, "up", stall counts',
        'When we stalled out, I helped reset instead of standing still',
    ],
    'cutting': [
        'I timed my cuts for when the thrower could actually throw',
        'I sold the cut: set up my defender, then changed direction sharply',
        'I ran full speed through the cut',
        'I cleared out fast when I wasn\'t thrown to',
        'After catching, I kept running for the next pass',
    ],
    'handling': [
        'I caught cleanly, with no drops',
        'I looked upfield first and saw the open cutter',
        'I used pivots and fakes to get past the mark',
        'My throws were catchable and led the receiver',
        'I stayed calm at a high stall count and used the reset',
    ],
    'defence': [
        'On the mark, I held the force and gave up no easy break throws',
        'I kept good body position: right side, between my player and the space',
        'I worked hard every point, including chasing deep',
        'I called out threats: "strike", "up", switches',
        'I switched quickly when the disc turned over',
    ],
    'mental': [
        'I bounced back quickly after a mistake',
        'I stayed composed in close points and under pressure',
        'I was a positive voice on the field and the sideline',
        'I knew the rules and made or resolved calls calmly and fairly',
        'I treated opponents with respect and played with good spirit',
    ],
}


class RubricItem(db.Model):
    """One statement on a team's rubric. Hidden rather than deleted once it
    has been answered, so old check-ins keep their wording."""
    __tablename__ = 'rubric_item'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    section = db.Column(db.String(20), nullable=False)
    text = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def section_label(self):
        return SECTION_LABELS.get(self.section, self.section)


class CheckInRequest(db.Model):
    """A coach's nudge: "fill in a check-in" for the whole team, e.g. after
    a tournament, monthly or mid-season. Open until closed (or a month old)."""
    __tablename__ = 'check_in_request'
    OPEN_DAYS = 30

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id', ondelete='SET NULL'), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id', ondelete='SET NULL'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    tournament = db.relationship('Tournament')
    session = db.relationship('SessionPlan')
    coach = db.relationship('User')
    assessments = db.relationship('SelfAssessment', back_populates='request')

    def is_open(self, now=None):
        now = now or datetime.utcnow()
        return self.closed_at is None and (now - self.created_at).days < self.OPEN_DAYS


class SelfAssessment(db.Model):
    """One check-in by a player: their rubric taps and their own notes."""
    __tablename__ = 'self_assessment'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    request_id = db.Column(db.Integer, db.ForeignKey('check_in_request.id', ondelete='SET NULL'), nullable=True, index=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id', ondelete='SET NULL'), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(120))
    notes = db.Column(db.Text)
    # The statement the player wants to focus on next
    focus_item_id = db.Column(db.Integer, db.ForeignKey('rubric_item.id', ondelete='SET NULL'), nullable=True)
    seen_by_coach_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = db.relationship('Player')
    request = db.relationship('CheckInRequest', back_populates='assessments')
    tournament = db.relationship('Tournament')
    session = db.relationship('SessionPlan')
    focus_item = db.relationship('RubricItem')
    scores = db.relationship('SelfAssessmentScore', back_populates='assessment',
                             cascade='all, delete-orphan', passive_deletes=True)

    @property
    def label(self):
        if self.title:
            return self.title
        if self.request:
            return self.request.title
        if self.tournament:
            return self.tournament.name
        if self.session:
            return self.session.title
        return 'Check-in'

    def score_map(self):
        return {s.item_id: s.score for s in self.scores}

    def section_averages(self):
        """{section: average score} for the sections answered."""
        totals = {}
        for s in self.scores:
            if s.item is None:
                continue
            t = totals.setdefault(s.item.section, [0, 0])
            t[0] += s.score
            t[1] += 1
        return {sec: round(a / n, 1) for sec, (a, n) in totals.items() if n}


class SelfAssessmentScore(db.Model):
    __tablename__ = 'self_assessment_score'

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey('self_assessment.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('rubric_item.id', ondelete='CASCADE'), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)

    assessment = db.relationship('SelfAssessment', back_populates='scores')
    item = db.relationship('RubricItem')

    __table_args__ = (db.UniqueConstraint('assessment_id', 'item_id', name='uq_self_assessment_score_item'),)
