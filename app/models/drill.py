from datetime import datetime
from app import db  # Import your Flask-SQLAlchemy instance
from sqlalchemy import Integer, ForeignKey

class Drill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_public = db.Column(db.Boolean, default=False)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Relationship with frames
    frames = db.relationship('DrillFrame', backref='drill', lazy=True, cascade='all, delete-orphan')

class DrillFrame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drill_id = db.Column(db.Integer, db.ForeignKey('drill.id'), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)  # Order in animation
    name = db.Column(db.String(50))  # Optional name for the frame
    # Fix the relationship to TeamOrganization
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Store all elements as JSON (players, discs, lines, text)
    # This includes positions, colors, labels, etc.
    elements = db.Column(db.JSON, nullable=False)

class SavedDrill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    setup_instructions = db.Column(db.Text, nullable=True)
    recommended_duration = db.Column(db.Integer, nullable=True)
    min_players = db.Column(db.Integer, nullable=True)
    max_players = db.Column(db.Integer, nullable=True)
    skill_level = db.Column(db.String(20), nullable=True)
    focus_area = db.Column(db.String(100), nullable=True)
    equipment_needed = db.Column(db.String(200), nullable=True)
    ultiplay_embed = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))

    # Season plan fields (filled by `flask import-season`; all optional)
    external_id = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(200), nullable=True)
    is_standard_card = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    card_code = db.Column(db.String(20), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('team_organization_id', 'external_id',
                            name='uq_saved_drill_team_external_id'),
    )

    # Relationship to SessionComponent
    components = db.relationship('SessionComponent', back_populates='saved_drill', lazy='dynamic')
    diagrams = db.relationship('DrillDiagram', back_populates='saved_drill',
                               order_by='DrillDiagram.order',
                               cascade='all, delete-orphan')

    @property
    def first_diagram(self):
        return self.diagrams[0] if self.diagrams else None

    def __repr__(self):
        return f'<SavedDrill {self.title}>'


class DrillDiagram(db.Model):
    """A diagram image for a SavedDrill. A drill can have several (e.g. Flik step panels).

    Railway's disk is wiped on every deploy and S3 isn't in use, so the image
    itself is stored in the database (base64 text, so the JSON data exports
    keep working) and served by the session.drill_diagram_image route.
    image_url / svg_url hold that route's URL.
    """
    id = db.Column(db.Integer, primary_key=True)
    saved_drill_id = db.Column(db.Integer, db.ForeignKey('saved_drill.id', ondelete='CASCADE'),
                               nullable=False, index=True)
    order = db.Column(db.Integer, nullable=False, default=0)
    image_url = db.Column(db.String(500), nullable=True)
    svg_url = db.Column(db.String(500), nullable=True)
    caption = db.Column(db.String(255), nullable=True)
    step_label = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(100), nullable=True)
    image_data = db.Column(db.Text, nullable=True)  # base64
    image_mime = db.Column(db.String(50), nullable=True)
    image_hash = db.Column(db.String(64), nullable=True)  # sha256 of the raw image bytes
    svg_data = db.Column(db.Text, nullable=True)  # raw SVG markup
    svg_hash = db.Column(db.String(64), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    saved_drill = db.relationship('SavedDrill', back_populates='diagrams')

    def __repr__(self):
        return f'<DrillDiagram {self.saved_drill_id}#{self.order}>'