# app/models/leadership.py
"""The Leadership hub: ideas, articles and footage that coaches, captains and
team admins share and talk over, for leaders only. Shown under /leadership
when the team has the Leadership hub switched on (the same switch as the
leadership handbook, which lives in the hub too)."""
from datetime import datetime

from app import db


class LeadershipPost(db.Model):
    __tablename__ = 'leadership_post'

    KINDS = [('idea', 'Idea', 'bi-lightbulb'), ('article', 'Article', 'bi-newspaper'),
             ('footage', 'Footage', 'bi-camera-video'), ('question', 'Question', 'bi-question-circle')]
    KIND_KEYS = [k for k, _, _ in KINDS]
    KIND_LABELS = {k: label for k, label, _ in KINDS}
    KIND_ICONS = {k: icon for k, _, icon in KINDS}
    STATUSES = [('open', 'Open'), ('actioned', 'Actioned'), ('archived', 'Archived')]
    STATUS_KEYS = [k for k, _ in STATUSES]
    STATUS_LABELS = dict(STATUSES)

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    kind = db.Column(db.String(20), nullable=False, default='idea')
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500))                       # an article or video link
    body = db.Column(db.Text)                             # plain text; links and timestamps linked on display
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id', ondelete='SET NULL'), nullable=True)
    start_seconds = db.Column(db.Integer)                 # where the footage worth watching starts
    status = db.Column(db.String(20), nullable=False, default='open', server_default='open')
    pinned = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    on_agenda = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # A question a player asked the leaders ("Ask the leaders"): the player
    # (the author) sees it and the replies not marked leaders-only.
    from_player = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # What it's about: a key of app.utils.ask_leaders.SUBJECTS and the row's id
    subject_type = db.Column(db.String(20))
    subject_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    author = db.relationship('User', foreign_keys=[author_id])
    clip = db.relationship('Clip')
    comments = db.relationship('LeadershipComment', back_populates='post', cascade='all, delete-orphan',
                               order_by='LeadershipComment.created_at')

    @property
    def author_name(self):
        return self.author.username if self.author else 'Someone'

    @property
    def kind_label(self):
        return self.KIND_LABELS.get(self.kind, self.kind)

    @property
    def kind_icon(self):
        return self.KIND_ICONS.get(self.kind, 'bi-chat')

    def visible_comments(self):
        """The replies the asking player sees."""
        return [c for c in self.comments if not c.leaders_only]

    def answered(self):
        """A leader has replied where the player can see it."""
        return any(c.author_id != self.author_id for c in self.visible_comments())

    @property
    def player_status(self):
        """How the player sees their question."""
        if self.status != 'open':
            return 'closed'
        return 'answered' if self.answered() else 'waiting'

    def __repr__(self):
        return f'<LeadershipPost {self.id} {self.title!r}>'


class LeadershipComment(db.Model):
    __tablename__ = 'leadership_comment'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('leadership_post.id', ondelete='CASCADE'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    body = db.Column(db.Text, nullable=False)
    # On a player's question: a note only the leaders see (not the player)
    leaders_only = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    post = db.relationship('LeadershipPost', back_populates='comments')
    author = db.relationship('User')

    @property
    def author_name(self):
        return self.author.username if self.author else 'Someone'


class LeadershipRead(db.Model):
    """When a leader last opened a post, for the unread markers."""
    __tablename__ = 'leadership_read'
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_leadership_read_user_post'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('leadership_post.id', ondelete='CASCADE'), nullable=False, index=True)
    seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
