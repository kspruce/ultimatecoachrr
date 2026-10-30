# app/models/feedback.py
from app import db
from datetime import datetime


class PlayerFeedback(db.Model):
    __tablename__ = 'player_feedback'

    CONTEXT_TAGS = ['In-game', 'Drill', 'Debrief', 'Tournament', 'General']
    # What the note is: an observation, something to keep doing, or to work on
    KINDS = [('note', 'Note'), ('keep', 'Keep doing'), ('work_on', 'Work on')]

    id = db.Column(db.Integer, primary_key=True)

    # Who the note is about (Player record)
    player_id = db.Column(
        db.Integer,
        db.ForeignKey('player.id'),
        nullable=False,
        index=True
    )

    # Who wrote the note (User record — the coach/admin). Empty for notes
    # brought over from the old notes box on the player page.
    coach_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=True,
        index=True
    )

    # Optional: which session was this note captured during
    session_id = db.Column(
        db.Integer,
        db.ForeignKey('session_plan.id'),
        nullable=True,
        index=True
    )

    # Optional: the game or clip it's about
    game_id = db.Column(db.Integer, db.ForeignKey('game.id', ondelete='SET NULL'), nullable=True, index=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id', ondelete='SET NULL'), nullable=True, index=True)

    # The player sees it under My Feedback; otherwise it's for coaches only
    shared = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # When the player first saw it (shared notes only)
    seen_at = db.Column(db.DateTime, nullable=True)

    # The note content (qualitative, no ratings)
    content = db.Column(db.Text, nullable=False)

    # Context label: 'In-game', 'Drill', 'Debrief', 'Tournament', 'General'
    context_tag = db.Column(db.String(50), nullable=False, default='General')
    kind = db.Column(db.String(10), nullable=False, default='note', server_default='note')
    # The goal it's about, if any
    goal_id = db.Column(db.Integer, db.ForeignKey('player_goal.id', ondelete='SET NULL'), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────────
    player = db.relationship(
        'Player',
        back_populates='feedback_entries'
    )
    coach = db.relationship(
        'User',
        foreign_keys=[coach_id],
        backref=db.backref('feedback_given', lazy='dynamic')
    )
    session = db.relationship(
        'SessionPlan',
        foreign_keys=[session_id],
        backref=db.backref('feedback_entries', lazy='dynamic')
    )
    game = db.relationship('Game', foreign_keys=[game_id])
    clip = db.relationship('Clip', foreign_keys=[clip_id])

    goal = db.relationship('PlayerGoal', back_populates='notes')
    replies = db.relationship('FeedbackReply', back_populates='feedback', order_by='FeedbackReply.created_at',
                              cascade='all, delete-orphan', passive_deletes=True)

    @property
    def author(self):
        return self.coach.username if self.coach else 'Coach'

    @property
    def kind_label(self):
        return dict(self.KINDS).get(self.kind or 'note', 'Note')

    def __repr__(self):
        return f'<PlayerFeedback id={self.id} player={self.player_id} tag={self.context_tag}>'


class FeedbackReply(db.Model):
    """A reply on a note: the player answering a note shared with them, or a
    coach answering back."""
    __tablename__ = 'feedback_reply'

    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('player_feedback.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    from_player = db.Column(db.Boolean, nullable=False, default=False)  # the player wrote it (not a coach)
    seen_at = db.Column(db.DateTime, nullable=True)  # read by the other side
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    feedback = db.relationship('PlayerFeedback', back_populates='replies')
    user = db.relationship('User')

    @property
    def author(self):
        return self.user.username if self.user else ('Player' if self.from_player else 'Coach')


class PlayerFocus(db.Model):
    """What a player should keep in mind: a few lines from the coaches, for
    the next training or tournament or until changed. A new one replaces the
    last (which stays as history); the player always sees it."""
    __tablename__ = 'player_focus'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session_plan.id', ondelete='SET NULL'), nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id', ondelete='SET NULL'), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)  # the current one (cleared or replaced: False)
    set_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    seen_at = db.Column(db.DateTime, nullable=True)  # when the player first saw it

    player = db.relationship('Player')
    session = db.relationship('SessionPlan')
    tournament = db.relationship('Tournament')
    coach = db.relationship('User')

    @property
    def event_date(self):
        if self.tournament:
            return self.tournament.start_date
        if self.session:
            return self.session.date
        return None

    @property
    def for_label(self):
        """'For Nationals (Sat 7 Nov)' / 'For Tuesday training (Tue 3 Nov)' / ''."""
        name = self.tournament.name if self.tournament else self.session.title if self.session else None
        if not name:
            return ''
        when = self.event_date
        return f'For {name}' + (f" ({when.strftime('%a %-d %b')})" if when else '')

    def is_past(self, today):
        return bool(self.event_date and self.event_date < today)


class PlayerGoal(db.Model):
    """One of a player's goals: theirs or set with their coaches. Notes can
    be about a goal (PlayerFeedback.goal)."""
    __tablename__ = 'player_goal'
    HORIZONS = [('short', '1–3 months'), ('mid', '3–6 months'), ('long', '6+ months'), ('skill', 'Skill to develop')]
    STATUSES = [('active', 'Working on it'), ('achieved', 'Achieved'), ('dropped', 'Dropped')]

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text)
    horizon = db.Column(db.String(10), nullable=False, default='short')
    status = db.Column(db.String(10), nullable=False, default='active')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    done_at = db.Column(db.DateTime, nullable=True)  # achieved or dropped

    player = db.relationship('Player')
    author = db.relationship('User')
    notes = db.relationship('PlayerFeedback', back_populates='goal', order_by='PlayerFeedback.created_at.desc()')

    @property
    def horizon_label(self):
        return dict(self.HORIZONS).get(self.horizon, '')

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, '')


class PlayerReview(db.Model):
    """A written review of how a player's going (mid-season, end of season):
    what's gone well, what to work on, next steps. Coaches only until shared;
    the player can add their own comment."""
    __tablename__ = 'player_review'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False, index=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(120), nullable=False)
    went_well = db.Column(db.Text)
    work_on = db.Column(db.Text)
    next_steps = db.Column(db.Text)
    player_comment = db.Column(db.Text)
    shared = db.Column(db.Boolean, nullable=False, default=False)
    seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = db.relationship('Player')
    coach = db.relationship('User')
