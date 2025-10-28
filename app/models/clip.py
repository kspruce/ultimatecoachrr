from app import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

# Association table for clip tags (video-level)
clip_tag_relation = db.Table('clip_tag_relation',
    db.Column('clip_id', db.Integer, db.ForeignKey('clip.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('clip_tag.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# Association table for clip players
clip_player = db.Table('clip_player',
    db.Column('clip_id', db.Integer, db.ForeignKey('clip.id'), primary_key=True),
    db.Column('player_id', db.Integer, db.ForeignKey('player.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

class Clip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=True)
    title = db.Column(db.String(100))
    start_time = db.Column(db.Integer)  # in seconds
    end_time = db.Column(db.Integer)    # in seconds
    youtube_link = db.Column(db.String(200))
    video_source = db.Column(db.String(20), default='youtube')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    description = db.Column(db.Text, nullable=True)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # New fields for enhanced clip management
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)  # Highlight important clips
    view_count = db.Column(db.Integer, default=0)
    
    # Relationships
    game = db.relationship('Game', back_populates='clips')
    point = db.relationship('Point', back_populates='clips')
    tags = db.relationship('ClipTag', 
                         secondary=clip_tag_relation,
                         backref=db.backref('clips', lazy='dynamic'))
    players = db.relationship('Player', 
                            secondary=clip_player,
                            backref=db.backref('clip_appearances', lazy='dynamic'))
    annotations = db.relationship('ClipAnnotation', back_populates='clip', cascade='all, delete-orphan')
    created_by = db.relationship('User', backref='clips_created', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<Clip {self.title}>'

    @property
    def tag_list(self):
        """Return a list of tags for this clip."""
        return self.tags

    @property
    def player_list(self):
        """Return a list of players in this clip."""
        return self.players

    @property
    def embed_url(self):
        """Return the appropriate embed URL based on video source"""
        if self.video_source == 'youtube':
            return self.youtube_embed_url
        elif self.video_source == 'veo':
            return self.veo_embed_url
        return None

    @property
    def youtube_embed_url(self):
        """Return the YouTube embed URL for this clip."""
        if not self.youtube_link:
            return None
        
        # Extract video ID from YouTube link
        if 'youtube.com/watch?v=' in self.youtube_link:
            video_id = self.youtube_link.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in self.youtube_link:
            video_id = self.youtube_link.split('youtu.be/')[1].split('?')[0]
        else:
            return None
        
        # Create embed URL with start time if available
        embed_url = f'https://www.youtube.com/embed/{video_id}'
        params = []
        
        if self.start_time:
            params.append(f'start={self.start_time}')
        if self.end_time:
            params.append(f'end={self.end_time}')
        
        if params:
            embed_url += '?' + '&'.join(params)
        
        return embed_url

    @property
    def veo_embed_url(self):
        """Return the Veo embed URL for this clip."""
        # Implement Veo-specific embedding logic here
        return None
    
    @property
    def duration(self):
        """Return the duration of the clip in seconds"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def annotation_count(self):
        """Return the number of annotations for this clip"""
        return len(self.annotations)
    
    @property
    def key_moments_count(self):
        """Return the number of key moment annotations"""
        return sum(1 for ann in self.annotations if ann.is_key_moment)


class ClipTag(db.Model):
    __tablename__ = 'clip_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))  # e.g., "Video Type", "Context"
    parent_tag_id = db.Column(db.Integer, db.ForeignKey('clip_tag.id'), nullable=True)
    color = db.Column(db.String(7), default='#3F51B5')  # Hex color
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Self-referential relationship for hierarchical tags
    children = db.relationship('ClipTag',
                              backref=db.backref('parent', remote_side=[id]),
                              lazy='dynamic')
    
    def __repr__(self):
        return f'<ClipTag {self.name}>'
    
    @property
    def full_path(self):
        """Return the full hierarchical path of this tag"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
    
    @property
    def clip_count(self):
        """Return the number of clips using this tag"""
        return self.clips.count()


class ClipPointSegment(db.Model):
    """Model to track point segments within a clip for point-by-point analysis"""
    __tablename__ = 'clip_point_segments'
    
    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    point_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Integer, nullable=False)  # seconds
    end_time = db.Column(db.Integer, nullable=True)     # seconds or None while open
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    # Relationships
    clip = db.relationship('Clip', backref=db.backref('point_segments', cascade='all, delete-orphan', lazy='dynamic'))
    created_by = db.relationship('User', backref='point_segments_created', foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f'<ClipPointSegment Point {self.point_number} in Clip {self.clip_id}>'
    
    @property
    def duration(self):
        """Return the duration of this segment in seconds"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None