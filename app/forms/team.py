from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Email, Optional, Length

class PlayerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email()])  # Email is optional
    jersey_number = StringField('Jersey Number', validators=[Optional()])
    position = SelectField('Position', choices=[
        ('', 'Select Position'),  # Add a placeholder
        ('handler', 'Handler'),
        ('cutter', 'Cutter'),
        ('hybrid', 'Hybrid')
    ])
    gender_match = SelectField('Gender Match', choices=[
        ('', 'Select Gender'),  # Add a placeholder
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ])
    line_preference = SelectField('Line Preference', choices=[
        ('', 'Select Line'),  # Add a placeholder
        ('O-line', 'O-line'),
        ('D-line', 'D-line'),
        ('both', 'Both')
    ])
    team = SelectField('Team', choices=[
        ('', 'Select Team'),  # Add a placeholder
        ('A', 'Team A'),  # Replace with your actual teams
        ('B', 'Team B'),
        ('C', 'Team C')
    ])
    active = BooleanField('Active', default=True)
    
    # User account fields
    create_account = BooleanField('Create User Account')
    username = StringField('Username', validators=[Optional(), Length(min=3, max=64)])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    
    submit = SubmitField('Save Player')


class PlayerFilterForm(FlaskForm):
    position = SelectField('Position', choices=[
        ('', 'All'),
        ('cutter', 'Cutter'),
        ('handler', 'Handler'),
        ('hybrid', 'Hybrid')
    ])
    line_preference = SelectField('Line', choices=[
        ('', 'All'),
        ('O-line', 'O-Line'),
        ('D-line', 'D-Line'),
        ('both', 'Both')
    ])
    gender_match = SelectField('Gender', choices=[
        ('', 'All'),
        ('male', 'Male'),
        ('female', 'Female')
    ])
    team = SelectField('Team', choices=[('', 'All')])  # Dynamically populated in route
    active_only = BooleanField('Active Only', default=True)
