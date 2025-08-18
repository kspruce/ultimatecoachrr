# app/utils/query_helpers.py
from flask import g
from flask_login import current_user

def get_team_filtered_query(model_class):
    """Get a query for the model filtered by the current team"""
    if hasattr(model_class, 'team_organization_id'):
        # If current user is global admin and no team is selected, return all results
        if current_user.is_admin and current_user.team_organization_id is None and not g.current_team_id:
            return model_class.query
            
        # Filter by team organization
        if g.current_team_id:
            return model_class.query.filter_by(team_organization_id=g.current_team_id)
            
        # Regular user with team organization
        if current_user.team_organization_id:
            return model_class.query.filter_by(team_organization_id=current_user.team_organization_id)
    
    # Default to unfiltered query
    return model_class.query
