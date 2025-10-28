from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, TextAreaField, SelectField, SelectMultipleField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Optional, NumberRange
from app.models.annotation import AnnotationTag
from app.models.player import Player


class AnnotationForm(FlaskForm):
    """Form for creating and editing clip annotations"""
    title = StringField('Title', validators=[Optional()])
    timestamp = IntegerField('Timestamp (seconds)', validators=[DataRequired(), NumberRange(min=0)])
    event_type = SelectField('Event Type', 
        choices=[
            ('', 'Select Event Type'),
            ('goal', 'Goal'),
            ('assist', 'Assist'),
            ('turnover', 'Turnover'),
            ('block', 'Block'),
            ('drop', 'Drop'),
            ('throwaway', 'Throwaway'),
            ('callahan', 'Callahan'),
            ('timeout', 'Timeout'),
            ('pull', 'Pull'),
            ('other', 'Other')
        ],
        validators=[Optional()]
    )
    our_score = IntegerField('Our Score', validators=[Optional(), NumberRange(min=0)])
    their_score = IntegerField('Their Score', validators=[Optional(), NumberRange(min=0)])
    
    offense = SelectField('Offense Type',
        choices=[
            ('', 'Select...'),
            ('horo', 'Horizontal Stack'),
            ('vert', 'Vertical Stack'),
            ('flow', 'Flow/Handler Offense'),
            ('side', 'Side Stack'),
            ('split', 'Split Stack'),
            ('iso', 'Isolation'),
            ('other', 'Other')
        ],
        validators=[Optional()]
    )
    
    defense = SelectField('Defense Type',
        choices=[
            ('', 'Select...'),
            ('match_flick', 'Person - Force Forehand'),
            ('match_backhand', 'Person - Force Backhand'),
            ('match_middle', 'Person - Straight Up'),
            ('zone', 'Zone Defense'),
            ('junk', 'Junk Defense'),
            ('trap', 'Trap/Sideline'),
            ('switch', 'Switch Defense'),
            ('other', 'Other')
        ],
        validators=[Optional()]
    )
    
    notes = TextAreaField('Notes', validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    players = SelectMultipleField('Players Involved', coerce=int, validators=[Optional()])
    is_key_moment = BooleanField('Mark as Key Moment')
    visibility = SelectField('Visibility',
        choices=[
            ('team', 'Team (All Members)'),
            ('coaches', 'Coaches Only'),
            ('private', 'Private (Only Me)')
        ],
        default='team',
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Annotation')

    def __init__(self, *args, **kwargs):
        super(AnnotationForm, self).__init__(*args, **kwargs)
        # Populate annotation tag choices (hierarchical structure)
        self.tags.choices = self._get_hierarchical_tag_choices()
        # Populate player choices
        self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                               for p in Player.query.filter_by(active=True).order_by(Player.name).all()]
    
    def _get_hierarchical_tag_choices(self):
        """Build hierarchical tag choices for display"""
        choices = []
        # Get root tags (no parent)
        root_tags = AnnotationTag.query.filter_by(parent_tag_id=None, is_active=True).order_by(AnnotationTag.category, AnnotationTag.name).all()
        
        for root in root_tags:
            # Add root tag
            choices.append((root.id, root.name))
            # Add children with indentation
            self._add_child_tags(root, choices, level=1)
        
        return choices
    
    def _add_child_tags(self, parent, choices, level):
        """Recursively add child tags with indentation"""
        children = parent.children.filter_by(is_active=True).order_by(AnnotationTag.name).all()
        for child in children:
            indent = "  " * level
            choices.append((child.id, f"{indent}↳ {child.name}"))
            self._add_child_tags(child, choices, level + 1)


class QuickAnnotationForm(FlaskForm):
    """Simplified form for quick annotations during video review"""
    timestamp = IntegerField('Timestamp', validators=[DataRequired()])
    title = StringField('Quick Note', validators=[DataRequired()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    is_key_moment = BooleanField('Key Moment')
    submit = SubmitField('Add Quick Note')
    
    def __init__(self, *args, **kwargs):
        super(QuickAnnotationForm, self).__init__(*args, **kwargs)
        # Get most commonly used tags for quick access
        self.tags.choices = [
            (t.id, t.name) for t in AnnotationTag.query.filter_by(
                is_active=True
            ).order_by(AnnotationTag.name).limit(20).all()
        ]


class AnnotationFilterForm(FlaskForm):
    """Form for filtering annotations"""
    tag_id = SelectMultipleField('Filter by Tags', coerce=int, validators=[Optional()])
    player_id = SelectField('Filter by Player', coerce=int, validators=[Optional()])
    event_type = SelectField('Filter by Event', 
        choices=[
            (0, 'All Events'),
            ('goal', 'Goals'),
            ('turnover', 'Turnovers'),
            ('block', 'Blocks'),
            ('assist', 'Assists')
        ],
        validators=[Optional()]
    )
    creator_id = SelectField('Filter by Creator', coerce=int, validators=[Optional()])
    key_moments_only = BooleanField('Key Moments Only')
    submit = SubmitField('Apply Filters')
    
    def __init__(self, *args, **kwargs):
        from app.models.user import User
        super(AnnotationFilterForm, self).__init__(*args, **kwargs)
        
        # Populate tag choices
        self.tag_id.choices = [(t.id, t.name) for t in AnnotationTag.query.filter_by(is_active=True).order_by(AnnotationTag.name).all()]
        
        # Populate player choices
        self.player_id.choices = [(0, 'All Players')] + [
            (p.id, f"{p.name} (#{p.jersey_number})") 
            for p in Player.query.filter_by(active=True).order_by(Player.name).all()
        ]
        
        # Populate creator choices (users who have created annotations)
        self.creator_id.choices = [(0, 'All Users')] + [
            (u.id, u.username) for u in User.query.order_by(User.username).all()
        ]


class AnnotationTagForm(FlaskForm):
    """Form for creating and editing annotation tags"""
    name = StringField('Tag Name', validators=[DataRequired()])
    category = StringField('Category', validators=[Optional()])
    parent_tag_id = SelectField('Parent Tag (Optional)', coerce=int, validators=[Optional()])
    color = StringField('Color (Hex)', validators=[Optional()], default='#3F51B5')
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Tag')
    
    def __init__(self, *args, **kwargs):
        super(AnnotationTagForm, self).__init__(*args, **kwargs)
        # Populate parent tag choices
        self.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
            (t.id, t.full_path) for t in AnnotationTag.query.filter_by(is_active=True).order_by(AnnotationTag.name).all()
        ]
