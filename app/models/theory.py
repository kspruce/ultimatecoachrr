# app/models/theory.py
"""Theory hub: sections of topics (markdown articles) with videos, tags and
linked drills, photos uploaded from a phone, who has read what, and the
topics coaches have asked the team to read."""
import re
from datetime import datetime

from slugify import slugify
from sqlalchemy import event

from app import db


def unique_slug(model, name, team_id, exclude_id=None):
    """A slug for `name` not yet used by another row of `model` on the team."""
    base = slugify(name)[:90] or 'section'
    slug, n = base, 2
    while True:
        query = model.query.filter_by(team_organization_id=team_id, slug=slug)
        if exclude_id:
            query = query.filter(model.id != exclude_id)
        if not query.first():
            return slug
        slug, n = f'{base}-{n}', n + 1


class TheorySection(db.Model):
    __tablename__ = 'theory_section'
    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'slug', name='uq_theory_section_team_slug'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100))
    description = db.Column(db.Text)
    order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationships
    topics = db.relationship('TheoryTopic', back_populates='section',
                             lazy='dynamic', cascade='all, delete-orphan')

    def generate_slug(self):
        # Routes set a slug that's unique on the team (unique_slug); this
        # is the fallback for sections made elsewhere
        if not self.slug:
            self.slug = slugify(self.name)

    @staticmethod
    def before_save(mapper, connection, target):
        target.generate_slug()

    def __repr__(self):
        return f'<TheorySection {self.name}>'


class TheoryTopic(db.Model):
    __tablename__ = 'theory_topic'

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('theory_section.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100))
    content = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    order = db.Column(db.Integer)
    # Drafts are only seen by coaches
    published = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationships
    section = db.relationship('TheorySection', back_populates='topics')
    author = db.relationship('User', foreign_keys=[created_by])
    editor = db.relationship('User', foreign_keys=[updated_by])
    related_drills = db.relationship('SavedDrill',
                                     secondary='topic_drill_association',
                                     backref=db.backref('theory_topics', lazy='dynamic'))
    related_videos = db.relationship('TheoryVideo',
                                     back_populates='topic',
                                     order_by='TheoryVideo.order',
                                     cascade='all, delete-orphan')
    tags = db.relationship('TheoryTag',
                           secondary='topic_tag_association',
                           order_by='TheoryTag.name',
                           backref=db.backref('topics', lazy='dynamic'))
    reads = db.relationship('TheoryRead', back_populates='topic', cascade='all, delete-orphan')
    assignment = db.relationship('TheoryAssignment', back_populates='topic', uselist=False,
                                 cascade='all, delete-orphan')

    def generate_slug(self):
        if not self.slug:
            self.slug = slugify(self.name)

    @staticmethod
    def before_save(mapper, connection, target):
        target.generate_slug()

    @property
    def last_edited_by(self):
        return self.editor or self.author

    @property
    def last_edited_at(self):
        return self.updated_at or self.created_at

    def __repr__(self):
        return f'<TheoryTopic {self.name}>'


YOUTUBE_ID = re.compile(
    r'^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)'
    r'([A-Za-z0-9_-]{11})')
YOUTUBE_NOCOOKIE_ID = re.compile(r'^https?://(?:www\.)?youtube-nocookie\.com/embed/([A-Za-z0-9_-]{11})')
VIMEO_ID = re.compile(r'^https?://(?:www\.)?(?:player\.)?vimeo\.com/(?:video/)?(\d+)(?:/([0-9a-f]+))?')
YOUTUBE_START = re.compile(r'[?&#]t=(?:(\d+)h)?(?:(\d+)m)?(\d+)s?')


def video_embed_url(url):
    """The embeddable player URL for a YouTube or Vimeo link, else None."""
    url = (url or '').strip()
    match = YOUTUBE_ID.match(url) or YOUTUBE_NOCOOKIE_ID.match(url)
    if match:
        embed = f'https://www.youtube-nocookie.com/embed/{match.group(1)}'
        start = YOUTUBE_START.search(url)
        if start:
            h, m, s = (int(g or 0) for g in start.groups())
            embed += f'?start={h * 3600 + m * 60 + s}'
        return embed
    match = VIMEO_ID.match(url)
    if match:
        embed = f'https://player.vimeo.com/video/{match.group(1)}'
        if match.group(2):  # unlisted videos carry a privacy hash
            embed += f'?h={match.group(2)}'
        return embed
    return None


class TheoryVideo(db.Model):
    __tablename__ = 'theory_video'

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('theory_topic.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationship
    topic = db.relationship('TheoryTopic', back_populates='related_videos')

    @property
    def embed_url(self):
        return video_embed_url(self.url)

    def __repr__(self):
        return f'<TheoryVideo {self.title}>'


class TheoryTag(db.Model):
    __tablename__ = 'theory_tag'
    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'name', name='uq_theory_tag_team_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    def __repr__(self):
        return f'<TheoryTag {self.name}>'


class TheoryImage(db.Model):
    """A photo uploaded from the editor, resized and kept in the database
    (like drill diagrams) so it survives redeploys without file storage."""
    __tablename__ = 'theory_image'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    mime_type = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Text, nullable=False)  # base64
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TheoryRead(db.Model):
    """A player has marked a topic as read."""
    __tablename__ = 'theory_read'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'topic_id', name='uq_theory_read_user_topic'),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('theory_topic.id', ondelete='CASCADE'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    topic = db.relationship('TheoryTopic', back_populates='reads')
    user = db.relationship('User')


class TheoryAssignment(db.Model):
    """A topic the coaches have asked the whole team to read."""
    __tablename__ = 'theory_assignment'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('theory_topic.id', ondelete='CASCADE'),
                         nullable=False, unique=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    topic = db.relationship('TheoryTopic', back_populates='assignment')
    assigner = db.relationship('User')


# Association Tables
topic_drill_association = db.Table('topic_drill_association',
    db.Column('topic_id', db.Integer, db.ForeignKey('theory_topic.id', ondelete='CASCADE')),
    db.Column('drill_id', db.Integer, db.ForeignKey('saved_drill.id', ondelete='CASCADE'))
)

topic_tag_association = db.Table('topic_tag_association',
    db.Column('topic_id', db.Integer, db.ForeignKey('theory_topic.id', ondelete='CASCADE')),
    db.Column('tag_id', db.Integer, db.ForeignKey('theory_tag.id', ondelete='CASCADE'))
)

# Register event listeners for slug generation
event.listen(TheorySection, 'before_insert', TheorySection.before_save)
event.listen(TheorySection, 'before_update', TheorySection.before_save)
event.listen(TheoryTopic, 'before_insert', TheoryTopic.before_save)
event.listen(TheoryTopic, 'before_update', TheoryTopic.before_save)
