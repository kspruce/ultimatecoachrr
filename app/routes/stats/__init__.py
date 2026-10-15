"""Stats pages (blueprint stats_dashboard). Routes live in the submodules;
the calculations they use live in app/stats."""
from flask import Blueprint

bp = Blueprint('stats_dashboard', __name__, url_prefix='/stats')

# Register the routes (imported for their side effect on bp).
from app.routes.stats import dashboard, player, game, team, exports, api  # noqa: E402,F401
