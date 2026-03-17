from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length, Optional
from app.models.user import User
from app.models.player import Player


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')



class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])

    password = PasswordField('Password', validators=[Optional()])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[Optional(), EqualTo('password', message='Passwords must match')]
    )

    team_organization_id = SelectField('Team', coerce=int, validators=[DataRequired()])

    role = SelectField(
        'Role',
        choices=[
            ('guest', 'Guest (Read-only Demo)'),
            ('player', 'Player'),
            ('stat_taker', 'Stat Taker'),
            ('captain', 'Captain'),
            ('coach', 'Coach'),
            ('admin', 'Admin'),
        ],
        validators=[DataRequired()]
    )

    player_id = SelectField('Linked Player', coerce=int, validators=[Optional()], choices=[])

    submit = SubmitField('Save')

    def __init__(self, original_username=None, original_email=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if self.original_username and username.data == self.original_username:
            return
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        if self.original_email and email.data == self.original_email:
            return
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Please use a different email address.')


