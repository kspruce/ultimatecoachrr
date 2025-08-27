# In app/forms/stats_form.py
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField

class StatsCalculatorForm(FlaskForm):
    scope = SelectField('Calculation Scope', choices=[
        ('game', 'Single Game'),
        ('tournament', 'Tournament'),
        ('season', 'Season'),
        ('all', 'All Games')
    ])
    game_id = SelectField('Select Game', choices=[], validate_choice=False)
    tournament_id = SelectField('Select Tournament', choices=[], validate_choice=False)
    season = SelectField('Select Season', choices=[], validate_choice=False)
    submit = SubmitField('Calculate and Store Statistics')
