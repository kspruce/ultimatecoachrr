from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DateField, TextAreaField, SelectField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Optional, NumberRange, URL
from app.models.tournament import Tournament
from app.models.player import Player


class GameForm(FlaskForm):
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    opponent = StringField('Opponent', validators=[DataRequired()])
    our_score = IntegerField('Our Score', validators=[Optional(), NumberRange(min=0)], default=0)
    their_score = IntegerField('Their Score', validators=[Optional(), NumberRange(min=0)], default=0)
    date = DateField('Date', format='%Y-%m-%d', validators=[Optional()])
    youtube_link = StringField('YouTube Link', validators=[Optional(), URL()])
    notes = TextAreaField('Notes', validators=[Optional()])
    players_present = SelectMultipleField('Players Present', coerce=int, validators=[Optional()])
    submit = SubmitField('Submit')

    def __init__(self, *args, **kwargs):
        super(GameForm, self).__init__(*args, **kwargs)
        # Populate tournament choices
        self.tournament_id.choices = [(0, 'No Tournament')] + [
            (t.id, t.name) for t in Tournament.query.order_by(Tournament.start_date.desc()).all()
        ]
        # Populate players_present choices
        self.players_present.choices = [(p.id, f"{p.name} (#{p.jersey_number})") for p in Player.query.filter_by(active=True).all()]

class GameFilterForm(FlaskForm):
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    opponent = StringField('Opponent', validators=[Optional()])
    result = SelectField('Result', choices=[
        ('', 'All'),
        ('win', 'Wins'),
        ('loss', 'Losses'),
        ('tie', 'Ties')
    ], validators=[Optional()])
    submit = SubmitField('Filter')

    def __init__(self, *args, **kwargs):
        super(GameFilterForm, self).__init__(*args, **kwargs)
        # Populate tournament choices
        self.tournament_id.choices = [(0, 'All Tournaments')] + [
            (t.id, t.name) for t in Tournament.query.order_by(Tournament.start_date.desc()).all()
        ]
