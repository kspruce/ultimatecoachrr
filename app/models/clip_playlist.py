from datetime import datetime

from app import db


class ClipPlaylist(db.Model):
    """An ordered set of clips to watch back to back, e.g. a film session."""
    __tablename__ = 'clip_playlist'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)

    items = db.relationship('ClipPlaylistItem', back_populates='playlist',
                            order_by='ClipPlaylistItem.position',
                            cascade='all, delete-orphan')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<ClipPlaylist {self.title}>'

    def visible_items(self, sees_hidden):
        """Items in order, leaving out clips hidden from players unless sees_hidden."""
        return [item for item in self.items if sees_hidden or not item.clip.is_hidden]


class ClipPlaylistItem(db.Model):
    __tablename__ = 'clip_playlist_item'

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('clip_playlist.id'), nullable=False)
    clip_id = db.Column(db.Integer, db.ForeignKey('clip.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(300))  # what to watch for in this clip
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)

    playlist = db.relationship('ClipPlaylist', back_populates='items')
    # Deleting a clip takes it out of every playlist
    clip = db.relationship('Clip', backref=db.backref('playlist_items', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ClipPlaylistItem {self.position} of playlist {self.playlist_id}>'
