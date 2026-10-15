# app/routes/team_organization.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app import db
from app.utils.team_filter import accessible_teams, can_access_team
from app.models.team_organization import TeamOrganization
from app.forms.team_organization import TeamOrganizationForm
import logging
from sqlalchemy import or_

logger = logging.getLogger(__name__)

bp = Blueprint('team_organization', __name__, url_prefix='/teams')

@bp.route('/')
@login_required
def index():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    teams = accessible_teams(current_user)
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
    if not (current_user.is_admin and can_access_team(current_user, team_id)):
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
    if not current_user.is_superadmin:
        flash('Only site superadmins can switch teams.', 'danger')
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
        _delete_team_data(team_id)
        db.session.delete(team)
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


def _delete_team_data(team_id):
    """Delete every row that belongs to a team, children before parents.

    Walks all tables in reverse foreign-key order, so new tables are covered
    without editing this function: tables with team_organization_id lose
    that team's rows; tables without it (association tables, player
    feedback, ...) lose the rows that point at one of the team's rows.
    Superadmins are detached from the team rather than deleted.
    """
    from sqlalchemy import select
    from app.models.user import User

    User.query.filter_by(team_organization_id=team_id, is_superadmin=True).update(
        {'team_organization_id': None}, synchronize_session=False)

    tables = db.metadata.sorted_tables  # parents before children
    scoped = {t.name for t in tables if 'team_organization_id' in t.c}
    for table in reversed(tables):
        if table.name == 'team_organization':
            continue
        if 'team_organization_id' in table.c:
            condition = table.c.team_organization_id == team_id
        else:
            links = []
            for fk in table.foreign_keys:
                parent = fk.column.table
                if parent.name == 'team_organization':
                    links.append(fk.parent == team_id)
                elif parent.name in scoped:
                    links.append(fk.parent.in_(
                        select(fk.column).where(parent.c.team_organization_id == team_id)))
            if not links:
                continue
            condition = or_(*links)
        result = db.session.execute(table.delete().where(condition))
        if result.rowcount:
            logger.info(f'[TeamDelete] {table.name}: {result.rowcount} rows')
