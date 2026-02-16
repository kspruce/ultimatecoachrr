# app/forms/team_organization.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, ValidationError
from app.models.team_organization import TeamOrganization

class TeamOrganizationForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired()])
    slug = StringField('Slug', validators=[DataRequired()])
    description = TextAreaField('Description')
    submit = SubmitField('Save')
    division = SelectField(
        "Division",
        choices=[
            ("open", "Open"),
            ("womens", "Womens"),
            ("mixed", "Mixed")
        ],
        validators=[DataRequired()]
    )

    
    def __init__(self, *args, **kwargs):
        self.team_id = kwargs.pop('team_id', None)
        super(TeamOrganizationForm, self).__init__(*args, **kwargs)
    
    def validate_slug(self, slug):
        # Query for any team with this slug
        team = TeamOrganization.query.filter_by(slug=slug.data).first()
        
        # If we found a team with this slug and it's not the one we're editing
        if team and (self.team_id is None or team.id != self.team_id):
            raise ValidationError('This slug is already in use. Please choose a different one.')
