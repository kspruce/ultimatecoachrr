from app import db
from datetime import datetime

class ClipAnnotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)  # in seconds
    event_type = db.Column(db.String(50), nullable=False)  # point_start, drill_start, turnover, score, etc.
    our_score = db.Column(db.Integer, nullable=True)
    their_score = db.Column(db.Integer, nullable=True)
    offense = db.Column(db.String(50), nullable=True)  # us, them
    defense = db.Column(db.String(50), nullable=True)  # us, them
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ClipAnnotation {self.event_type} at {self.timestamp}s>'
    
    @property
    def formatted_timestamp(self):
        """Return the timestamp formatted as MM:SS."""
        minutes = self.timestamp // 60
        seconds = self.timestamp % 60
        return f"{minutes}:{seconds:02d}"
    
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
