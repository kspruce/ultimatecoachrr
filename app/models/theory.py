# app/models/theory.py
from app import db
from datetime import datetime
from flask_login import current_user
from slugify import slugify
from sqlalchemy import event  # Add this import at the top

class TheorySection(db.Model):
    __tablename__ = 'theory_section'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    description = db.Column(db.Text)
    order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    topics = db.relationship('TheoryTopic', back_populates='section', 
                           lazy='dynamic', cascade='all, delete-orphan')

    def generate_slug(self):
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    section = db.relationship('TheorySection', back_populates='topics')
    # Add this to the existing relationships in TheoryTopic
    related_drills = db.relationship('SavedDrill', 
                                   secondary='topic_drill_association',
                                   backref=db.backref('theory_topics', lazy='dynamic'))
    related_videos = db.relationship('TheoryVideo', 
                                   back_populates='topic',
                                   cascade='all, delete-orphan')
    tags = db.relationship('TheoryTag', 
                          secondary='topic_tag_association',
                          backref=db.backref('topics', lazy='dynamic'))

    def generate_slug(self):
        if not self.slug:
            self.slug = slugify(self.name)

    @staticmethod
    def before_save(mapper, connection, target):
        target.generate_slug()

    def __repr__(self):
        return f'<TheoryTopic {self.name}>'

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
    
    # Relationship
    topic = db.relationship('TheoryTopic', back_populates='related_videos')

    def __repr__(self):
        return f'<TheoryVideo {self.title}>'

class TheoryTag(db.Model):
    __tablename__ = 'theory_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TheoryTag {self.name}>'


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
