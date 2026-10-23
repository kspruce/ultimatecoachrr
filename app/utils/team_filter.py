from functools import wraps
from flask import session, g
from flask_login import current_user

def get_current_team_id():
    """The team whose data the current user is working on.

    Superadmins can switch between every team (the choice is kept in the
    session) and default to their own team. Everyone else switches between
    the teams they belong to, starting on their home team.
    """
    if not current_user.is_authenticated:
        return None

    cached = g.get('current_team')
    if cached and cached[0] == current_user.id:
        return cached[1]
    team_id = (_valid_superadmin_team_id() if current_user.is_superadmin
               else _valid_member_team_id())
    g.current_team = (current_user.id, team_id)
    return team_id


def team_row_or_404(model, row_id):
    """Fetch a row by id only if it belongs to the current team, else 404."""
    return model.query.filter_by(id=row_id, team_organization_id=get_current_team_id()).first_or_404()


def accessible_teams(user):
    """Teams the user may view and switch to, in a stable order."""
    from app.models.team_organization import TeamOrganization
    if not user.is_authenticated:
        return []
    if user.is_superadmin:
        return TeamOrganization.query.order_by(TeamOrganization.id).all()
    if not user.team_ids:
        return []
    return (TeamOrganization.query.filter(TeamOrganization.id.in_(user.team_ids))
            .order_by(TeamOrganization.name).all())


def can_access_team(user, team_id):
    return user.is_authenticated and (user.is_superadmin or user.is_member_of(team_id))


def _valid_member_team_id():
    """The team they switched to if they're still on it, else their home
    team, else any team they're on."""
    team_ids = current_user.team_ids
    if not team_ids:
        return current_user.team_organization_id
    for team_id in (session.get('current_team_id'), current_user.team_organization_id):
        if team_id in team_ids:
            return team_id
    return team_ids[0]


def _valid_superadmin_team_id():
    """The superadmin's chosen team if it still exists, else their own team,
    else the first team."""
    from app.models.team_organization import TeamOrganization
    for team_id in (session.get('current_team_id'), current_user.team_organization_id):
        if team_id and TeamOrganization.query.get(team_id):
            return team_id
    team = TeamOrganization.query.order_by(TeamOrganization.id).first()
    return team.id if team else None

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
        
    # Filter by team organization
    return query.filter(model.team_organization_id == team_id)


def team_player_ids(raw_ids):
    """The ids in `raw_ids` that are players on the current team, in order and
    without duplicates; anything else (another team's players, junk) is dropped."""
    from app.models.player import Player
    ids = []
    for raw in raw_ids:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid not in ids:
            ids.append(pid)
    if not ids:
        return []
    valid = {pid for (pid,) in Player.query.with_entities(Player.id).filter(
        Player.id.in_(ids), Player.team_organization_id == get_current_team_id())}
    return [pid for pid in ids if pid in valid]
