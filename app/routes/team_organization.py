# app/routes/team_organization.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g
from flask_login import login_required, current_user
from app import db
from app.models.team_organization import TeamOrganization
from app.forms.team_organization import TeamOrganizationForm

bp = Blueprint('team_organization', __name__, url_prefix='/teams')

@bp.route('/')
@login_required
def index():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    teams = TeamOrganization.query.all()
    return render_template('team_organization/index.html', teams=teams)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    form = TeamOrganizationForm()
    if form.validate_on_submit():
        team = TeamOrganization(
            name=form.name.data,
            slug=form.slug.data,
            description=form.description.data
        )
        db.session.add(team)
        db.session.commit()
        flash(f'Team {team.name} has been created!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, title='Add Team')

@bp.route('/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
def edit(team_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    team = TeamOrganization.query.get_or_404(team_id)
    form = TeamOrganizationForm(obj=team)
    if form.validate_on_submit():
        form.populate_obj(team)
        db.session.commit()
        flash(f'Team {team.name} has been updated!', 'success')
        return redirect(url_for('team_organization.index'))
    return render_template('team_organization/form.html', form=form, team=team, title='Edit Team')

@bp.route('/switch/<int:team_id>')
@login_required
def switch(team_id):
    if not current_user.is_admin:
        flash('Only administrators can switch teams.', 'danger')
        return redirect(url_for('main.index'))
    
    team = TeamOrganization.query.get_or_404(team_id)
    session['current_team_id'] = team.id
    flash(f'Switched to team: {team.name}', 'success')
    return redirect(request.referrer or url_for('main.index'))
