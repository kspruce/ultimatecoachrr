from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SelectMultipleField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Optional
from app.models.player import Player

class PointForm(FlaskForm):
    game_id = HiddenField('Game ID')
    point_number = IntegerField('Point Number', validators=[DataRequired(), NumberRange(min=1)])
    our_line_type = SelectField('Line Type', choices=[
        ('O-line', 'Offense Line'),
        ('D-line', 'Defense Line')
    ], validators=[DataRequired()])
    our_score_before = IntegerField('Our Score Before', validators=[Optional(), NumberRange(min=0)])  # Changed validators
    their_score_before = IntegerField('Their Score Before', validators=[Optional(), NumberRange(min=0)]) # Changed validators
    starting_position = SelectField('Starting Position', choices=[
        ('offense', 'Offense'),
        ('defense', 'Defense')
    ], validators=[DataRequired()])
    point_outcome = SelectField('Point Outcome', choices=[
        ('scored', 'We Scored'),
        ('conceded', 'They Scored')
    ], validators=[DataRequired()])
    duration = IntegerField('Duration (seconds)', validators=[Optional(), NumberRange(min=0)])
    timestamp_in_video = IntegerField('Timestamp in Video (seconds)', validators=[Optional(), NumberRange(min=0)])
    players = SelectMultipleField('Players on Line', coerce=int, validators=[Optional()])
    gender_ratio = SelectField('Gender Ratio', choices=[
        ('4-3', '4 MMP - 3 FMP'),
        ('3-4', '3 MMP - 4 FMP')
    ], validators=[DataRequired()])
    force_direction = SelectField('Force Direction', choices=[
        ('forehand', 'Forehand'),
        ('backhand', 'Backhand'),
        ('middle', 'Middle'),
        ('zone', 'Zone'),
        ('unknown', 'Unknown')
    ], validators=[DataRequired()])
    submit = SubmitField('Save Point')

    def __init__(self, *args, **kwargs):
        super(PointForm, self).__init__(*args, **kwargs)
        # Populate player choices
        self.players.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                               for p in Player.query.filter_by(active=True).order_by(Player.jersey_number).all()]

class PullForm(FlaskForm):
    point_id = HiddenField('Point ID')
    player_id = SelectField('Puller', coerce=int, validators=[DataRequired()])
    is_inbounds = SelectField('Pull Result', choices=[
        (True, 'In Bounds'),
        (False, 'Out of Bounds')
    ], coerce=lambda x: x == 'True', validators=[DataRequired()])
    submit = SubmitField('Record Pull')

    def __init__(self, point=None, *args, **kwargs):
        super(PullForm, self).__init__(*args, **kwargs)
        if point:
            # Only show players who were on this point
            self.player_id.choices = [(p.id, f"{p.name} (#{p.jersey_number})") 
                                     for p in point.players]
