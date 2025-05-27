from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Optional, URL, NumberRange, Length
from app.models.tournament import Tournament
from app.models.game import Game

class ScoutingReportForm(FlaskForm):
    team_name = StringField('Team Name', validators=[DataRequired(), Length(max=100)])
    date = DateField('Date', format='%Y-%m-%d', validators=[Optional()])
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    offense_strategy = TextAreaField('Offensive Strategy', validators=[Optional()])
    defense_strategy = TextAreaField('Defensive Strategy', validators=[Optional()])
    strengths = TextAreaField('Strengths', validators=[Optional()])
    weaknesses = TextAreaField('Weaknesses', validators=[Optional()])
    notes = TextAreaField('Additional Notes', validators=[Optional()])
    submit = SubmitField('Save Scouting Report')
    
    def __init__(self, *args, **kwargs):
        super(ScoutingReportForm, self).__init__(*args, **kwargs)
        # Populate tournament choices
        self.tournament_id.choices = [(0, 'None')] + [
            (t.id, t.name) for t in Tournament.query.order_by(Tournament.start_date.desc()).all()
        ]
        # Populate game choices
        self.game_id.choices = [(0, 'None')] + [
            (g.id, f"vs {g.opponent} ({g.date.strftime('%Y-%m-%d') if g.date else 'No date'})") 
            for g in Game.query.order_by(Game.date.desc()).all()
        ]

class OpponentPlayerForm(FlaskForm):
    name = StringField('Player Name', validators=[DataRequired(), Length(max=100)])
    jersey_number = StringField('Jersey Number', validators=[Optional(), Length(max=10)])
    position = SelectField('Position', choices=[
        ('', 'Select...'),
        ('handler', 'Handler'),
        ('cutter', 'Cutter'),
        ('hybrid', 'Hybrid')
    ], validators=[Optional()])
    height = StringField('Height', validators=[Optional(), Length(max=20)])
    gender = SelectField('Gender', choices=[
        ('', 'Select...'),
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], validators=[Optional()])
    throwing_ability = SelectField('Throwing Ability', choices=[
        ('', 'Select...'),
        ('1', '1 - Poor'),
        ('2', '2 - Below Average'),
        ('3', '3 - Average'),
        ('4', '4 - Good'),
        ('5', '5 - Excellent')
    ], validators=[Optional()], coerce=lambda x: int(x) if x else None)
    cutting_ability = SelectField('Cutting Ability', choices=[
        ('', 'Select...'),
        ('1', '1 - Poor'),
        ('2', '2 - Below Average'),
        ('3', '3 - Average'),
        ('4', '4 - Good'),
        ('5', '5 - Excellent')
    ], validators=[Optional()], coerce=lambda x: int(x) if x else None)
    defensive_ability = SelectField('Defensive Ability', choices=[
        ('', 'Select...'),
        ('1', '1 - Poor'),
        ('2', '2 - Below Average'),
        ('3', '3 - Average'),
        ('4', '4 - Good'),
        ('5', '5 - Excellent')
    ], validators=[Optional()], coerce=lambda x: int(x) if x else None)
    athletic_ability = SelectField('Athletic Ability', choices=[
        ('', 'Select...'),
        ('1', '1 - Poor'),
        ('2', '2 - Below Average'),
        ('3', '3 - Average'),
        ('4', '4 - Good'),
        ('5', '5 - Excellent')
    ], validators=[Optional()], coerce=lambda x: int(x) if x else None)
    preferred_throws = StringField('Preferred Throws', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Player')


class ScoutingClipForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=100)])
    youtube_link = StringField('YouTube Link', validators=[DataRequired(), URL()])
    start_time = IntegerField('Start Time (seconds)', validators=[Optional(), NumberRange(min=0)])
    end_time = IntegerField('End Time (seconds)', validators=[Optional(), NumberRange(min=0)])
    clip_type = SelectField('Clip Type', choices=[
        ('', 'Select...'),
        ('offense', 'Offense'),
        ('defense', 'Defense'),
        ('set_play', 'Set Play'),
        ('pull', 'Pull'),
        ('other', 'Other')
    ], validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save Clip')

class ScoutingFilterForm(FlaskForm):
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    submit = SubmitField('Filter')
    
    def __init__(self, *args, **kwargs):
        super(ScoutingFilterForm, self).__init__(*args, **kwargs)
        # Populate tournament choices
        self.tournament_id.choices = [(0, 'All Tournaments')] + [
            (t.id, t.name) for t in Tournament.query.order_by(Tournament.start_date.desc()).all()
        ]
