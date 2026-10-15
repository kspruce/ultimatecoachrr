"""Stats pages (blueprint stats_dashboard). Routes live in the submodules;
the calculations they use live in app/stats."""
from flask import Blueprint

bp = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

def is_admin(user):
    """Check if user has admin role"""
    return user.role == 'admin' if hasattr(user, 'role') else False

def is_coach(user):
    """Check if user has coach role"""
    return user.role == 'coach' if hasattr(user, 'role') else False


# Register the routes (imported for their side effect on bp).
from app.routes.stats import dashboard, player, game, team, exports, api  # noqa: E402,F401
