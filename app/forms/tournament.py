from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional

class TournamentForm(FlaskForm):
    name = StringField('Tournament Name', validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    location = StringField('Location', validators=[Optional()])
    season = StringField('Season', validators=[Optional()])
    submit = SubmitField('Submit')

class TournamentFilterForm(FlaskForm):
    season = StringField('Season', validators=[Optional()])
    submit = SubmitField('Filter')
