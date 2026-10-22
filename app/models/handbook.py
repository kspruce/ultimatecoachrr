# app/models/handbook.py
"""The leadership handbook: a team's pages for captains and coaches.
Filled by `flask import-handbook`; shown under /handbook to leaders when the
team has the Leadership handbook feature switched on."""
from datetime import datetime

from app import db


class HandbookPage(db.Model):
    __tablename__ = 'handbook_page'
    __table_args__ = (db.UniqueConstraint('team_organization_id', 'slug', name='uq_handbook_page_team_slug'),)

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    slug = db.Column(db.String(80), nullable=False)      # its address: /handbook/<slug>
    section = db.Column(db.String(40), nullable=False)   # a key from app.utils.handbook.SECTIONS
    position = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(200), nullable=False)
    lead = db.Column(db.Text)
    body_html = db.Column(db.Text)                       # sanitised on the way in
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<HandbookPage {self.slug}>'
