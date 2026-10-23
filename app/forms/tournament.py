from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, IntegerField, SelectField, StringField, SubmitField,
                     TextAreaField)
from wtforms.validators import DataRequired, NumberRange, Optional

class TournamentForm(FlaskForm):
    name = StringField('Tournament Name', validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    location = StringField('Location', validators=[Optional()])
    # Year of the club season; blank puts it in the season its start date is in
    season = SelectField('Season', choices=[('', 'From the start date')], validate_choice=False)
    squad_id = SelectField('Squad', choices=[('', 'Whole club')], validate_choice=False)
    rsvp_deadline = DateField('Reply by', format='%Y-%m-%d', validators=[Optional()])
    squad_size_target = IntegerField('Squad size', validators=[Optional(), NumberRange(min=1, max=60)])
    notes = TextAreaField('Notes for players', validators=[Optional()])
    # Only on the add form: email everyone it's for asking if they can make it
    ask_players = BooleanField('Ask players if they can make it', default=True)
    submit = SubmitField('Submit')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.start_date.data and self.end_date.data and self.end_date.data < self.start_date.data:
            self.end_date.errors.append('The end date is before the start date.')
            return False
        return True

class TournamentFilterForm(FlaskForm):
    season = SelectField('Season', choices=[('all', 'All time')], validate_choice=False)
    submit = SubmitField('Filter')
