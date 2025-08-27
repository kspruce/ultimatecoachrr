# app/utils/team_utils.py
from flask_login import current_user
from flask import g

def get_current_team_id():
    """
    Get the current team organization ID from the logged-in user or from the Flask g object.
    
    Returns:
        int: The team organization ID
    """
    # First check if it's stored in Flask's g object (for the current request)
    if hasattr(g, 'current_team_id'):
        return g.current_team_id
    
    # Otherwise, get it from the current user
    if current_user and hasattr(current_user, 'team_organization_id'):
        return current_user.team_organization_id
    
    # Return None if no team ID is found
    return None
