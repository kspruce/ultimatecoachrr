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
    submit = SubmitField('Save Session Plan')

class DrillForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description')
    setup_instructions = TextAreaField('Setup Instructions')
    recommended_duration = IntegerField('Recommended Duration (minutes)')
    min_players = IntegerField('Minimum Players')
    max_players = IntegerField('Maximum Players')
    skill_level = SelectField('Skill Level', choices=[
        ('', 'Any Level'),
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced')
    ])
    focus_area = StringField('Focus Area')
    equipment_needed = StringField('Equipment Needed')
    # Remove diagram_file and diagram_url fields
    ultiplay_embed = TextAreaField('Ultiplay Embed Code')  # Add this field
    is_public = BooleanField('Make this drill public')

    def __init__(self, *args, **kwargs):
        drill_type = kwargs.pop('drill_type', 'basic') if 'drill_type' in kwargs else 'basic'
        super(DrillForm, self).__init__(*args, **kwargs)
        self.has_visual_diagram.data = (drill_type == 'visual')
        
        # Hide diagram_url field for visual drills
        if drill_type == 'visual':
            del self.diagram_url

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
    submit = SubmitField('Save Component')

class AttendanceForm(FlaskForm):
    players = SelectMultipleField('Players', coerce=int, validators=[DataRequired()])
    status = SelectField('Status', choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused')
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Attendance')
    
    def __init__(self, *args, **kwargs):
        super(AttendanceForm, self).__init__(*args, **kwargs)
        self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                               for p in Player.query.filter_by(active=True).order_by(Player.name).all()]

class SessionFilterForm(FlaskForm):
    focus_area = SelectField('Focus Area', validators=[Optional()])
    date_range = SelectField('Date Range', choices=[
        ('all', 'All Time'),
        ('past_week', 'Past Week'),
        ('past_month', 'Past Month'),
        ('past_year', 'Past Year')
    ], validators=[Optional()])
    submit = SubmitField('Filter')
    
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
