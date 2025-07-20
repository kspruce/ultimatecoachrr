from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired

class RSVPForm(FlaskForm):
    """Form for RSVPing to sessions and tournaments."""
    status = SelectField(
        'Your Status',
        choices=[
            ('attending', 'Attending'),
            ('maybe', 'Maybe'),
            ('not_attending', 'Not Attending')
        ],
        validators=[DataRequired()]
    )
    notes = TextAreaField('Notes')
    submit = SubmitField('Submit RSVP')