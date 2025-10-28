from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, TextAreaField, SelectField, SelectMultipleField, SubmitField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Optional, URL, NumberRange, Length
from app.models.game import Game
from app.models.player import Player
from app.models.clip import ClipTag
from flask_login import current_user
from flask import session


class ClipForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    point_id = SelectField('Point', coerce=int, validators=[Optional()])
    video_source = SelectField('Video Source', 
        choices=[
            ('youtube', 'YouTube'),
            ('veo', 'Veo')
        ],
        default='youtube',
        validators=[DataRequired()]
    )
    youtube_link = StringField('Video Link', validators=[DataRequired(), URL()])
    start_time = IntegerField('Start Time (seconds)', validators=[Optional()])
    end_time = IntegerField('End Time (seconds)', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    players = SelectMultipleField('Players', coerce=int, validators=[Optional()])
    is_featured = BooleanField('Featured Clip')
    submit = SubmitField('Save Clip')

    def __init__(self, *args, **kwargs):
        super(ClipForm, self).__init__(*args, **kwargs)
        
        # Get current team ID
        if current_user.is_authenticated:
            if current_user.is_admin:
                team_id = session.get('current_team_id')
            else:
                team_id = current_user.team_organization_id
        else:
            team_id = None
        
        # Populate game choices - FILTERED BY TEAM
        if team_id:
            self.game_id.choices = [(0, 'Select Game')] + [
                (g.id, f"vs {g.opponent} ({g.date.strftime('%Y-%m-%d') if g.date else 'No date'})")
                for g in Game.query.filter_by(team_organization_id=team_id).order_by(Game.date.desc()).all()
            ]
        else:
            self.game_id.choices = [(0, 'Select Game')]
        
        # Point choices will be populated via AJAX when a game is selected
        self.point_id.choices = [(0, 'Select Point')]
        
        # Populate tag choices with hierarchical structure and categories - FILTERED BY TEAM
        if team_id:
            self.tags.choices = self._get_hierarchical_tag_choices(team_id)
        else:
            self.tags.choices = []
        
        # Populate player choices - FILTERED BY TEAM
        if team_id:
            self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                                   for p in Player.query.filter_by(
                                       team_organization_id=team_id,
                                       active=True
                                   ).order_by(Player.name).all()]
        else:
            self.players.choices = []
    
    def _get_hierarchical_tag_choices(self, team_id):
        """Build hierarchical tag choices grouped by category"""
        choices = []
        
        # Get all active tags for this team
        tags = ClipTag.query.filter_by(
            team_organization_id=team_id,
            is_active=True
        ).order_by(ClipTag.category, ClipTag.name).all()
        
        # Group by category
        categories = {}
        for tag in tags:
            category = tag.category or 'Other'
            if category not in categories:
                categories[category] = []
            categories[category].append(tag)
        
        # Build choices with category headers
        for category in sorted(categories.keys()):
            # Add category header (disabled option)
            choices.append((-1, f"─── {category} ───"))
            # Add tags in this category
            for tag in categories[category]:
                if tag.parent_tag_id is None:
                    # Root tag
                    choices.append((tag.id, tag.name))
                    # Add children with indentation
                    self._add_child_tags(tag, choices, level=1)
        
        return choices
    
    def _add_child_tags(self, parent, choices, level):
        """Recursively add child tags with indentation"""
        children = parent.children.filter_by(is_active=True).order_by(ClipTag.name).all()
        for child in children:
            indent = "  " * level
            choices.append((child.id, f"{indent}↳ {child.name}"))
            self._add_child_tags(child, choices, level + 1)


class ClipTagForm(FlaskForm):
    name = StringField('Tag Name', validators=[DataRequired(), Length(max=100)])
    category = SelectField('Category', 
        choices=[
            ('', 'Select Category'),
            ('Video Type', 'Video Type'),
            ('Game Context', 'Game Context'),
            ('Training Type', 'Training Type'),
            ('Skill Focus', 'Skill Focus'),
            ('Strategic Focus', 'Strategic Focus'),
            ('Player Development', 'Player Development'),
            ('Analysis', 'Analysis')
        ],
        validators=[Optional()]
    )
    parent_tag_id = SelectField('Parent Tag (Optional)', coerce=int, validators=[Optional()])
    color = StringField('Color (Hex)', validators=[Optional(), Length(max=7)], default='#3F51B5')
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Tag')

    def __init__(self, *args, **kwargs):
        super(ClipTagForm, self).__init__(*args, **kwargs)
        
        # Get current team ID
        if current_user.is_authenticated:
            if current_user.is_admin:
                team_id = session.get('current_team_id')
            else:
                team_id = current_user.team_organization_id
        else:
            team_id = None
        
        # Populate parent tag choices - FILTERED BY TEAM
        if team_id:
            self.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
                (t.id, t.full_path) for t in ClipTag.query.filter_by(
                    team_organization_id=team_id,
                    is_active=True
                ).order_by(ClipTag.category, ClipTag.name).all()
            ]
        else:
            self.parent_tag_id.choices = [(0, 'None (Root Tag)')]


class ClipFilterForm(FlaskForm):
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    tag_category = SelectField('Tag Category', 
        choices=[
            ('', 'All Categories'),
            ('Video Type', 'Video Type'),
            ('Game Context', 'Game Context'),
            ('Training Type', 'Training Type'),
            ('Skill Focus', 'Skill Focus'),
            ('Strategic Focus', 'Strategic Focus'),
            ('Player Development', 'Player Development'),
            ('Analysis', 'Analysis')
        ],
        validators=[Optional()]
    )
    player_id = SelectField('Player', coerce=int, validators=[Optional()])
    video_source = SelectField('Video Source',
        choices=[
            ('', 'All Sources'),
            ('youtube', 'YouTube'),
            ('veo', 'Veo')
        ],
        validators=[Optional()]
    )
    is_featured = SelectField('Featured Only',
        choices=[
            ('', 'All Clips'),
            ('1', 'Featured Only')
        ],
        validators=[Optional()]
    )
    sort_by = SelectField('Sort By',
        choices=[
            ('created_desc', 'Newest First'),
            ('created_asc', 'Oldest First'),
            ('title_asc', 'Title (A-Z)'),
            ('views_desc', 'Most Viewed'),
            ('annotations_desc', 'Most Annotated')
        ],
        default='created_desc',
        validators=[Optional()]
    )
    submit = SubmitField('Filter')

    def __init__(self, *args, **kwargs):
        super(ClipFilterForm, self).__init__(*args, **kwargs)
        
        # Get current team ID
        if current_user.is_authenticated:
            if current_user.is_admin:
                team_id = session.get('current_team_id')
            else:
                team_id = current_user.team_organization_id
        else:
            team_id = None
        
        # Populate game choices - FILTERED BY TEAM
        if team_id:
            self.game_id.choices = [(0, 'All Games')] + [
                (g.id, f"vs {g.opponent} ({g.date.strftime('%Y-%m-%d') if g.date else 'No date'})")
                for g in Game.query.filter_by(team_organization_id=team_id).order_by(Game.date.desc()).all()
            ]
        else:
            self.game_id.choices = [(0, 'All Games')]
        
        # Populate tag choices with hierarchical structure - FILTERED BY TEAM
        if team_id:
            self.tags.choices = self._get_hierarchical_tag_choices(team_id)
        else:
            self.tags.choices = []
        
        # Populate player choices - FILTERED BY TEAM
        if team_id:
            self.player_id.choices = [(0, 'All Players')] + [(p.id, f"{p.name} (#{p.jersey_number})") 
                                    for p in Player.query.filter_by(
                                        team_organization_id=team_id,
                                        active=True
                                    ).order_by(Player.name).all()]
        else:
            self.player_id.choices = [(0, 'All Players')]
    
    def _get_hierarchical_tag_choices(self, team_id):
        """Build hierarchical tag choices grouped by category"""
        choices = []
        
        # Get all active tags for this team
        tags = ClipTag.query.filter_by(
            team_organization_id=team_id,
            is_active=True
        ).order_by(ClipTag.category, ClipTag.name).all()
        
        # Group by category
        categories = {}
        for tag in tags:
            category = tag.category or 'Other'
            if category not in categories:
                categories[category] = []
            categories[category].append(tag)
        
        # Build choices with category headers
        for category in sorted(categories.keys()):
            # Add tags in this category
            for tag in categories[category]:
                if tag.parent_tag_id is None:
                    # Show category prefix
                    choices.append((tag.id, f"[{category}] {tag.name}"))
                    # Add children with indentation
                    self._add_child_tags(tag, choices, level=1, category=category)
        
        return choices
    
    def _add_child_tags(self, parent, choices, level, category):
        """Recursively add child tags with indentation"""
        children = parent.children.filter_by(is_active=True).order_by(ClipTag.name).all()
        for child in children:
            indent = "  " * level
            choices.append((child.id, f"[{category}] {indent}↳ {child.name}"))
            self._add_child_tags(child, choices, level + 1, category)