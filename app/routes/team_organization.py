# app/routes/team_organization.py
from flask import Blueprint, redirect, url_for, flash, session, request
from flask_login import login_required, current_user
from app.models.team_organization import TeamOrganization

bp = Blueprint('team_organization', __name__, url_prefix='/teams')

@bp.route('/switch/<int:team_id>')
@login_required
def switch(team_id):
    # Only admins can switch teams
    if not current_user.is_admin:
        flash('Only administrators can switch teams.', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if team exists
    team = TeamOrganization.query.get_or_404(team_id)
    
    # Store the selected team in the session
    session['current_team_id'] = team.id
    flash(f'Switched to team: {team.name}', 'success')
    
    # Redirect back to the referring page or home
    return redirect(request.referrer or url_for('main.index'))

