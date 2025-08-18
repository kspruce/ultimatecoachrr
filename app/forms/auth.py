from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
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
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('password')])
    role = SelectField('Role', choices=[
        ('player', 'Player'),
        ('stat_taker', 'Stat Taker'),
        ('coach', 'Coach'),
        ('admin', 'Admin')
    ], validators=[DataRequired()])
    player_id = SelectField('Link to Player', coerce=int, default=0)
    team_organization_id = SelectField('Team', coerce=int)
    submit = SubmitField('Save User')
    
    def __init__(self, *args, original_username=None, original_email=None, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        # Store original values for validation
        self.original_username = original_username
        self.original_email = original_email
        
        # Populate player choices
        from app.models.player import Player
        player_choices = [(0, 'None')] + [
            (p.id, p.name) for p in Player.query.filter_by(active=True).order_by(Player.name).all()
        ]
        self.player_id.choices = player_choices
        
        # Populate team choices
        from app.models.team_organization import TeamOrganization
        self.team_organization_id.choices = [(0, 'None')] + [
            (t.id, t.name) for t in TeamOrganization.query.order_by(TeamOrganization.name).all()
        ]
    
    def validate_username(self, username):
        if self.original_username is None or username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')
    
    def validate_email(self, email):
        if self.original_email is None or email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('Please use a different email address.')
