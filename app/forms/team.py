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
    # The club's squads (filled in by the route); saved on this season's roster
    squad_id = SelectField('Squad', choices=[('', 'No squad')], validate_choice=False)
    active = BooleanField('On the current season roster', default=True)
    
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
    active_only = BooleanField("Hide players who've left", default=True)
