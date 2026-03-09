from functools import wraps
from flask import session, g
from flask_login import current_user

def get_current_team_id():
    """Get the current team ID from session or user.

    For any admin (superadmin or team admin), the session selection always
    takes precedence so that team-switching works correctly.  Falls back to
    the user's own team_organization_id if no session value is present, and
    to None if neither is set (edge-case on very first login).
    """
    if not current_user.is_authenticated:
        return None

    if current_user.is_admin:
        # Admins can switch between teams – respect the session selection first.
        session_team_id = session.get('current_team_id')
        if session_team_id:
            return session_team_id
        # Fall back to their own assigned team (if any) so data is never empty
        # on the very first request before the context processor has set the session.
        return current_user.team_organization_id

    # Regular players always see their own team only.
    return current_user.team_organization_id

def team_context(f):
    """Store current team ID in g object for use in route functions"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.current_team_id = get_current_team_id()
        return f(*args, **kwargs)
    return decorated_function

def filter_query(query, model):
    """Filter a query by team organization if applicable"""
    team_id = getattr(g, 'current_team_id', None)
    
    # If no team ID or model doesn't have team_organization_id, return original query
    if team_id is None or not hasattr(model, 'team_organization_id'):
        return query
        
    # If current user is global admin and no team is selected, return all results
    if current_user.is_admin and current_user.team_organization_id is None and not team_id:
        return query
        
    # Filter by team organization
    return query.filter(model.team_organization_id == team_id)
