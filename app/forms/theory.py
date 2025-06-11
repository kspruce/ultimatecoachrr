# app/forms/theory.py
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, IntegerField, SelectField, 
    URLField, SelectMultipleField, BooleanField
)
from wtforms.validators import DataRequired, Optional, Length, URL, ValidationError
from flask_wtf.file import FileField, FileAllowed

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
    image = FileField('Topic Image', 
                     validators=[
                         Optional(),
                         FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
                     ])
    related_drills = SelectMultipleField('Related Drills', coerce=int, validators=[Optional()])
    
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
        tag = TheoryTag.query.filter_by(name=field.data).first()
        if tag:
            raise ValidationError('This tag already exists.')

class TheorySearchForm(FlaskForm):
    query = StringField('Search', validators=[Optional()])
    section = SelectField('Section', coerce=int, validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
