from app import db
from datetime import datetime

class Clip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=True)
    title = db.Column(db.String(100))
    start_time = db.Column(db.Integer)  # in seconds
    end_time = db.Column(db.Integer)    # in seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game = db.relationship('Game', back_populates='clips')
    point = db.relationship('Point', back_populates='clips')
    # Use backref for many-to-many relationship
    tags = db.relationship('ClipTag', 
                         secondary='clip_tag_relation',
                         backref=db.backref('clips', lazy='dynamic'))
    players = db.relationship('Player', 
                            secondary='clip_player',
                            backref=db.backref('clips', lazy='dynamic'))
    annotations = db.relationship('ClipAnnotation', back_populates='clip', cascade='all, delete-orphan')

    
    def __repr__(self):
        return f'<Clip {self.title}>'
    
    @property
    def tag_list(self):
        """Return a list of tags for this clip."""
        return [relation.tag for relation in self.tags]
    
    @property
    def embed_url(self):
        """Return the appropriate embed URL based on video source"""
        if self.video_source == 'youtube':
            return self.youtube_embed_url
        elif self.video_source == 'veo':
            # Implement Veo embed URL logic
            return self.veo_embed_url
        # Add more platforms as needed
        return None
    
    @property
    def player_list(self):
        """Return a list of players in this clip."""
        return [relation.player for relation in self.players]
    
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




class ClipTag(db.Model):
    __tablename__ = 'clip_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Association table for Clip-Tag relationship
    clip_tag_relation = db.Table('clip_tag_relation',
        db.Column('clip_id', db.Integer, db.ForeignKey('clip.id'), primary_key=True),
        db.Column('tag_id', db.Integer, db.ForeignKey('clip_tag.id'), primary_key=True),
        db.Column('created_at', db.DateTime, default=datetime.utcnow)
    )
    
    # Association table for Clip-Player relationship
    clip_player = db.Table('clip_player',
        db.Column('clip_id', db.Integer, db.ForeignKey('clip.id'), primary_key=True),
        db.Column('player_id', db.Integer, db.ForeignKey('player.id'), primary_key=True),
        db.Column('created_at', db.DateTime, default=datetime.utcnow)
    )

    def __repr__(self):
        return f'<ClipTag {self.name}>'



class ClipTagRelation(db.Model):
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('clip_tag.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ClipTagRelation {self.clip_id}-{self.tag_id}>'



class ClipPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ClipPlayer {self.clip_id}-{self.player_id}>'
