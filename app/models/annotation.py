from app import db
from datetime import datetime

def seconds_to_timestamp(seconds):
    """Convert seconds to HH:MM:SS format"""
    if seconds is None:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def timestamp_to_seconds(timestamp):
    """Convert HH:MM:SS format to seconds"""
    if not timestamp:
        return None
    try:
        parts = timestamp.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        else:
            return int(parts[0])
    except (ValueError, IndexError):
        return None

# Association table for annotation tags
annotation_tag_relation = db.Table('annotation_tag_relation',
    db.Column('annotation_id', db.Integer, db.ForeignKey('clip_annotation.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('annotation_tag.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# Association table for annotation players
annotation_player = db.Table('annotation_player',
    db.Column('annotation_id', db.Integer, db.ForeignKey('clip_annotation.id'), primary_key=True),
    db.Column('player_id', db.Integer, db.ForeignKey('player.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

class ClipAnnotation(db.Model):
    __tablename__ = 'clip_annotation'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Track who created it
    timestamp = db.Column(db.Integer)
    event_type = db.Column(db.String(50))
    our_score = db.Column(db.Integer)
    their_score = db.Column(db.Integer)
    offense = db.Column(db.String(20))
    defense = db.Column(db.String(20))
    notes = db.Column(db.Text)

    # Enhanced functionality fields
    title = db.Column(db.String(200))  # Brief title for the annotation
    is_key_moment = db.Column(db.Boolean, default=False)  # Flag important moments
    visibility = db.Column(db.String(20), default='team')  # 'team', 'coaches', 'specific', 'private'
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # For 'specific' visibility

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    # Relationships
    clip = db.relationship('Clip', back_populates='annotations')
    created_by = db.relationship('User', backref='annotations_created', foreign_keys=[user_id])
    targeted_user = db.relationship('User', backref='targeted_annotations', foreign_keys=[target_user_id])
    tags = db.relationship('AnnotationTag', 
                          secondary=annotation_tag_relation,
                          backref=db.backref('annotations', lazy='dynamic'))
    players = db.relationship('Player',
                            secondary=annotation_player,
                            backref=db.backref('annotation_appearances', lazy='dynamic'))

    @property
    def formatted_timestamp(self):
        if self.timestamp is None:
            return ""
        return seconds_to_timestamp(self.timestamp)
    
    @property
    def youtube_timestamp_link(self):
        """Return a direct link to this timestamp in the YouTube video."""
        if not self.clip or not self.clip.youtube_link:
            return None
        
        # Extract video ID from YouTube link
        if 'youtube.com/watch?v=' in self.clip.youtube_link:
            video_id = self.clip.youtube_link.split('v=')[1].split('&')[0]
            return f"https://www.youtube.com/watch?v={video_id}&t={self.timestamp}s"
        elif 'youtu.be/' in self.clip.youtube_link:
            video_id = self.clip.youtube_link.split('youtu.be/')[1].split('?')[0]
            return f"https://youtu.be/{video_id}?t={self.timestamp}s"
        
        return None
    
    @property
    def tag_names(self):
        """Return a list of tag names for this annotation"""
        return [tag.name for tag in self.tags]
    
    @property
    def primary_category(self):
        """Return the primary category of this annotation based on tags"""
        if not self.tags:
            return "Uncategorized"
        # Return the category of the first tag
        return self.tags[0].category if self.tags[0].category else "General"


class AnnotationTag(db.Model):
    __tablename__ = 'annotation_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))  # e.g., "Offense", "Defense", "Skills"
    parent_tag_id = db.Column(db.Integer, db.ForeignKey('annotation_tag.id'), nullable=True)
    color = db.Column(db.String(7), default='#3F51B5')  # Hex color for UI
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Self-referential relationship for hierarchical tags
    children = db.relationship('AnnotationTag',
                              backref=db.backref('parent', remote_side=[id]),
                              lazy='dynamic')
    
    def __repr__(self):
        return f'<AnnotationTag {self.name}>'
    
    @property
    def full_path(self):
        """Return the full hierarchical path of this tag"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
    
    @property
    def annotation_count(self):
        """Return the number of annotations using this tag"""
        return self.annotations.count()
