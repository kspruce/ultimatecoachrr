from flask_wtf import FlaskForm
from wtforms import (
    StringField, DateField, TimeField, TextAreaField, SelectField, 
    IntegerField, BooleanField, SelectMultipleField, SubmitField, 
    URLField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length, URL
from app.models.player import Player
from app import db
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename
import os

class SessionPlanForm(FlaskForm):
    title = StringField('Session Title', validators=[DataRequired(), Length(max=100)])
    date = DateField('Date', format='%Y-%m-%d', validators=[Optional()])
    start_time = TimeField('Start Time', format='%H:%M', validators=[Optional()])
    end_time = TimeField('End Time', format='%H:%M', validators=[Optional()])
    location = StringField('Location', validators=[Optional(), Length(max=100)])
    focus_area = StringField('Focus Area', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional()])
    is_recurring = BooleanField('Recurring Session', default=False)
    recurrence_pattern = SelectField('Recurrence Pattern', choices=[
        ('', 'Select...'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-weekly'),
        ('monthly', 'Monthly')
    ], validators=[Optional()])
    # Add session type field with choices
    session_type = SelectField(
        'Session Type',
        choices=[
            ('invited_training', 'Invited Training'),
            ('open_training', 'Open Training'),
            ('pod_training', 'Pod Training')
        ],
        default='invited_training',
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Session Plan')

class DrillForm(FlaskForm):
    title = StringField('Title', validators=[
        DataRequired(), 
        Length(max=100)
    ])
    description = TextAreaField('Description')
    setup_instructions = TextAreaField('Setup Instructions')
    recommended_duration = IntegerField('Recommended Duration (minutes)', 
        validators=[Optional(), NumberRange(min=1, max=120)]
    )
    min_players = IntegerField('Minimum Players',
        validators=[Optional(), NumberRange(min=1)]
    )
    max_players = IntegerField('Maximum Players',
        validators=[Optional(), NumberRange(min=1)]
    )
    skill_level = SelectField('Skill Level',
        choices=[
            ('', 'Any Level'),
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced')
        ],
        validators=[Optional()]
    )
    focus_area = StringField('Focus Area')
    equipment_needed = StringField('Equipment Needed')
    ultiplay_embed = TextAreaField('Ultiplay Embed Code')
    is_public = BooleanField('Make this drill public')

    def __init__(self, *args, **kwargs):
        super(DrillForm, self).__init__(*args, **kwargs)
        # Remove the has_visual_diagram initialization
        # It's no longer needed since we're using embed codes

class SessionComponentForm(FlaskForm):
    title = StringField('Component Title', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    duration_minutes = IntegerField('Duration (minutes)', 
                                  validators=[Optional(), NumberRange(min=1)])
    order = IntegerField('Order', validators=[DataRequired(), NumberRange(min=1)])
    component_type = SelectField('Component Type', choices=[
        ('warmup', 'Warm-up'),
        ('drill', 'Drill'),
        ('scrimmage', 'Scrimmage'),
        ('cooldown', 'Cool-down'),
        ('discussion', 'Discussion'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    focus_area = StringField('Focus Area', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional()])
    drill_id = SelectField('Use Saved Drill', coerce=int, validators=[Optional()])
    plays = SelectMultipleField('Plays Used', coerce=int)
    
    def __init__(self, *args, **kwargs):
        super(SessionComponentForm, self).__init__(*args, **kwargs)
        from app.models.playbook import Play
        self.plays.choices = [(p.id, p.name) for p in Play.query.order_by(Play.name).all()]    
    submit = SubmitField('Save Component')

class AttendanceForm(FlaskForm):
    players = SelectMultipleField('Players', coerce=int, validators=[])
    status = SelectField('Status', choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Attendance')
    
    def __init__(self, team_organization_id=None, *args, **kwargs):
        super(AttendanceForm, self).__init__(*args, **kwargs)
        if team_organization_id:
            self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                                   for p in Player.query.filter_by(
                                       active=True, 
                                       team_organization_id=team_organization_id
                                   ).order_by(Player.name).all()]
        else:
            self.players.choices = []

class SessionFilterForm(FlaskForm):
    focus_area = SelectField('Focus Area', validators=[Optional()])
    date_range = SelectField('Date Range', choices=[
        ('all', 'All Time'),
        ('past_week', 'Past Week'),
        ('past_month', 'Past Month'),
        ('past_year', 'Past Year')
    ], validators=[Optional()])
    submit = SubmitField('Filter')
    # Add session type filter field
    session_type = SelectField(
        'Session Type',
        choices=[
            ('', 'All Types'),
            ('invited_training', 'Invited Training'),
            ('open_training', 'Open Training'),
            ('pod_training', 'Pod Training')
        ],
        default='',
        validators=[]
    )
    
    def __init__(self, *args, **kwargs):
        super(SessionFilterForm, self).__init__(*args, **kwargs)
        # Populate focus area choices dynamically
        from app.models.session import SessionPlan
        focus_areas = db.session.query(SessionPlan.focus_area).distinct().all()
        self.focus_area.choices = [('', 'All Focus Areas')] + \
                                [(fa[0], fa[0]) for fa in focus_areas if fa[0]]

class SessionRSVPForm(FlaskForm):
    status = SelectField('Attendance Status', choices=[
        ('attending', 'I will attend'),
        ('not_attending', 'I cannot attend'),
        ('maybe', 'I might attend')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Submit RSVP')

class AdminSessionRSVPForm(FlaskForm):
    player_id = SelectField('Player', coerce=int, validators=[DataRequired()])
    status = SelectField('Attendance Status', choices=[
        ('attending', 'Will attend'),
        ('not_attending', 'Cannot attend'),
        ('maybe', 'Might attend')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Submit RSVP')
    
    def __init__(self, team_organization_id=None, *args, **kwargs):
        super(AdminSessionRSVPForm, self).__init__(*args, **kwargs)
        if team_organization_id:
            self.player_id.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                                     for p in Player.query.filter_by(
                                         active=True,
                                         team_organization_id=team_organization_id
                                     ).order_by(Player.name).all()]
        else:
            self.player_id.choices = []

class DrillSearchForm(FlaskForm):
    """Form for searching drills"""
    query = StringField('Search', validators=[Optional()])
    skill_level = SelectField('Skill Level', choices=[
        ('', 'Any Level'),
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('all', 'All Levels')
    ], validators=[Optional()])
    focus_area = StringField('Focus Area', validators=[Optional()])
    submit = SubmitField('Search')

class AdminBulkRSVPForm(FlaskForm):
    players = SelectMultipleField('Players', coerce=int, validators=[DataRequired()])
    status = SelectField('RSVP Status', choices=[
        ('attending', 'Attending'),
        ('not_attending', 'Not Attending'),
        ('maybe', 'Maybe')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save RSVPs')
    
    def __init__(self, team_organization_id=None, *args, **kwargs):
        super(AdminBulkRSVPForm, self).__init__(*args, **kwargs)
        if team_organization_id:
            self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                                   for p in Player.query.filter_by(
                                       active=True,
                                       team_organization_id=team_organization_id
                                   ).order_by(Player.name).all()]
        else:
            self.players.choices = []