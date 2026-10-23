from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional

class TournamentForm(FlaskForm):
    name = StringField('Tournament Name', validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    location = StringField('Location', validators=[Optional()])
    # Year of the club season; blank puts it in the season its start date is in
    season = SelectField('Season', choices=[('', 'From the start date')], validate_choice=False)
    squad_id = SelectField('Squad', choices=[('', 'Whole club')], validate_choice=False)
    submit = SubmitField('Submit')

class TournamentFilterForm(FlaskForm):
    season = SelectField('Season', choices=[('all', 'All time')], validate_choice=False)
    submit = SubmitField('Filter')
