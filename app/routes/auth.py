from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from urllib.parse import urlparse
from flask_login import login_user, logout_user, current_user, login_required
import logging

from app import db
from app.models.user import User
from app.models.player import Player
from app.models.team_organization import TeamOrganization
from app.forms.auth import LoginForm, RegistrationForm, UserForm
from app.utils.permissions import can_manage_team_users

# ---------------------------------------
# Setup
# ---------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

# ---------------------------------------
# Internal Helpers
# ---------------------------------------

def _get_managed_team_id():
    if current_user.is_superadmin:
        team_id = request.args.get('team_id', type=int)

        if team_id:
            return team_id

        first_team = TeamOrganization.query.order_by(
            TeamOrganization.name
        ).first()

        return first_team.id if first_team else None

    return current_user.team_organization_id



def _populate_team_choices(form, selected_team_id, set_default=True):
    """
    Populate team dropdown based on role.
    Only sets default value if set_default=True (for GET requests).
    """
    if current_user.is_superadmin:
        teams = TeamOrganization.query.order_by(TeamOrganization.name).all()
        form.team_organization_id.choices = [(t.id, t.name) for t in teams]
        if set_default:
            form.team_organization_id.data = selected_team_id
    else:
        team = TeamOrganization.query.get(selected_team_id)
        form.team_organization_id.choices = [(team.id, team.name)]
        if set_default:
            form.team_organization_id.data = team.id


def _populate_player_choices(form, team_id):

    players = Player.query.filter_by(
        team_organization_id=team_id,
        active=True
    ).order_by(Player.name).all()

    form.player_id.choices = [(0, "No Player")] + [
        (p.id, f"{p.name} ({p.jersey_number or ''})")
        for p in players
    ]



def _link_player_to_user(user, player_id):
    """
    Ensure clean 1:1 linking between player and user.
    """
    if not player_id or player_id == 0:
        # Unlink existing player if removing
        if user.player:
            user.player.user_id = None
        return

    player = Player.query.get(player_id)
    if not player:
        return

    # Unlink from previous user if needed
    if player.user_id and player.user_id != user.id:
        other_user = User.query.get(player.user_id)
        if other_user:
            flash(f'Player was unlinked from user {other_user.username}', 'warning')

    # Unlink user's current player if different
    if user.player and user.player.id != player_id:
        user.player.user_id = None

    player.user_id = user.id
    player.team_organization_id = user.team_organization_id


# ---------------------------------------
# Authentication Routes
# ---------------------------------------

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
                flash('Invalid username or password', 'danger')
                return redirect(url_for('auth.login'))

            login_user(user, remember=form.remember_me.data)

            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.index')

            return redirect(next_page)

        return render_template('auth/login.html', title='Sign In', form=form)

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        flash('An error occurred during login.', 'danger')
        return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))

        form = RegistrationForm()

        if form.validate_on_submit():
            user = User(
                username=form.username.data,
                email=form.email.data
            )
            user.set_password(form.password.data)

            db.session.add(user)
            db.session.commit()

            flash('Registration successful.', 'success')
            return redirect(url_for('auth.login'))

        return render_template('auth/register.html', title='Register', form=form)

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        flash('An error occurred during registration.', 'danger')
        return redirect(url_for('auth.register'))


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


# ---------------------------------------
# User Management
# ---------------------------------------

@bp.route('/users')
@login_required
def users():

    team_id = _get_managed_team_id()

    if not team_id:
        flash("Select a team first.", "warning")
        return redirect(url_for("main.index"))

    if not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    teams = TeamOrganization.query.order_by(TeamOrganization.name).all() \
        if current_user.is_superadmin \
        else [TeamOrganization.query.get(team_id)]

    users = User.query.filter_by(
        team_organization_id=team_id
    ).order_by(User.username).all()

    current_team = TeamOrganization.query.get(team_id)

    return render_template(
        "auth/users.html",
        users=users,
        teams=teams,
        current_team=current_team
    )


@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():

    team_id = _get_managed_team_id()

    if not team_id:
        flash("Select a team first.", "warning")
        return redirect(url_for("auth.users"))

    if not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    form = UserForm()

    # Populate choices but only set defaults on GET request
    _populate_team_choices(form, team_id, set_default=(request.method == 'GET'))
    _populate_player_choices(form, team_id)

    if request.method == "POST":
        current_app.logger.debug("VALID:", form.validate())
        current_app.logger.error("ERRORS:", form.errors)

    if form.validate_on_submit():

        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
            team_organization_id=form.team_organization_id.data,
            is_superadmin=False
        )

        if form.password.data:
            user.set_password(form.password.data)

        db.session.add(user)
        db.session.flush()

        _link_player_to_user(user, form.player_id.data)

        db.session.commit()

        flash(f"User {user.username} created.", "success")
        return redirect(url_for("auth.users", team_id=team_id))

    return render_template("auth/user_form.html", form=form, title="Add User")


@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):

    user = User.query.get_or_404(user_id)
    team_id = user.team_organization_id

    if not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    form = UserForm(
        original_username=user.username,
        original_email=user.email
    )

    # Populate choices but only set defaults on GET request
    _populate_team_choices(form, team_id, set_default=(request.method == 'GET'))
    _populate_player_choices(form, team_id)

    if request.method == "GET":
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role
        form.team_organization_id.data = user.team_organization_id
        form.player_id.data = user.player.id if user.player else 0

    if request.method == "POST":
        current_app.logger.debug("VALID:", form.validate())
        current_app.logger.error("ERRORS:", form.errors)

    if form.validate_on_submit():

        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data.lower()

        if current_user.is_superadmin:
            user.team_organization_id = form.team_organization_id.data

        if form.password.data:
            user.set_password(form.password.data)

        _link_player_to_user(user, form.player_id.data)

        db.session.commit()

        flash("User updated.", "success")
        return redirect(url_for("auth.users", team_id=user.team_organization_id))

    return render_template("auth/user_form.html", form=form, title="Edit User")


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for("auth.users"))

    if not can_manage_team_users(user.team_organization_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    if user.player:
        user.player.user_id = None

    db.session.delete(user)
    db.session.commit()

    flash("User deleted.", "success")
    return redirect(url_for("auth.users", team_id=user.team_organization_id))


# ---------------------------------------
# Profile & Player Linking
# ---------------------------------------

@bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


@bp.route('/link_player', methods=['GET', 'POST'])
@login_required
def link_player():

    available_players = Player.query.filter(
        (Player.user_id == None) | (Player.user_id == current_user.id)
    ).filter_by(active=True).order_by(Player.first_name).all()

    if request.method == 'POST':
        player_id = request.form.get('player_id', type=int)

        if not player_id:
            flash('Please select a player.', 'warning')
            return redirect(url_for('auth.link_player'))

        player = Player.query.get(player_id)

        if not player:
            flash('Invalid player selected.', 'danger')
            return redirect(url_for('auth.link_player'))

        # Unlink previous
        if current_user.player and current_user.player.id != player_id:
            current_user.player.user_id = None

        # Link new
        player.user_id = current_user.id

        db.session.commit()

        flash(f'Linked to player {player.first_name} {player.last_name}.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/link_player.html', players=available_players)