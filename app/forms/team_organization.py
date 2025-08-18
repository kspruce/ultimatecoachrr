# app/forms/team_organization.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError
from app.models.team_organization import TeamOrganization
import re

class TeamOrganizationForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired(), Length(min=2, max=100)])
    slug = StringField('Slug (URL-friendly name)', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description')
    submit = SubmitField('Save Team')
    
    def validate_slug(self, slug):
        # Check if slug is URL-friendly
        if not re.match('^[a-z0-9-]+$', slug.data):
            raise ValidationError('Slug must contain only lowercase letters, numbers, and hyphens.')
        
        # Check if slug is unique
        team = TeamOrganization.query.filter_by(slug=slug.data).first()
        if team and (not hasattr(self, 'team') or team.id != self.team.id):
            raise ValidationError('This slug is already in use. Please choose a different one.')
