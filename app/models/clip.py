from app import db
from datetime import datetime

# Association tables
clip_tag_relation = db.Table('clip_tag_relation',
    db.Column('clip_id', db.Integer, db.ForeignKey('clip.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('clip_tag.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

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
    youtube_link = db.Column(db.String(200))  # Added for YouTube functionality
    video_source = db.Column(db.String(20), default='youtube')  # Added for multiple video sources
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        if self.start_time:
            embed_url += f'?start={self.start_time}'
            if self.end_time:
                embed_url += f'&end={self.end_time}'
        elif self.end_time:
            embed_url += f'?end={self.end_time}'
        
        return embed_url

    @property
    def veo_embed_url(self):
        """Return the Veo embed URL for this clip."""
        # Implement Veo-specific embedding logic here
        return None


class ClipTag(db.Model):
    __tablename__ = 'clip_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ClipTag {self.name}>'


