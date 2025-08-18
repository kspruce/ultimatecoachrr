# app/utils/base_blueprint.py
from flask import Blueprint as FlaskBlueprint
from app.utils.team_filter import team_context

class Blueprint(FlaskBlueprint):
    """Extended Blueprint with team filtering capabilities"""
    
    def route(self, rule, **options):
        """Override route decorator to include team context"""
        original_decorator = super(Blueprint, self).route(rule, **options)
        
        def decorator(f):
            # Apply team_context decorator first
            decorated_function = team_context(f)
            return original_decorator(decorated_function)
            
        return decorator
