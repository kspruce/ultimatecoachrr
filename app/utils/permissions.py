from flask_login import current_user

from app.models.user import ROLE_ORDER


def _level(role):
    return ROLE_ORDER.get(role or 'player', ROLE_ORDER['player'])


def can_manage_team_users(team_id: int) -> bool:
    """User management permission: coach+ for that team, or global superadmin."""
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, "is_superadmin", False):
        return True
    if not team_id or not current_user.team_organization_id:
        return False
    if int(current_user.team_organization_id) != int(team_id):
        return False
    return _level(current_user.role) >= ROLE_ORDER["coach"]


def can_manage_user(target, actor=None) -> bool:
    """May `actor` edit, delete or reset the password of `target`?

    Superadmins can manage everyone. Everyone else can only manage people on
    their own team whose role is strictly below theirs, and never a
    superadmin, so a coach can't take over a team admin's (or your) account.
    People change their own details from their profile, not from here.
    """
    actor = actor or current_user
    if not actor.is_authenticated:
        return False
    if actor.is_superadmin:
        return True
    if target.is_superadmin or target.id == actor.id:
        return False
    if not can_manage_team_users(target.team_organization_id):
        return False
    return _level(target.role) < _level(actor.role)


def grantable_roles(actor=None):
    """Role keys `actor` may give someone: superadmins any role, everyone
    else roles up to their own (so a coach can add a co-coach, but only a
    team admin can make someone a team admin)."""
    actor = actor or current_user
    if actor.is_superadmin:
        return list(ROLE_ORDER)
    return [role for role, level in ROLE_ORDER.items() if level <= _level(actor.role)]
