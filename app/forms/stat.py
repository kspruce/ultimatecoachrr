from flask_wtf import FlaskForm
from wtforms import SelectField, FloatField, TextAreaField, HiddenField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange


class EventForm(FlaskForm):
    point_id = HiddenField('Point ID')
    event_type = SelectField('Event Type', choices=[
        ('catch', 'Catch'),
        ('throw', 'Throw'),
        ('assist', 'Assist'),
        ('hockey_assist', 'Hockey Assist'),
        ('throwaway', 'Throwaway'),
        ('drop', 'Drop'),
        ('goal', 'Goal'),
        ('block', 'Block'),
        ('stall', 'Stall'),
        ('callahan', 'Callahan')
    ], validators=[DataRequired()])
    player_id = SelectField('Player', coerce=int, validators=[DataRequired()])
    field_position_x = FloatField('X Position (meters)', validators=[Optional()])
    field_position_y = FloatField('Y Position (meters)', validators=[Optional()])
    throw_type = SelectField('Throw Type', choices=[
        ('', 'Select Throw Type'),
        ('backhand', 'Backhand'),
        ('forehand', 'Forehand'),
        ('hammer', 'Hammer'),
        ('scoober', 'Scoober'),
        ('blade', 'Blade'),
        ('push_pass', 'Push Pass'),
        ('other', 'Other')
    ], validators=[Optional()])
    force_direction = SelectField('Force Direction', choices=[
        ('', 'Select Force'),
        ('forehand', 'Forehand'),
        ('backhand', 'Backhand'),
        ('no_force', 'No Force')
    ], validators=[Optional()])
    receiver_id = SelectField('Receiver', coerce=int, validators=[Optional()])
    timestamp = IntegerField('Timestamp (seconds)', validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Record Event')

    def __init__(self, point=None, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        if point:
            # Only show players who were on this point
            player_choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                             for p in point.players]
            self.player_id.choices = player_choices
            self.receiver_id.choices = [(0, 'None')] + player_choices
