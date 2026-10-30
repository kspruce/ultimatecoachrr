from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, RadioField, SelectField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.forms.theory import IMAGE_URL
from app.models.playbook import PLAY_STATUSES, PLAY_TYPES, SITUATIONS


def image_url(form, field):
    value = (field.data or '').strip()
    if value and not (IMAGE_URL.match(value) or value.startswith('/playbook/image/') and value[16:].isdigit()):
        raise ValidationError('Choose a photo, or paste a link that starts with https://')


class PlayForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    type = RadioField('Side', choices=PLAY_TYPES, validators=[DataRequired()])
    status = RadioField('Status', choices=PLAY_STATUSES, validators=[DataRequired()])
    call = StringField('Call', validators=[Optional(), Length(max=60)],
                       description="What's called on the line, e.g. \"Hammer\"")
    signal = StringField('Hand signal', validators=[Optional(), Length(max=100)])
    description = TextAreaField('How it works', validators=[Optional()])
    notes = TextAreaField('Coaching notes', validators=[Optional()])
    image_url = StringField('Photo', validators=[Optional(), Length(max=500), image_url])
    ultiplay_embed = TextAreaField('Ultiplay embed code', validators=[Optional()])
    tags = StringField('Tags', validators=[Optional(), Length(max=300)])
    is_core = BooleanField('Core play: everyone must know it')
    situations = SelectMultipleField('When it\'s for', choices=SITUATIONS, validators=[Optional()])
    # Ids that aren't the team's are dropped by the route
    topics = SelectMultipleField('Theory', coerce=int, validators=[Optional()], validate_choice=False)
    drills = SelectMultipleField('Drills', coerce=int, validators=[Optional()], validate_choice=False)
    clips = SelectMultipleField('Clips', coerce=int, validators=[Optional()], validate_choice=False)


class LearnForm(FlaskForm):
    tournament_id = SelectField('Before a tournament', coerce=int, validators=[Optional()])
    due_date = DateField('Learn by', validators=[Optional()])
    note = StringField('Note for the team', validators=[Optional(), Length(max=200)])
