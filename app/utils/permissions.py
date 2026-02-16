from flask_login import current_user

ROLE_ORDER = {
    "player": 1,
    "stat_taker": 2,
    "captain": 3,
    "coach": 4,
    "admin": 5,
}

def can_manage_team_users(team_id: int) -> bool:
    """User management permission: team admin+ for that team, or global superadmin."""
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, "is_superadmin", False):
        return True
    if not team_id or not current_user.team_organization_id:
        return False
    if int(current_user.team_organization_id) != int(team_id):
        return False
    return ROLE_ORDER.get(current_user.role, 1) >= ROLE_ORDER["admin"]
