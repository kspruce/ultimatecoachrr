# app/forms/theory.py
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, IntegerField, SelectField, 
    URLField, SelectMultipleField
)
from wtforms.validators import DataRequired, Optional, Length, URL, ValidationError

class TheorySectionForm(FlaskForm):
    name = StringField('Section Name', 
                      validators=[DataRequired(), Length(max=100)],
                      description="Name of the theory section (e.g., Defense, Throwing)")
    
    description = TextAreaField('Description', 
                              validators=[Optional()],
                              description="Brief overview of what this section covers")
    
    order = IntegerField('Display Order', 
                        validators=[Optional()],
                        description="Order in which this section appears (lower numbers first)")

class TheoryTopicForm(FlaskForm):
    name = StringField('Topic Name', validators=[DataRequired(), Length(max=100)])
    content = TextAreaField('Content', validators=[DataRequired()])
    section_id = SelectField('Section', coerce=int, validators=[DataRequired()])
    order = IntegerField('Display Order', validators=[Optional()])
    image_url = StringField('Image URL (Imgur)', validators=[
        Optional(),
        URL(message="Please enter a valid URL")
    ])
    related_drills = SelectMultipleField('Drills that practise it', coerce=int, validate_choice=False,
                                         validators=[Optional()])
    clips = SelectMultipleField('Clips that show it', coerce=int, validate_choice=False, validators=[Optional()])
    
    tags = SelectMultipleField('Tags',
                              coerce=int,
                              validators=[Optional()],
                              render_kw={"class": "select2-multiple"})  # Add this class

class TheoryVideoForm(FlaskForm):
    title = StringField('Video Title', 
                       validators=[DataRequired(), Length(max=200)],
                       description="Title of the video")
    
    url = URLField('Video URL', 
                   validators=[DataRequired(), URL()],
                   description="YouTube or Vimeo URL")
    
    description = TextAreaField('Description', 
                              validators=[Optional()],
                              description="Brief description of the video content")
    
    order = IntegerField('Display Order', 
                        validators=[Optional()],
                        description="Order in which this video appears")

class TheoryTagForm(FlaskForm):
    name = StringField('Tag Name', 
                      validators=[DataRequired(), Length(max=50)],
                      description="Name of the tag")

    def validate_name(self, field):
        from app.models.theory import TheoryTag
        from app.utils.team_filter import get_current_team_id
        tag = TheoryTag.query.filter_by(name=field.data, team_organization_id=get_current_team_id()).first()
        if tag:
            raise ValidationError('This tag already exists.')

class TheorySearchForm(FlaskForm):
    query = StringField('Search', validators=[Optional()])
    section = SelectField('Section', coerce=int, validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
