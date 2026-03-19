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

    # Who wrote the note (User record — the coach/admin)
    coach_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False,
        index=True
    )

    # Optional: which session was this note captured during
    session_id = db.Column(
        db.Integer,
        db.ForeignKey('session_plan.id'),
        nullable=True,
        index=True
    )

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

    def __repr__(self):
        return f'<PlayerFeedback id={self.id} player={self.player_id} tag={self.context_tag}>'
