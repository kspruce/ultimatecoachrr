# app/forms/playbook.py
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, FileField, SelectMultipleField
from wtforms.validators import DataRequired, Optional, Length
from flask_wtf.file import FileAllowed

class PlayForm(FlaskForm):
    name = StringField('Play Name', validators=[DataRequired(), Length(max=100)])
    type = SelectField('Play Type', choices=[
        ('offense', 'Offense'),
        ('defense', 'Defense')
    ], validators=[DataRequired()])
    formation_id = SelectField('Formation', coerce=int, validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    # Replace diagram_file with ultiplay_embed
    ultiplay_embed = TextAreaField('Ultiplay Embed Code', validators=[Optional()])

class FormationForm(FlaskForm):
    name = StringField('Formation Name', validators=[DataRequired(), Length(max=100)])
    type = SelectField('Formation Type', choices=[
        ('offense', 'Offense'),
        ('defense', 'Defense')
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    # Replace diagram_file with ultiplay_embed
    ultiplay_embed = TextAreaField('Ultiplay Embed Code', validators=[Optional()])
