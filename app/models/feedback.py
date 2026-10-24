# app/models/feedback.py
from app import db
from datetime import datetime


class PlayerFeedback(db.Model):
    __tablename__ = 'player_feedback'

    CONTEXT_TAGS = ['In-game', 'Drill', 'Debrief', 'Tournament', 'General']

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

    @property
    def author(self):
        return self.coach.username if self.coach else 'Coach'

    def __repr__(self):
        return f'<PlayerFeedback id={self.id} player={self.player_id} tag={self.context_tag}>'
