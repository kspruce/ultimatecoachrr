from flask import Blueprint
from app.routes.main import bp as main_bp
from app.routes.auth import bp as auth_bp
from app.routes.team import bp as team_bp
from app.routes.game import bp as game_bp
from app.routes.point import bp as point_bp
from app.routes.clip import bp as clip_bp
#from app.routes.drill_routes import bp as drill_bp
from app.routes.session import bp as session_bp
from app.routes.theory import bp as theory_bp
from app.routes.tournament import bp as tournament_bp
from app.routes.stats import bp as stats_bp
from app.routes.playbook import bp as playbook_bp
from app.routes.scouting import bp as scouting_bp

__all__ = [
    'main_bp',
    'auth_bp',
    'team_bp',
    'game_bp',
    'point_bp',
    'clip_bp',
    #'drill_bp',
    'session_bp',
    'theory_bp',
    'tournament_bp',
    'stats_bp',
    'playbook_bp',
    'scouting_bp'
]
