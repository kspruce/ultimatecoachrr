from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange, Regexp

class AnnotationForm(FlaskForm):
    timestamp = StringField('Timestamp', 
        validators=[
            DataRequired(),
            Regexp(r'^(?:(?:[0-9]{1,2}:)?[0-5]?[0-9]:)?[0-5]?[0-9]$', 
                message='Invalid timestamp format. Use HH:MM:SS, MM:SS, or SS')
        ])
    event_type = SelectField('Event Type', choices=[
        ('point_start', 'Point Start'),
        ('point_end', 'Point End'),
        ('drill_start', 'Drill Start'),
        ('drill_end', 'Drill End'),
        ('turnover', 'Turnover'),
        ('score', 'Score'),
        ('timeout', 'Timeout'),
        ('injury', 'Injury'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    our_score = IntegerField('Our Score', validators=[Optional(), NumberRange(min=0)])
    their_score = IntegerField('Their Score', validators=[Optional(), NumberRange(min=0)])
    offense = SelectField('Offense', choices=[
        ('', 'Select...'),
        ('horo', 'Horizontal'),
        ('vert', 'Vertical'),
        ('flow', 'Flow')
    ], validators=[Optional()])
    defense = SelectField('Defense', choices=[
        ('', 'Select...'),
        ('match_flick', 'Match Flick'),
        ('match_backhand', 'Match Backhand'),
        ('match_middle', 'Match Middle'),
        ('zone', 'Zone')
    ], validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Annotation')
