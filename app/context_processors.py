from flask import session, current_app
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from app import db

def team_info_processor():
    """Make team information available to all templates"""
    from app.models.team_organization import TeamOrganization
    from app.models.team_settings import TeamSettings

    # current_user is None when rendering outside a request (e.g. background
    # jobs like the playbook PDF export) — treat it like an anonymous user.
    if not current_user or not current_user.is_authenticated:
        return {'current_team': None, 'available_teams': [], 'is_guest': False, 'nav_gameday_tournaments': []}

    try:
        if current_user.is_superadmin or current_user.role == "admin":
            available_teams = TeamOrganization.query.all()
            current_team_id = session.get('current_team_id')
            current_team = None

            if current_team_id:
                current_team = TeamOrganization.query.get(current_team_id)
            elif available_teams:
                current_team = available_teams[0]
                session['current_team_id'] = current_team.id
        else:
            current_team = None
            available_teams = []

            if current_user.team_organization_id:
                current_team = TeamOrganization.query.get(current_user.team_organization_id)
                available_teams = [current_team] if current_team else []

        # NEW: Ensure settings row exists
        if current_team:
            if current_team.settings is None:
                settings = TeamSettings(team_id=current_team.id)
                db.session.add(settings)
                db.session.commit()

        # Tournaments for the current team — used in nav "Game Day" links
        nav_gameday_tournaments = []
        if current_team:
            try:
                from app.models.tournament import Tournament
                nav_gameday_tournaments = (
                    Tournament.query
                    .filter_by(team_organization_id=current_team.id)
                    .order_by(Tournament.start_date.desc())
                    .limit(8)
                    .all()
                )
            except Exception:
                pass

        return {
            'current_team': current_team,
            'available_teams': available_teams,
            'is_guest': current_user.role == 'guest',
            'nav_gameday_tournaments': nav_gameday_tournaments,
        }

    except SQLAlchemyError as e:
        if current_app:
            current_app.logger.error(f"Database error in team_info_processor: {str(e)}")

        db.session.rollback()

        return {
            'current_team': None,
            'available_teams': [],
            'is_guest': False,
            'nav_gameday_tournaments': [],
        }
