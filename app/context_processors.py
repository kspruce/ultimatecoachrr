# app/context_processors.py
from flask import session, current_app
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from app import db  # Make sure to import db

def team_info_processor():
    """Make team information available to all templates"""
    # Import inside the function to avoid circular imports
    from app.models.team_organization import TeamOrganization
    
    if not current_user.is_authenticated:
        return {'current_team': None, 'available_teams': []}
    
    try:
        # For admins, get all teams
        if current_user.is_admin:
            available_teams = TeamOrganization.query.all()
            
            # Get current team from session
            current_team_id = session.get('current_team_id')
            current_team = None
            
            if current_team_id:
                # Try to get team from session
                current_team = TeamOrganization.query.get(current_team_id)
            elif available_teams:
                # Default to first available team
                current_team = available_teams[0]
                session['current_team_id'] = current_team.id
        else:
            # For regular users, only their assigned team
            current_team = None
            available_teams = []
            
            if current_user.team_organization_id:
                current_team = TeamOrganization.query.get(current_user.team_organization_id)
                available_teams = [current_team] if current_team else []
        
        return {
            'current_team': current_team,
            'available_teams': available_teams
        }
    
    except SQLAlchemyError as e:
        # Log the error
        if current_app:
            current_app.logger.error(f"Database error in team_info_processor: {str(e)}")
        
        # Roll back the transaction
        db.session.rollback()
        
        # Return empty data to prevent template errors
        return {
            'current_team': None,
            'available_teams': []
        }
