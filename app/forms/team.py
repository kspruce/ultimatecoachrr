from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Optional

class PlayerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    jersey_number = StringField('Jersey Number')
    position = SelectField('Position', choices=[
        ('', 'Select...'),
        ('handler', 'Handler'),
        ('cutter', 'Cutter'),
        ('hybrid', 'Hybrid')
    ])
    height = StringField('Height')
    weight = StringField('Weight')
    # Remove the gender field
    gender_match = SelectField('Gender Match', choices=[
        ('', 'Select...'),
        ('male', 'Male'),
        ('female', 'Female'),
        ('both', 'Both')
    ])
    team = SelectField('Team', choices=[
        ('', 'Select...'),
        ('team1', 'Team 1'),
        ('team2', 'Team 2')
    ])
    birth_date = DateField('Birth Date', format='%Y-%m-%d', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    phone = StringField('Phone')
    line_preference = SelectField('Line Preference', choices=[
        ('', 'Select...'),
        ('o-line', 'O-line'),
        ('d-line', 'D-line'),
        ('both', 'Both')
    ])
    active = BooleanField('Active', default=True)
    notes = TextAreaField('Notes')
    submit = SubmitField('Save Player')

class PlayerFilterForm(FlaskForm):
    position = SelectField('Position', choices=[
        ('', 'All Positions'),
        ('handler', 'Handler'),
        ('cutter', 'Cutter'),
        ('hybrid', 'Hybrid')
    ], validators=[Optional()])
    line_preference = SelectField('Line Preference', choices=[
        ('', 'All Lines'),
        ('o-line', 'O-line'),
        ('d-line', 'D-line'),
        ('both', 'Both')
    ], validators=[Optional()])
    gender_match = SelectField('Gender Match', choices=[
        ('', 'All'),
        ('male', 'Male'),
        ('female', 'Female'),
        ('both', 'Both')
    ], validators=[Optional()])
    # Add this field
    team = SelectField('Team', choices=[
        ('', 'All Teams'),
        ('team1', 'Team 1'),
        ('team2', 'Team 2')
        # Add more teams as needed
    ], validators=[Optional()])
    active_only = BooleanField('Active Players Only', default=True)
    submit = SubmitField('Filter')

