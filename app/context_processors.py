from flask import session, current_app
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from app import db

def team_info_processor():
    """Make team information available to all templates"""
    from app.models.team_organization import TeamOrganization
    from app.models.team_settings import TeamSettings

    if not current_user.is_authenticated:
        return {'current_team': None, 'available_teams': []}

    try:
        if current_user.is_superadmin or current_user.role == "admin":
            available_teams = TeamOrganization.query.all()
            current_team_id = session.get('current_team_id')
            current_team = None

            if current_team_id:
                current_team = TeamOrganization.query.get(current_team_id)
            elif available_teams:
                current_team = available_teams[0]
                session['current_team_id'] = current_team.id
        else:
            current_team = None
            available_teams = []

            if current_user.team_organization_id:
                current_team = TeamOrganization.query.get(current_user.team_organization_id)
                available_teams = [current_team] if current_team else []

        # NEW: Ensure settings row exists
        if current_team:
            if current_team.settings is None:
                settings = TeamSettings(team_id=current_team.id)
                db.session.add(settings)
                db.session.commit()

        return {
            'current_team': current_team,
            'available_teams': available_teams
        }

    except SQLAlchemyError as e:
        if current_app:
            current_app.logger.error(f"Database error in team_info_processor: {str(e)}")

        db.session.rollback()

        return {
            'current_team': None,
            'available_teams': []
        }
