# app/routes/team_organization.py
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app import db
from app.models.site_settings import SiteSettings
from app.models.team_signup_invite import TeamSignupInvite
from app.utils.email import email_configured, email_provider, is_real_email, send_email
from app.utils.utils import superadmin_required
from app.utils.team_filter import accessible_teams, can_access_team
from app.models.team_organization import TeamOrganization
from app.models.user import TEAM_ADMIN_ROLES
from app.forms.team_organization import TeamOrganizationForm
import logging
from app.utils.team_data import delete_team_data

logger = logging.getLogger(__name__)

bp = Blueprint('team_organization', __name__, url_prefix='/teams')


def _runs_team(team_id):
    return current_user.is_superadmin or current_user.role_in(team_id) in TEAM_ADMIN_ROLES

@bp.route('/')
@login_required
def index():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    # Only the teams they run (they may just play on others)
    teams = [t for t in accessible_teams(current_user) if _runs_team(t.id)]
    return render_template('team_organization/index.html', teams=teams)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not current_user.is_superadmin:
        flash('Only site superadmins can add teams.', 'danger')
        return redirect(url_for('team_organization.index'))
    
    form = TeamOrganizationForm()
    if form.validate_on_submit():
        team = TeamOrganization(
            name=form.name.data,
            slug=form.slug.data,
            description=form.description.data,
            division=form.division.data,
            logo=form.logo.data.strip() if form.logo.data else None
        )

        db.session.add(team)
        db.session.commit()
        flash(f'Team {team.name} has been created!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, title='Add Team')


@bp.route('/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
def edit(team_id):
    if not _runs_team(team_id):
        flash('You can only edit your own team.', 'danger')
        return redirect(url_for('main.index'))

    team = TeamOrganization.query.get_or_404(team_id)
    form = TeamOrganizationForm(obj=team, team_id=team_id)  # Pass team_id here
    if form.validate_on_submit():
        team.name = form.name.data
        team.slug = form.slug.data
        team.description = form.description.data
        team.division = form.division.data
        # Logo is a URL — save it directly (empty string → None to clear)
        logo_url = form.logo.data.strip() if form.logo.data else None
        team.logo = logo_url if logo_url else None
        db.session.commit()
        flash(f'Team {team.name} has been updated!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, team=team, title='Edit Team')


@bp.route('/switch/<int:team_id>')
@login_required
def switch(team_id):
    """Superadmins switch to any team; everyone else to a team they're on."""
    if not can_access_team(current_user, team_id):
        flash('You are not on that team.', 'danger')
        return redirect(url_for('main.index'))

    team = TeamOrganization.query.get_or_404(team_id)
    session['current_team_id'] = team.id
    flash(f'Switched to team: {team.name}', 'success')
    return redirect(request.referrer or url_for('main.index'))


@bp.route('/delete/<int:team_id>', methods=['POST'])
@login_required
def delete(team_id):
    """Hard delete a team and ALL related data. Superadmin only."""
    if not current_user.is_superadmin:
        flash('Only site superadmins can delete teams.', 'danger')
        return redirect(url_for('team_organization.index'))

    team = TeamOrganization.query.get_or_404(team_id)
    team_name = team.name

    # Safety: require typing the team name to confirm
    confirm = request.form.get('confirm_name', '').strip()
    if confirm != team_name:
        flash(f'Confirmation name did not match. Type exactly: {team_name}', 'danger')
        return redirect(url_for('team_organization.index'))

    try:
        delete_team_data(team_id)
        db.session.commit()
        # Clear session if we just deleted the active team
        if session.get('current_team_id') == team_id:
            session.pop('current_team_id', None)
        flash(f'Team "{team_name}" and all its data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deleting team {team_id}: {e}', exc_info=True)
        flash(f'Error deleting team: {str(e)}', 'danger')

    return redirect(url_for('team_organization.index'))


# ─────────────────────────────────────────────────────────────
# Team sign-ups (superadmin): who may register a new team
# ─────────────────────────────────────────────────────────────

SIGNUP_LINK_DAYS = (7, 14, 30, 90)


@bp.route('/signups')
@login_required
@superadmin_required
def signups():
    links = TeamSignupInvite.query.order_by(TeamSignupInvite.created_at.desc()).limit(100).all()
    return render_template('team_organization/signups.html',
                           settings=SiteSettings.get(), links=links,
                           link_days=SIGNUP_LINK_DAYS,
                           email_enabled=email_configured(),
                           email_provider=email_provider(),
                           admin_email=(current_user.email if is_real_email(current_user.email) else ''))


@bp.route('/signups/open', methods=['POST'])
@login_required
@superadmin_required
def set_signup_open():
    settings = SiteSettings.get()
    settings.open_team_registration = request.form.get('open') == '1'
    db.session.commit()
    if settings.open_team_registration:
        flash('Team sign-up is open: anyone can register a team.', 'warning')
    else:
        flash('Team sign-up is invite-only: new teams need a sign-up link.', 'success')
    return redirect(url_for('team_organization.signups'))


@bp.route('/signups/two-factor', methods=['POST'])
@login_required
@superadmin_required
def set_two_factor_required():
    settings = SiteSettings.get()
    settings.require_two_factor = request.form.get('required') == '1'
    db.session.commit()
    if settings.require_two_factor:
        flash('Superadmins now need two-step sign-in.', 'success')
    else:
        flash('Two-step sign-in is optional for superadmins.', 'warning')
    return redirect(url_for('team_organization.signups'))


@bp.route('/signups/links', methods=['POST'])
@login_required
@superadmin_required
def create_signup_link():
    note = request.form.get('note', '').strip()[:200]
    email = request.form.get('email', '').strip()[:120]
    if email and not is_real_email(email):
        flash("That email address doesn't look right.", 'danger')
        return redirect(url_for('team_organization.signups'))
    days = request.form.get('days', type=int)
    days = days if days in SIGNUP_LINK_DAYS else 14

    invite = TeamSignupInvite.create(current_user.id, note=note, email=email, expires_days=days)
    db.session.add(invite)
    db.session.commit()

    link = url_for('auth.register_team', invite=invite.token, _external=True)
    if email and send_email(
            email, "You're invited to set up your team on Ultimate Coach",
            f'Hi{" " + note if note else ""},\n\n'
            f'You\'ve been invited to set up your team on Ultimate Coach. '
            f'Use this link to create your team and your team admin account:\n\n{link}\n\n'
            f'The link works once and expires in {days} days.\n'):
        flash(f'Sign-up link created and emailed to {email}.', 'success')
    else:
        flash('Sign-up link created. Copy it below and send it to the club.', 'success')
    return redirect(url_for('team_organization.signups', new=invite.id))


@bp.route('/signups/links/<int:link_id>/revoke', methods=['POST'])
@login_required
@superadmin_required
def revoke_signup_link(link_id):
    invite = TeamSignupInvite.query.get_or_404(link_id)
    if invite.is_valid:
        invite.revoked_at = datetime.utcnow()
        db.session.commit()
        flash('Sign-up link revoked.', 'success')
    return redirect(url_for('team_organization.signups'))


@bp.route('/signups/test-email', methods=['POST'])
@login_required
@superadmin_required
def send_test_email():
    to = request.form.get('email', '').strip()
    if not email_configured():
        flash('Email is not set up yet. See docs/EMAIL_SETUP.md.', 'warning')
    elif not is_real_email(to):
        flash('Enter the address to send the test email to.', 'danger')
    else:
        try:
            send_email(to, 'Ultimate Coach test email',
                       'Email from Ultimate Coach is working.\n', wait=True)
            flash(f'Test email sent to {to}. Check the inbox (and spam folder).', 'success')
        except Exception as e:
            logger.error(f'Test email failed: {e}', exc_info=True)
            flash(f'Sending failed: {e}', 'danger')
    return redirect(url_for('team_organization.signups'))
