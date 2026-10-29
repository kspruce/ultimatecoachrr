# app/forms/theory.py
import re

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

# A web address, or a photo uploaded here (/theory/image/<id>)
IMAGE_URL = re.compile(r'^(https?://\S+|/theory/image/\d+)$')


def image_url(form, field):
    if field.data and not IMAGE_URL.match(field.data.strip()):
        raise ValidationError('Choose a photo, or paste a link that starts with https://')


class TheorySectionForm(FlaskForm):
    name = StringField('Section name',
                       validators=[DataRequired(), Length(max=100)],
                       description="e.g. Defence, Throwing, Offence")

    description = TextAreaField('Description',
                                validators=[Optional(), Length(max=1000)],
                                description="One or two lines on what this section covers")


class TheoryTopicForm(FlaskForm):
    name = StringField('Title', validators=[DataRequired(), Length(max=100)])
    section_id = SelectField('Section', coerce=int, validators=[DataRequired()])
    # Required to publish, not to save a draft (checked in the route)
    content = TextAreaField('Content', validators=[Optional()])
    image_url = StringField('Cover photo', validators=[Optional(), Length(max=500), image_url])
    tags = StringField('Tags', validators=[Optional(), Length(max=500)],
                       description='Separate tags with commas')
    related_drills = SelectMultipleField('Linked drills', coerce=int, validators=[Optional()],
                                         validate_choice=False)
    clips = SelectMultipleField('Linked clips', coerce=int, validators=[Optional()], validate_choice=False)


class TheoryAssignmentForm(FlaskForm):
    due_date = DateField('Read by', validators=[Optional()])
    note = StringField('Note for the team', validators=[Optional(), Length(max=200)])
