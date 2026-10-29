from app import db
from datetime import datetime

# Association table must be defined before the models that use it
play_tag_association = db.Table('play_tag_association',
    db.Column('play_id', db.Integer, db.ForeignKey('play.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('play_tag.id'))
)

class PlayTag(db.Model):
    __table_args__ = (db.UniqueConstraint('team_organization_id', 'name', name='uq_play_tag_team_name'),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    def __repr__(self):
        return f'<PlayTag {self.name}>'

class Formation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    imgur_url = db.Column(db.String(255))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
class Play(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20))  # offense/defense
    description = db.Column(db.Text)
    formation_id = db.Column(db.Integer, db.ForeignKey('formation.id'))
    notes = db.Column(db.Text)
    ultiplay_embed = db.Column(db.Text)
    image_url = db.Column(db.String(255))  # static diagram (e.g. ImgBB link) shown online + used in PDF export
    sort_order = db.Column(db.Integer)  # manual ordering in playbook + PDF (lower = first)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    formation = db.relationship('Formation', backref='plays')
    tags = db.relationship('PlayTag', secondary=play_tag_association)
    # Drawn in the drill editor: one per stage, the first holding the drawing
    diagrams = db.relationship('DrillDiagram', back_populates='play',
                               order_by='DrillDiagram.order',
                               cascade='all, delete-orphan')

    @property
    def editor_diagram(self):
        return next((d for d in self.diagrams if d.editor_json), None)

    @property
    def editor_diagrams(self):
        return [d for d in self.diagrams if d.editor_json]

    @property
    def stage_count(self):
        return len(self.editor_diagrams)
    
    session_components = db.relationship('SessionComponent', 
                                        secondary='play_session_component',
                                        backref=db.backref('plays', lazy='dynamic'))
    
    # Create association table
    play_session_component = db.Table('play_session_component',
        db.Column('play_id', db.Integer, db.ForeignKey('play.id')),
        db.Column('component_id', db.Integer, db.ForeignKey('session_component.id'))
    )    
    
class PlayerPosition(db.Model):
    """A team role, such as "O-line initiation cutter". Coaches give players
    roles each season (PlayerRole, Team → Roles), and plays say what each
    role does (PlayAssignment). Kept under its old name and table: it was
    the playbook's list of positions."""
    LINES = [('O', 'O-line'), ('D', 'D-line'), ('', 'Either line')]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    line = db.Column(db.String(1))                    # 'O', 'D' or empty for either
    description = db.Column(db.String(200))
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    @property
    def line_label(self):
        return dict(self.LINES).get(self.line or '', 'Either line')

    def __repr__(self):
        return f'<Position {self.name}>'

class PlayAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    play_id = db.Column(db.Integer, db.ForeignKey('play.id'))
    position_id = db.Column(db.Integer, db.ForeignKey('player_position.id'))
    instructions = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    position = db.relationship('PlayerPosition')
    play = db.relationship('Play', backref='assignments')
