from flask import Blueprint, render_template, redirect, url_for, flash, request
from urllib.parse import urlparse
from app import db
from app.models.user import User
from app.forms.auth import LoginForm, RegistrationForm
from flask_login import login_user, logout_user, current_user, login_required
import logging
from app.models.player import Player
from app.forms.auth import UserForm
from app.models.team_organization import TeamOrganization  # Add this import
from flask import abort
from app.utils.permissions import can_manage_team_users





# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))
        
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            logger.info(f"Login attempt for user: {form.username.data}")
            
            if user is None or not user.check_password(form.password.data):
                logger.warning(f"Failed login attempt for user: {form.username.data}")
                flash('Invalid username or password')
                return redirect(url_for('auth.login'))
            
            login_user(user, remember=form.remember_me.data)
            logger.info(f"Successful login for user: {user.username}")
            
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.index')
            return redirect(next_page)
        
        return render_template('auth/login.html', title='Sign In', form=form)
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        flash('An error occurred during login. Please try again.')
        return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))
        
        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            logger.info(f"New user registered: {user.username}")
            flash('Congratulations, you are now a registered user!')
            return redirect(url_for('auth.login'))
        
        return render_template('auth/register.html', title='Register', form=form)
    
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        flash('An error occurred during registration. Please try again.')
        return redirect(url_for('auth.register'))

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/users')
@login_required
def users():
    # Superadmin can browse all teams; others only their team
    team_id = request.args.get('team_id', type=int)

    if current_user.is_superadmin:
        teams = TeamOrganization.query.order_by(TeamOrganization.name).all()
        # Default to first team if none selected
        if not team_id and teams:
            team_id = teams[0].id
    else:
        if not current_user.team_organization_id:
            flash('You are not assigned to a team. Ask an admin to assign you.', 'danger')
            return redirect(url_for('main.index'))
        team_id = int(current_user.team_organization_id)
        teams = [TeamOrganization.query.get(team_id)]

    if not team_id:
        users = []
        current_team = None
    else:
        if not can_manage_team_users(team_id):
            flash('You do not have permission to manage users for this team.', 'danger')
            return redirect(url_for('main.index'))

        users = User.query.filter_by(team_organization_id=team_id).all()
        current_team = TeamOrganization.query.get(team_id)

    return render_template(
        'auth/users.html',
        users=users,
        teams=teams,
        current_team=current_team
    )



@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    # Determine which team we are managing
    if current_user.is_superadmin:
        team_id = request.args.get('team_id', type=int)
    else:
        team_id = int(current_user.team_organization_id) if current_user.team_organization_id else None

    if not team_id:
        flash('Select a team first.', 'warning')
        return redirect(url_for('auth.users'))

    if not can_manage_team_users(team_id):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    form = UserForm()

    # Team choices: superadmin can choose; team admin is locked
    if current_user.is_superadmin:
        form.team_organization_id.choices = [(t.id, t.name) for t in TeamOrganization.query.order_by(TeamOrganization.name).all()]
        form.team_organization_id.data = team_id
    else:
        # lock to their team
        team = TeamOrganization.query.get(team_id)
        form.team_organization_id.choices = [(team.id, team.name)]
        form.team_organization_id.data = team_id

    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
            team_organization_id=form.team_organization_id.data
        )

        if form.password.data:
            user.set_password(form.password.data)

        # Force: only superadmin can create superadmin (we won't expose this in form)
        user.is_superadmin = False

        db.session.add(user)
        db.session.commit()

        # Link to player if selected
        if form.player_id.data and form.player_id.data > 0:
            player = Player.query.get(form.player_id.data)
            if player:
                # Ensure 1:1 player->user
                if player.user_id and player.user_id != user.id:
                    other_user = User.query.get(player.user_id)
                    if other_user:
                        flash(f'Player was unlinked from user {other_user.username}', 'warning')

                player.user_id = user.id
                player.team_organization_id = user.team_organization_id
                db.session.commit()

        flash(f'User {user.username} has been created!', 'success')
        return redirect(url_for('auth.users', team_id=team_id))

    return render_template('auth/user_form.html', form=form, title='Add User')



@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    # Which team are we managing?
    team_id = user.team_organization_id
    if not team_id:
        flash('This user is not assigned to a team.', 'warning')
        return redirect(url_for('auth.users'))

    if not can_manage_team_users(team_id):
        flash('You do not have permission to edit users for this team.', 'danger')
        return redirect(url_for('main.index'))

    form = UserForm(
        obj=user,
        original_username=user.username,
        original_email=user.email
    )

    # Team selector: superadmin can move users; team admin cannot
    if current_user.is_superadmin:
        form.team_organization_id.choices = [(t.id, t.name) for t in TeamOrganization.query.order_by(TeamOrganization.name).all()]
    else:
        team = TeamOrganization.query.get(team_id)
        form.team_organization_id.choices = [(team.id, team.name)]
        form.team_organization_id.data = team_id

    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data

        # Only superadmin can change team
        if current_user.is_superadmin:
            user.team_organization_id = form.team_organization_id.data

        if form.password.data:
            user.set_password(form.password.data)

        # Update player link (1:1)
        if user.player and (form.player_id.data == 0 or form.player_id.data != user.player.id):
            user.player.user_id = None

        if form.player_id.data and form.player_id.data > 0:
            player = Player.query.get(form.player_id.data)
            if player:
                if player.user_id and player.user_id != user.id:
                    other_user = User.query.get(player.user_id)
                    if other_user:
                        flash(f'Player was unlinked from user {other_user.username}', 'warning')

                player.user_id = user.id
                player.team_organization_id = user.team_organization_id

        db.session.commit()
        flash(f'User {user.username} has been updated!', 'success')
        return redirect(url_for('auth.users', team_id=user.team_organization_id))

    return render_template('auth/user_form.html', form=form, user=user, title='Edit User')




@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('auth.users'))

    team_id = user.team_organization_id
    if not team_id or not can_manage_team_users(team_id):
        flash('You do not have permission to delete users for this team.', 'danger')
        return redirect(url_for('main.index'))

    if user.player:
        user.player.user_id = None

    db.session.delete(user)
    db.session.commit()

    flash(f'User {user.username} has been deleted!', 'success')
    return redirect(url_for('auth.users', team_id=team_id))


@bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')

@bp.route('/link_player', methods=['GET', 'POST'])
@login_required
def link_player():
    # Get players that aren't linked to any user
    available_players = Player.query.filter(
        (Player.user_id == None) | (Player.user_id == current_user.id)
    ).filter_by(active=True).order_by(Player.name).all()
    
    if request.method == 'POST':
        player_id = request.form.get('player_id', type=int)
        if player_id:
            player = Player.query.get(player_id)
            if player:
                # If player is already linked to another user, unlink it
                if player.user_id and player.user_id != current_user.id:
                    other_user = User.query.get(player.user_id)
                    if other_user:
                        flash(f'Player was unlinked from user {other_user.username}', 'warning')
                
                # Unlink any previously linked player for this user
                if current_user.player and current_user.player.id != player_id:
                    current_user.player.user_id = None
                
                player.user_id = current_user.id
                db.session.commit()
                
                flash(f'You are now linked to player {player.name}!', 'success')
                return redirect(url_for('auth.profile'))
            else:
                flash('Invalid player selected.', 'error')
        else:
            flash('Please select a player.', 'error')
    
    return render_template('auth/link_player.html', players=available_players)
