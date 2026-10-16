# app/routes/onboarding.py
"""Getting started: the welcome page and checklist for each role."""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import onboarding
from app.models.team_organization import TeamOrganization
from app.utils.team_filter import get_current_team_id

bp = Blueprint('onboarding', __name__, url_prefix='/welcome')


def _current_team():
    team_id = get_current_team_id()
    return TeamOrganization.query.get(team_id) if team_id else None


@bp.route('/')
@login_required
def welcome():
    if current_user.is_guest:
        return redirect(url_for('main.index'))
    team = _current_team()
    checklist = onboarding.progress(current_user, team) if team else None
    onboarding.mark_welcomed(current_user)
    return render_template('onboarding/welcome.html', title='Getting started',
                           team=team, checklist=checklist,
                           role=onboarding.role_info(current_user))


@bp.route('/go/<key>')
@login_required
def go(key):
    """Open a checklist step. "Go and look" steps count as done once opened."""
    team = _current_team()
    step = next((s for s in onboarding.steps_for(current_user, team) if s.key == key), None)
    if step is None:
        abort(404)
    if step.needs_player and current_user.player is None:
        flash('Pick your name from the roster first.', 'info')
        return redirect(url_for('auth.link_player'))
    if step.check is None and not current_user.is_guest:
        onboarding.mark_done(current_user, key)
    return redirect(onboarding.step_target(current_user, step))


@bp.route('/dismiss', methods=['POST'])
@login_required
def dismiss():
    onboarding.dismiss(current_user)
    flash('Checklist hidden. You can open it again from "Getting started" in your menu.', 'info')
    return redirect(url_for('main.index'))


@bp.route('/restore', methods=['POST'])
@login_required
def restore():
    onboarding.restore(current_user)
    return redirect(url_for('main.index'))
