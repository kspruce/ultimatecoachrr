"""The playbook: offence and defence plays, drawn in the drill editor, with
who does what in each (roles), tags, a call and a hand signal, links to
theory topics, drills and clips, and who on the team has learned them.
Who plays which role is in app/models/team_role.py.

Plays are Draft (only coaches see them), In use, or Retired (kept, but off
the cards and the PDF)."""
from datetime import datetime

from app import db

# Association table must be defined before the models that use it
play_tag_association = db.Table('play_tag_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('play_tag.id'))
)

play_topic_association = db.Table('play_topic_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
    db.Column('topic_id', db.Integer, db.ForeignKey('theory_topic.id', ondelete='CASCADE'), primary_key=True)
)

play_drill_association = db.Table('play_drill_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
    db.Column('drill_id', db.Integer, db.ForeignKey('saved_drill.id', ondelete='CASCADE'), primary_key=True)
)

play_clip_association = db.Table('play_clip_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
    db.Column('clip_id', db.Integer, db.ForeignKey('clip.id', ondelete='CASCADE'), primary_key=True)
)

PLAY_TYPES = (('offense', 'Offence'), ('defense', 'Defence'))
PLAY_STATUSES = (('draft', 'Draft'), ('active', 'In use'), ('retired', 'Retired'))


class PlayTag(db.Model):
    __table_args__ = (db.UniqueConstraint('team_organization_id', 'name', name='uq_play_tag_team_name'),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    def __repr__(self):
        return f'<PlayTag {self.name}>'


class Formation(db.Model):
    """Team concepts used to live in the playbook. They were moved into
    Theory (an "Our system" section) by migration d7f9b1c3e5a7, which
    records the topic here so old links still lead somewhere. Nothing
    creates them any more."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    imgur_url = db.Column(db.String(255))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    moved_to_topic_id = db.Column(db.Integer, db.ForeignKey('theory_topic.id', ondelete='SET NULL'), nullable=True)


class Play(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    status = db.Column(db.String(10), nullable=False, default='active', server_default='active')
    call = db.Column(db.String(60))     # what's shouted on the line
    signal = db.Column(db.String(100))  # the hand signal
    description = db.Column(db.Text)
    formation_id = db.Column(db.Integer, db.ForeignKey('formation.id'))  # concepts: see Formation
    notes = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    image_url = db.Column(db.String(500))  # a photo or linked image, when it isn't drawn
    sort_order = db.Column(db.Integer)  # manual ordering in playbook + PDF (lower = first)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationships
    formation = db.relationship('Formation', backref='plays')
    tags = db.relationship('PlayTag', secondary=play_tag_association, order_by='PlayTag.name')
    assignments = db.relationship('PlayAssignment', back_populates='play', cascade='all, delete-orphan',
                                  order_by='PlayAssignment.order')
    theory_topics = db.relationship('TheoryTopic', secondary=play_topic_association,
                                    backref=db.backref('plays', order_by='Play.name'))
    drills = db.relationship('SavedDrill', secondary=play_drill_association, order_by='SavedDrill.title',
                             backref=db.backref('plays', lazy='dynamic'))
    clips = db.relationship('Clip', secondary=play_clip_association,
                            backref=db.backref('plays', lazy='dynamic'))
    learned = db.relationship('PlayLearned', back_populates='play', cascade='all, delete-orphan')
    to_learn = db.relationship('PlayToLearn', back_populates='play', uselist=False, cascade='all, delete-orphan')
    editor = db.relationship('User', foreign_keys=[updated_by])
    author = db.relationship('User', foreign_keys=[created_by])
    # Drawn in the drill editor: one per stage, the first holding the drawing
    diagrams = db.relationship('DrillDiagram', back_populates='play',
                               order_by='DrillDiagram.order',
                               cascade='all, delete-orphan')

    @property
    def editor_diagram(self):
        return next((d for d in self.diagrams if d.editor_json), None)

    @property
    def editor_diagrams(self):
        return [d for d in self.diagrams if d.editor_json]

    @property
    def stage_count(self):
        return len(self.editor_diagrams)

    @property
    def thumbnail(self):
        """The first drawn stage, else the play's photo or linked image."""
        first = self.editor_diagram
        return (first.image_url if first else None) or self.image_url

    @property
    def type_label(self):
        return dict(PLAY_TYPES).get(self.type, 'Play')

    @property
    def status_label(self):
        return dict(PLAY_STATUSES).get(self.status, 'In use')

    @property
    def is_draft(self):
        return self.status == 'draft'

    @property
    def is_retired(self):
        return self.status == 'retired'

    session_components = db.relationship('SessionComponent',
                                        secondary='play_session_component',
                                        backref=db.backref('plays', lazy='dynamic'))

    # Create association table
    play_session_component = db.Table('play_session_component',
        db.Column('play_id', db.Integer, db.ForeignKey('play.id')),
        db.Column('component_id', db.Integer, db.ForeignKey('session_component.id'))
    )


class PlayerPosition(db.Model):
    """A team role, such as "O-line initiation cutter". Coaches give players
    roles each season (PlayerRole, Team → Roles), and plays say what each
    role does (PlayAssignment). Kept under its old name and table: it was
    the playbook's list of positions."""
    LINES = [('O', 'O-line'), ('D', 'D-line'), ('', 'Either line')]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    line = db.Column(db.String(1))                    # 'O', 'D' or empty for either
    description = db.Column(db.String(200))
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    @property
    def line_label(self):
        return dict(self.LINES).get(self.line or '', 'Either line')

    def __repr__(self):
        return f'<Position {self.name}>'


class PlayAssignment(db.Model):
    """What one role does in one play."""
    id = db.Column(db.Integer, primary_key=True)
    play_id = db.Column(db.Integer, db.ForeignKey('play.id'))
    position_id = db.Column(db.Integer, db.ForeignKey('player_position.id'))
    instructions = db.Column(db.Text, nullable=False)
    order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationships
    position = db.relationship('PlayerPosition')
    play = db.relationship('Play', back_populates='assignments')


class PlayLearned(db.Model):
    """Someone has marked a play as learned."""
    __tablename__ = 'play_learned'
    __table_args__ = (db.UniqueConstraint('user_id', 'play_id', name='uq_play_learned_user_play'),)

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    play_id = db.Column(db.Integer, db.ForeignKey('play.id', ondelete='CASCADE'), nullable=False, index=True)
    learned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    play = db.relationship('Play', back_populates='learned')


class PlayToLearn(db.Model):
    """A play the coaches have asked the team to learn (by a date)."""
    __tablename__ = 'play_to_learn'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    play_id = db.Column(db.Integer, db.ForeignKey('play.id', ondelete='CASCADE'), nullable=False, unique=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    play = db.relationship('Play', back_populates='to_learn')
