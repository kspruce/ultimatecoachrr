# app/utils/query_helpers.py
from flask import g
from app.utils.team_filter import get_current_team_id

def get_team_filtered_query(model_class):
    """Get a query for the model filtered by the current team"""
    if hasattr(model_class, 'team_organization_id'):
        team_id = g.get('current_team_id') or get_current_team_id()
        if team_id:
            return model_class.query.filter_by(team_organization_id=team_id)
    
    # Default to unfiltered query
    return model_class.query
