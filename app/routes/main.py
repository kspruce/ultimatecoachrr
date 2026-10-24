from flask import Blueprint, render_template, redirect, request, url_for
from app.utils.team_filter import get_current_team_id
from flask_login import current_user
from app import csrf, db, limiter, onboarding
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


bp = Blueprint('main', __name__)


@bp.route('/')
@bp.route('/index')
def index():
    # First visit (or a promotion): show the welcome for their role
    if current_user.is_authenticated and onboarding.needs_welcome(current_user):
        return redirect(url_for('onboarding.welcome'))
    if not current_user.is_authenticated:
        return render_template('index.html', title='Home')

    from app.models.team_organization import TeamOrganization
    from app.utils import dashboard

    team_id = get_current_team_id()
    team = TeamOrganization.query.get(team_id) if team_id else None
    checklist = roster_signup = None
    my_training = []
    if team and not current_user.is_guest:
        checklist = onboarding.progress(current_user, team)
        if checklist and (checklist['dismissed'] or checklist['complete']):
            checklist = None
        if current_user.is_coach:
            roster_signup = onboarding.roster_signup(team.id)
        player = getattr(current_user, 'player', None)
        if player is not None and player.team_organization_id == team.id:
            try:
                from app.utils.programmes import players_week
                my_training = players_week(player)
            except Exception:
                logger.exception('Could not work out this week\'s programme sessions')

    data = {}
    if team:
        try:
            data = dashboard.build(current_user, team.id, team.settings, roster_signup)
        except Exception:
            # A broken panel shouldn't take the home page down with it
            logger.exception('Could not build the dashboard')
            db.session.rollback()

    return render_template('index.html',
                           title='Home',
                           team_name=team.name if team else None,
                           checklist=checklist,
                           my_training=my_training,
                           **data)


@bp.route('/privacy')
def privacy():
    from flask import current_app
    from app.utils.email import email_provider
    config = current_app.config
    return render_template('privacy.html', title='Privacy policy',
                           operator=config.get('SITE_OPERATOR'),
                           contact=config.get('PRIVACY_CONTACT_EMAIL'),
                           backup_days=config.get('BACKUP_RETENTION_DAYS', 30),
                           email_service=email_provider(),
                           sentry=bool(config.get('SENTRY_DSN')),
                           s3=bool(config.get('AWS_BUCKET_NAME')),
                           discord='discord.settings' in current_app.view_functions)


@bp.route('/about')
def about():
    return render_template('about.html', title='About')

@bp.route('/how-to-use')
def how_to_use():
    """Display the How to Use guide page."""
    return render_template('how_to_use.html', title='How to Use Ultimate Coach')

@bp.route('/admin/data-management')
def data_management():
    """The old backup page: everything now lives on the enhanced page."""
    return redirect(url_for('data_management.data_management'), code=301)


@bp.route('/csp-report', methods=['POST'])
@csrf.exempt
@limiter.limit('30 per minute')
def csp_report():
    """Browsers post here when a page breaks the report-only CSP (see
    CSP_REPORT_ONLY in app/__init__.py)."""
    report = (request.get_json(force=True, silent=True) or {}).get('csp-report') or {}
    logger.warning('CSP would block %s (%s) on %s', str(report.get('blocked-uri'))[:200],
                   str(report.get('violated-directive'))[:80],
                   str(report.get('document-uri'))[:200])
    return '', 204
