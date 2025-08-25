from app_factory import db
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
        # Split timestamp into components
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

class ClipAnnotation(db.Model):
    __tablename__ = 'clip_annotation'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    timestamp = db.Column(db.Integer)
    event_type = db.Column(db.String(50))
    our_score = db.Column(db.Integer)
    their_score = db.Column(db.Integer)
    offense = db.Column(db.String(20))
    defense = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True) # Nullable for migration
    
    # Relationship
    clip = db.relationship('Clip', back_populates='annotations')

    @property
    def formatted_timestamp(self):
        if self.timestamp is None:
            return ""
        hours = self.timestamp // 3600
        minutes = (self.timestamp % 3600) // 60
        seconds = self.timestamp % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
       
    
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
