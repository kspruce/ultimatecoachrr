from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, TextAreaField, SelectField, SelectMultipleField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Optional, URL, NumberRange
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
        
        # Populate tag choices - FILTERED BY TEAM
        if team_id:
            self.tags.choices = [(t.id, t.name) for t in ClipTag.query.filter_by(
                team_organization_id=team_id
            ).order_by(ClipTag.name).all()]
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


class ClipTagForm(FlaskForm):
    name = StringField('Tag Name', validators=[DataRequired()])
    submit = SubmitField('Save Tag')


class ClipFilterForm(FlaskForm):
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    tag_id = SelectField('Tag', coerce=int, validators=[Optional()])
    player_id = SelectField('Player', coerce=int, validators=[Optional()])
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
        
        # Populate tag choices - FILTERED BY TEAM
        if team_id:
            self.tag_id.choices = [(0, 'All Tags')] + [(t.id, t.name) for t in ClipTag.query.filter_by(
                team_organization_id=team_id
            ).order_by(ClipTag.name).all()]
        else:
            self.tag_id.choices = [(0, 'All Tags')]
        
        # Populate player choices - FILTERED BY TEAM
        if team_id:
            self.player_id.choices = [(0, 'All Players')] + [(p.id, f"{p.name} (#{p.jersey_number})") 
                                    for p in Player.query.filter_by(
                                        team_organization_id=team_id,
                                        active=True
                                    ).order_by(Player.name).all()]
        else:
            self.player_id.choices = [(0, 'All Players')]