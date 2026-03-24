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

    def __init__(self, *args, team_id=None, **kwargs):
        super(GameForm, self).__init__(*args, **kwargs)
        # Populate tournament choices — filtered to current team when team_id is provided
        t_query = Tournament.query
        if team_id:
            t_query = t_query.filter_by(team_organization_id=team_id)
        self.tournament_id.choices = [(0, 'No Tournament')] + [
            (t.id, t.name) for t in t_query.order_by(Tournament.start_date.desc()).all()
        ]
        # Populate players_present choices — filtered to current team when team_id is provided
        p_query = Player.query.filter_by(active=True)
        if team_id:
            p_query = p_query.filter_by(team_organization_id=team_id)
        self.players_present.choices = [(p.id, f"{p.name} (#{p.jersey_number})") for p in p_query.all()]

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

    def __init__(self, *args, team_id=None, **kwargs):
        super(GameFilterForm, self).__init__(*args, **kwargs)
        # Populate tournament choices — filtered to current team when team_id is provided
        t_query = Tournament.query
        if team_id:
            t_query = t_query.filter_by(team_organization_id=team_id)
        self.tournament_id.choices = [(0, 'All Tournaments')] + [
            (t.id, t.name) for t in t_query.order_by(Tournament.start_date.desc()).all()
        ]
