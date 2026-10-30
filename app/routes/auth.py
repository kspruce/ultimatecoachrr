from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, session, g
from urllib.parse import urlparse
from flask_login import login_user, logout_user, current_user, login_required
import logging
import time

from app import csrf, db, limiter, onboarding
from app.models.user import ROLE_ORDER, User
from app.models.player import Player
from app.models.team_membership import TeamMembership
from app.models.team_organization import TeamOrganization, generate_join_code, normalize_join_code
from app.models.team_settings import TeamSettings
from app.models.invite_token import InviteToken
from app.models.site_settings import SiteSettings
from app.models.team_signup_invite import TeamSignupInvite
from app.forms.auth import LoginForm, UserForm
from app.utils.email import email_configured, is_real_email, send_email
from app.utils.password_reset import (COACH_LINK_SECONDS, EMAIL_LINK_SECONDS,
                                      reset_url, user_for_reset_token)
from app.utils.permissions import can_manage_account, can_manage_team_users, can_manage_user, grantable_roles
from app.utils.team_filter import get_current_team_id

# ---------------------------------------
# Setup
# ---------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

MIN_PASSWORD_LENGTH = 8
# The first passwords anyone guessing tries (8+ characters, lower case), plus
# the obvious ones for this site
COMMON_PASSWORDS = frozenset('''
12345678 123456789 1234567890 0123456789 87654321 11111111 00000000 12341234
password password1 password12 password123 passw0rd p@ssword p@ssw0rd qwertyuiop
qwerty123 qwerty12 1q2w3e4r 1qaz2wsx zaq12wsx asdfghjk asdfghjkl iloveyou
sunshine princess football baseball welcome1 welcome123 letmein1 trustno1
superman starwars whatever abc12345 abcd1234 aa123456 changeme computer
liverpool chelsea1 arsenal1 admin123 administrator
ultimate frisbee ultimate1 frisbee1 ultimatefrisbee ultimatecoach
'''.split())

# Rate limits (per visitor IP) on pages that take passwords or create accounts
LOGIN_LIMIT = '10 per minute;60 per hour'
SIGNUP_LIMIT = '10 per hour'
TEAM_SIGNUP_LIMIT = '5 per hour'
RESET_REQUEST_LIMIT = '5 per 15 minutes'

# Tables whose rows belong to the team rather than the person: when the
# user is deleted, the rows move to whoever deleted them instead of being
# lost or losing their author.
_REASSIGN_ON_USER_DELETE = {('player_feedback', 'coach_id')}

# ---------------------------------------
# Internal Helpers
# ---------------------------------------

def _get_managed_team_id():
    """The team whose people are being managed: the current team. A
    superadmin can name another team, which switches to it (so roles and
    linked players on the page are that team's)."""
    if current_user.is_superadmin:
        team_id = request.args.get('team_id', type=int)
        if team_id and team_id != get_current_team_id() and db.session.get(TeamOrganization, team_id):
            session['current_team_id'] = team_id
            g.pop('current_team', None)
    return get_current_team_id()


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


def _populate_role_choices(form):
    """Only offer roles the current user is allowed to give (the form then
    rejects any other role that's posted)."""
    allowed = set(grantable_roles())
    form.role.choices = [(value, label) for value, label in form.role.choices if value in allowed]


def _populate_player_choices(form, team_id):

    players = Player.query.filter_by(
        team_organization_id=team_id,
        active=True
    ).order_by(Player.name).all()

    form.player_id.choices = [(0, "No Player")] + [
        (p.id, f"{p.name} ({p.jersey_number or ''})")
        for p in players
    ]


def _link_player_to_user(user, player_id, team_id):
    """
    Link the user to one player on a team (one player per user per team).
    """
    current = user.player_for(team_id)
    if not player_id or player_id == 0:
        # Unlink existing player if removing
        if current:
            current.user_account = None
        return

    player = db.session.get(Player, player_id)
    if not player or player.team_organization_id != team_id:
        return

    # Unlink from previous user if needed
    if player.user_account and player.user_account is not user:
        flash(f'Player was unlinked from user {player.user_account.username}', 'warning')

    # Unlink user's current player if different (first, as a user has one
    # player per team)
    if current and current.id != player_id:
        current.user_account = None
        db.session.flush()

    player.user_account = user


def _clean_email(raw):
    """Stripped email address, or None when left blank."""
    return (raw or '').strip() or None


def _new_account_errors(username, email, password, confirm):
    """Problems with the details someone typed to create an account."""
    errors = []
    if not username or len(username) < 3:
        errors.append('Username must be at least 3 characters.')
    elif len(username) > 64:
        errors.append('Username must be 64 characters or fewer.')
    elif User.query.filter_by(username=username).first():
        errors.append('That username is already taken — please choose another.')
    if email:
        if not is_real_email(email):
            errors.append('That email address doesn\'t look right.')
        elif User.query.filter_by(email=email).first():
            errors.append('That email address is already registered. If it\'s yours, log in '
                          'instead: one account can be on several teams.')
    errors.extend(_password_errors(password, confirm))
    return errors


def _password_errors(password, confirm):
    errors = []
    if len(password or '') < MIN_PASSWORD_LENGTH:
        errors.append(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
    elif password.lower() in COMMON_PASSWORDS or len(set(password)) < 3:
        errors.append('That password is too easy to guess. Try a few words together.')
    if password != confirm:
        errors.append('Passwords do not match.')
    return errors


def _flash_all(errors):
    for e in errors:
        flash(e, 'danger')


def _detach_user_rows(user_id):
    """Clear every reference to a user so they can be deleted: optional links
    are emptied, team records they wrote move to the person deleting them,
    and their own personal records (workout logs, preferences, ...) go."""
    for table in reversed(db.metadata.sorted_tables):
        for fk in table.foreign_keys:
            if fk.column.table.name != 'user' or table.name == 'user':
                continue
            column = fk.parent
            if (table.name, column.name) in _REASSIGN_ON_USER_DELETE:
                values = {column.name: current_user.id}
            elif column.nullable:
                values = {column.name: None}
            else:
                db.session.execute(table.delete().where(column == user_id))
                continue
            db.session.execute(table.update().where(column == user_id).values(**values))


def _unlinked_players_exist(team_id):
    return Player.query.filter_by(team_organization_id=team_id, active=True,
                                  user_id=None).first() is not None


def _team_managed_for(user):
    """The team whose role and player for `user` are being managed: the
    current team, or (for a superadmin acting on someone who isn't on it)
    their home team."""
    team_id = get_current_team_id()
    if not user.is_member_of(team_id) and user.team_organization_id:
        return user.team_organization_id
    return team_id


def _switch_to(team_id):
    session['current_team_id'] = team_id
    g.pop('current_team', None)


def _after_joining(user, team_id):
    """Where a new team member goes after joining: pick their name from the
    roster if they aren't linked to a player there yet."""
    if not user.player_for(team_id) and _unlinked_players_exist(team_id):
        flash('Pick your name from the roster so your stats and RSVPs are linked to you.', 'info')
        return redirect(url_for('auth.link_player'))
    return redirect(url_for('main.index'))


# ---------------------------------------
# Authentication Routes
# ---------------------------------------

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(LOGIN_LIMIT, methods=['POST'])
def login():
    try:
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))

        form = LoginForm()

        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()

            logger.info(f"Login attempt for user: {form.username.data}")

            if user is None or not user.password_hash or not user.check_password(form.password.data):
                logger.warning(f"Failed login attempt for user: {form.username.data}")
                flash('Invalid username or password', 'danger')
                return redirect(url_for('auth.login'))

            next_page = request.args.get('next')
            # Only paths on this site (browsers read //x and /\x as other sites)
            if (not next_page or not next_page.startswith('/') or next_page.startswith(('//', '/\\'))
                    or urlparse(next_page).netloc):
                next_page = url_for('main.index')

            if user.two_factor_enabled:
                # Password was right; the code from their app comes next
                session['tfa_pending'] = {'user': user.get_id(), 'remember': bool(form.remember_me.data),
                                          'next': next_page, 'at': time.time(), 'tries': 0}
                return redirect(url_for('auth.two_factor'))

            login_user(user, remember=form.remember_me.data)
            return redirect(next_page)

        return render_template('auth/login.html', title='Sign In', form=form)

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        flash('An error occurred during login.', 'danger')
        return redirect(url_for('auth.login'))


@bp.route('/register')
def register():
    """Getting started: join an existing team with a code, or register a new
    team. (Accounts always belong to a team, so there's no team-less sign-up.)"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return render_template('auth/get_started.html', title='Get Started',
                           team_signup_open=SiteSettings.get().open_team_registration)


@bp.route('/logout', methods=['GET', 'POST'])
@csrf.exempt  # a stale page must still log out; SameSite cookies stop other sites
def logout():
    # Only a POST logs out, so a link or image on another site can't
    if request.method == 'POST':
        logout_user()
    return redirect(url_for('main.index'))


# ---------------------------------------
# User Management
# ---------------------------------------

@bp.route('/users')
@login_required
def users():

    team_id = _get_managed_team_id()

    # Superadmin can view unassigned users (team_id=0 means "no team")
    viewing_unassigned = (current_user.is_superadmin and
                          request.args.get('team_id') == '0')

    if not viewing_unassigned and not team_id:
        flash("Select a team first.", "warning")
        return redirect(url_for("main.index"))

    if not viewing_unassigned and not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    if current_user.is_superadmin:
        teams = TeamOrganization.query.order_by(TeamOrganization.name).all()
    else:
        teams = [TeamOrganization.query.get(team_id)]

    if viewing_unassigned:
        users = User.query.filter(~User.memberships.any()).order_by(User.username).all()
        current_team = None
    else:
        users = User.query.filter(User.memberships.any(TeamMembership.team_organization_id == team_id)
                                  ).order_by(User.username).all()
        current_team = db.session.get(TeamOrganization, team_id)

    return render_template(
        "auth/users.html",
        users=users,
        teams=teams,
        current_team=current_team,
        viewing_unassigned=viewing_unassigned,
        is_superadmin=current_user.is_superadmin,
        manageable_ids={u.id for u in users if can_manage_user(u)},
        account_ids={u.id for u in users if can_manage_account(u)},
        email_enabled=email_configured(),
        member_status=onboarding.member_status(users),
        roster_signup=onboarding.roster_signup(current_team.id) if current_team else None,
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
    _populate_role_choices(form)
    _populate_player_choices(form, team_id)
    if request.method == 'GET':
        form.role.data = 'player'

    if form.validate_on_submit():

        user = User(
            username=form.username.data.strip(),
            email=_clean_email(form.email.data),
            role=form.role.data,
            team_organization_id=form.team_organization_id.data,
            is_superadmin=False
        )

        if form.password.data:
            user.set_password(form.password.data)

        db.session.add(user)
        db.session.flush()

        _link_player_to_user(user, form.player_id.data, user.team_organization_id)

        db.session.commit()

        if form.password.data:
            flash(f"User {user.username} created.", "success")
        else:
            flash(f"User {user.username} created. They have no password yet: use "
                  "Reset link to send them a link to set one.", "success")
        return redirect(url_for("auth.users", team_id=user.team_organization_id))

    return render_template("auth/user_form.html", form=form, title="Add User")


@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):

    user = User.query.get_or_404(user_id)
    team_id = get_current_team_id()

    if user.id == current_user.id and not current_user.is_superadmin:
        return redirect(url_for('auth.account'))

    if not can_manage_user(user):
        flash("You can only edit people whose role is below yours.", "danger")
        return redirect(url_for("auth.users") if can_manage_team_users(team_id)
                        else url_for("main.index"))

    team_id = _team_managed_for(user)

    # Someone also on teams this person doesn't run: only their role and
    # player here can change, not the login they share with those teams
    account_editable = can_manage_account(user)

    form = UserForm(
        original_username=user.username,
        original_email=user.email
    )
    if request.method == 'POST' and not account_editable:
        form.username.data, form.email.data = user.username, user.email
        form.password.data = form.confirm_password.data = ''

    # Populate choices but only set defaults on GET request
    _populate_team_choices(form, team_id, set_default=(request.method == 'GET'))
    _populate_role_choices(form)
    _populate_player_choices(form, team_id)

    if request.method == "GET":
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role_in(team_id)
        form.team_organization_id.data = team_id
        player = user.player_for(team_id)
        form.player_id.data = player.id if player else 0

    if form.validate_on_submit():

        if account_editable:
            user.username = form.username.data.strip()
            user.email = _clean_email(form.email.data)
            if form.password.data:
                user.set_password(form.password.data)

        old_role = user.role_in(team_id) if user.is_member_of(team_id) else None
        new_role = form.role.data.lower()
        promoted = ROLE_ORDER.get(new_role, 0) > ROLE_ORDER.get(old_role, 0)

        new_team_id = form.team_organization_id.data
        if current_user.is_superadmin and new_team_id and new_team_id != team_id:
            # Move them from this team to the chosen one
            user.leave_team(team_id)
            team_id = new_team_id
        if not user.is_member_of(team_id):
            user.join_team(team_id, new_role)
        user.set_role_in(team_id, new_role)

        _link_player_to_user(user, form.player_id.data, team_id)

        db.session.commit()

        flash("User updated.", "success")
        if promoted and new_role in onboarding.ROLES:
            flash(f"{user.username} will see a short welcome to their new role next time "
                  "they open the dashboard.", "info")
        return redirect(url_for("auth.users", team_id=team_id))

    other_teams = [m.team_organization.name for m in user.memberships if m.team_organization_id != team_id]
    return render_template("auth/user_form.html", form=form, title="Edit User",
                           account_editable=account_editable, other_teams=other_teams)


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):

    user = User.query.get_or_404(user_id)
    team_id = _team_managed_for(user)

    if user.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for("auth.users"))

    if not can_manage_user(user):
        flash("You can only delete people whose role is below yours.", "danger")
        return redirect(url_for("main.index"))

    if any(m.team_organization_id != team_id for m in user.memberships):
        # Also on other teams: take them off this one and keep the account
        user.leave_team(team_id)
        db.session.commit()
        flash(f"{user.username} was removed from this team. Their account stays, "
              "because they're also on another team.", "success")
        return redirect(url_for("auth.users", team_id=team_id))

    try:
        _detach_user_rows(user.id)
        db.session.delete(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deleting user {user_id}: {e}', exc_info=True)
        flash('That user could not be deleted. Change their role to Guest instead.', 'danger')
        return redirect(url_for("auth.users", team_id=team_id))

    flash("User deleted.", "success")
    return redirect(url_for("auth.users", team_id=team_id))


@bp.route('/users/<int:user_id>/reset-link', methods=['POST'])
@login_required
def create_reset_link(user_id):
    """A coach makes a password-reset link for one of their players (for
    players without email, or when email isn't set up). Also emailed to the
    player when possible."""
    user = User.query.get_or_404(user_id)
    if not can_manage_account(user):
        flash("You can only reset passwords for people whose role is below yours on every "
              "team they're on.", "danger")
        return redirect(url_for("main.index"))

    link = reset_url(user, COACH_LINK_SECONDS)
    emailed = send_email(
        user.email, 'Set your Ultimate Coach password',
        f'Hi {user.username},\n\n'
        f'{current_user.username} sent you a link to set a new password for '
        f'Ultimate Coach:\n\n{link}\n\n'
        f'The link works once and expires in {COACH_LINK_SECONDS // 86400} days.\n')
    return render_template('auth/reset_link.html', title='Password reset link', user=user,
                           link=link, days=COACH_LINK_SECONDS // 86400, emailed=emailed)


# ---------------------------------------
# Team join link
# ---------------------------------------

@bp.route('/join-link', methods=['POST'])
@login_required
def manage_join_link():
    """Coach turns the team's join link on or off, or replaces it with a new
    one (which stops the old link working)."""
    team_id = _get_managed_team_id()
    if not team_id or not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    team = TeamOrganization.query.get_or_404(team_id)
    action = request.form.get('action')
    if action == 'enable':
        team.join_code = team.join_code or generate_join_code()
        team.join_enabled = True
        flash('Join link is on. Share it with your players.', 'success')
    elif action == 'disable':
        team.join_enabled = False
        flash('Join link is off. Nobody new can join with it.', 'info')
    elif action == 'regenerate':
        team.join_code = generate_join_code()
        team.join_enabled = True
        flash('New join link created. The old link no longer works.', 'success')
    db.session.commit()
    return redirect(url_for('auth.users', team_id=team.id))


@bp.route('/remind-unjoined', methods=['POST'])
@login_required
def remind_unjoined():
    """Coach chases the roster players who haven't made an account: each one
    with an email gets their own invite link, and the team's Discord gets a
    note naming who's left."""
    team_id = _get_managed_team_id()
    if not team_id or not can_manage_team_users(team_id):
        flash("You do not have permission.", "danger")
        return redirect(url_for("main.index"))

    team = TeamOrganization.query.get_or_404(team_id)
    result = onboarding.remind_unjoined(team, current_user)
    if not result['waiting']:
        flash('Everyone on the roster has an account.', 'info')
        return redirect(url_for('auth.users', team_id=team.id, _anchor='signup'))
    emailed = result['emailed']
    sentences = []
    if emailed:
        sentences.append(f"Emailed {emailed} player{'s' if emailed != 1 else ''} their invite link.")
    if result['discord']:
        sentences.append("Posted who's left to your Discord.")
    went = bool(sentences)
    if not went:
        sentences.append('Nobody was sent anything.')
    message = ' '.join(sentences)
    if result['recent']:
        message += f" {result['recent']} had an invite in the last few days, so weren't sent another."
    if result['no_email']:
        message += (f" No email for {', '.join(result['no_email'])}: add one on their roster page, "
                    "or copy their invite link from the roster and send it yourself.")
    flash(message, 'success' if went else 'warning')
    return redirect(url_for('auth.users', team_id=team.id, _anchor='signup'))


@bp.route('/join', methods=['GET', 'POST'])
@limiter.limit(SIGNUP_LIMIT, methods=['POST'])
def join():
    """Enter a team's join code."""
    if request.method == 'POST':
        code = normalize_join_code(request.form.get('code'))
        team = TeamOrganization.query.filter_by(join_code=code, join_enabled=True).first() if code else None
        if team:
            return redirect(url_for('auth.join_team', code=code))
        flash('That join code isn\'t valid. Check it with your coach.', 'danger')
    return render_template('auth/join.html', title='Join a Team', team=None, form_data={})


@bp.route('/join/<code>', methods=['GET', 'POST'])
@limiter.limit(SIGNUP_LIMIT, methods=['POST'])
def join_team(code):
    """Public: a player creates their account on the team the link is for."""
    code = normalize_join_code(code)
    team = TeamOrganization.query.filter_by(join_code=code, join_enabled=True).first()
    if not team:
        flash('This join link isn\'t valid any more. Ask your coach for the current one.', 'warning')
        return redirect(url_for('auth.join'))

    if current_user.is_authenticated:
        # Already have an account: add this team to it (after they confirm,
        # so a link someone else planted can't sign them up)
        if current_user.is_member_of(team.id):
            _switch_to(team.id)
            return redirect(url_for('main.index'))
        if request.method == 'POST':
            user = current_user._get_current_object()
            user.join_team(team.id, 'player')
            db.session.commit()
            _switch_to(team.id)
            flash(f'Welcome to {team.name}! Switch between your teams from the menu.', 'success')
            return _after_joining(user, team.id)
        return render_template('auth/join_existing.html', title=f'Join {team.name}', team=team,
                               action=url_for('auth.join_team', code=code))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = _clean_email(request.form.get('email'))
        password = request.form.get('password', '')
        errors = _new_account_errors(username, email, password, request.form.get('confirm_password', ''))
        if errors:
            _flash_all(errors)
            return render_template('auth/join.html', title=f'Join {team.name}', team=team,
                                   code=code, form_data=request.form)

        user = User(username=username, email=email, role='player', is_superadmin=False,
                    team_organization_id=team.id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(f'Welcome to {team.name}, {username}!', 'success')
        return _after_joining(user, team.id)

    return render_template('auth/join.html', title=f'Join {team.name}', team=team,
                           code=code, form_data={},
                           login_next=url_for('auth.join_team', code=code))


# ---------------------------------------
# Passwords & Account Settings
# ---------------------------------------

@bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit(RESET_REQUEST_LIMIT, methods=['POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('auth.account'))

    can_email = email_configured()
    if request.method == 'POST' and can_email:
        identifier = request.form.get('identifier', '').strip()
        user = None
        if identifier:
            user = (User.query.filter_by(username=identifier).first()
                    or User.query.filter(db.func.lower(User.email) == identifier.lower()).first())
        if user and is_real_email(user.email):
            link = reset_url(user, EMAIL_LINK_SECONDS)
            send_email(
                user.email, 'Reset your Ultimate Coach password',
                f'Hi {user.username},\n\n'
                f'Someone (hopefully you) asked to reset your Ultimate Coach password. '
                f'Use this link to choose a new one:\n\n{link}\n\n'
                f'It works once and expires in {EMAIL_LINK_SECONDS // 60} minutes. '
                f'If you didn\'t ask for this, you can ignore this email.\n')
        # Same answer whether or not the account exists, so this page can't
        # be used to find out who has an account
        flash('If that account has an email address, a reset link is on its way. '
              'Check your spam folder too. No email on your account? Ask your coach '
              'for a reset link.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', title='Forgot Password', can_email=can_email)


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit(SIGNUP_LIMIT, methods=['POST'])
def reset_password(token):
    user = user_for_reset_token(token)
    if user is None:
        flash('That reset link has expired or was already used. Ask for a new one.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        errors = _password_errors(password, request.form.get('confirm_password', ''))
        if errors:
            _flash_all(errors)
        else:
            user.set_password(password)
            db.session.commit()
            logout_user()
            flash('Your password has been changed. Log in with your new password.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', title='Choose a New Password', user=user)


@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """Change your own email address, password or email preferences."""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'notifications':  # not sensitive: no password needed
            current_user.email_event_updates = bool(request.form.get('email_event_updates'))
            db.session.commit()
            flash('Email preferences saved.', 'success')
            return redirect(url_for('auth.account'))
        current_password = request.form.get('current_password', '')
        if current_user.password_hash and not current_user.check_password(current_password):
            flash('Your current password is incorrect.', 'danger')
            return redirect(url_for('auth.account'))

        if action == 'email':
            email = _clean_email(request.form.get('email'))
            if email and not is_real_email(email):
                flash('That email address doesn\'t look right.', 'danger')
            elif email and User.query.filter(User.email == email, User.id != current_user.id).first():
                flash('That email address is already registered to another account.', 'danger')
            else:
                current_user.email = email
                db.session.commit()
                flash('Email address saved.' if email else 'Email address removed.', 'success')
        elif action == 'password':
            password = request.form.get('password', '')
            errors = _password_errors(password, request.form.get('confirm_password', ''))
            if errors:
                _flash_all(errors)
            else:
                current_user.set_password(password)
                db.session.commit()
                # Signs out other devices; keep this one logged in
                login_user(current_user._get_current_object(),
                           remember=current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')
                           in request.cookies)
                flash('Password changed. Any other devices have been signed out.', 'success')
        return redirect(url_for('auth.account'))

    from app.utils.two_factor import recovery_codes_left, required_for
    return render_template('auth/account.html', title='Account Settings',
                           recovery_left=recovery_codes_left(current_user),
                           tfa_required=required_for(current_user),
                           email_enabled=email_configured(),
                           has_real_email=is_real_email(current_user.email))


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

    team_id = get_current_team_id()
    available_players = Player.query.filter(
        (Player.user_id == None) | (Player.user_id == current_user.id)
    ).filter_by(active=True, team_organization_id=team_id).order_by(Player.name).all()

    if request.method == 'POST':
        player_id = request.form.get('player_id', type=int)

        if not player_id:
            flash('Please select a player.', 'warning')
            return redirect(url_for('auth.link_player'))

        player = next((p for p in available_players if p.id == player_id), None)

        if not player:
            flash('Invalid player selected.', 'danger')
            return redirect(url_for('auth.link_player'))

        # Unlink previous (first, as a user has one player per team)
        if current_user.player and current_user.player.id != player_id:
            current_user.player.user_account = None
            db.session.flush()

        # Link new
        player.user_account = current_user._get_current_object()

        db.session.commit()

        flash(f'Linked to player {player.name}.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/link_player.html', players=available_players)


# ─────────────────────────────────────────────────────────────
# Player Invite Links
# ─────────────────────────────────────────────────────────────

@bp.route('/invite/create/<int:player_id>', methods=['POST'])
@login_required
def create_invite(player_id):
    """AJAX: create (or refresh) an invite token for a player and return the link."""
    if not current_user.is_coach:
        return jsonify({'error': 'Permission denied'}), 403

    team_id = get_current_team_id()
    player = Player.query.filter_by(id=player_id, team_organization_id=team_id).first_or_404()

    if player.user_account:
        return jsonify({'error': 'Player already has an account'}), 400

    # Invalidate any existing unused tokens for this player
    existing = InviteToken.query.filter_by(player_id=player_id, used_at=None).all()
    for t in existing:
        db.session.delete(t)

    invite = InviteToken.create(
        player_id=player.id,
        team_id=team_id,
        created_by_id=current_user.id,
    )
    db.session.add(invite)
    db.session.commit()

    link = url_for('auth.accept_invite', token=invite.token, _external=True)
    return jsonify({'link': link, 'expires_days': 7})


@bp.route('/invite/accept/<token>', methods=['GET', 'POST'])
@limiter.limit(SIGNUP_LIMIT, methods=['POST'])
def accept_invite(token):
    """Public: player follows invite link and sets up their account."""
    invite = InviteToken.query.filter_by(token=token).first_or_404()

    if not invite.is_valid:
        reason = 'already been used' if invite.is_used else 'expired'
        flash(f'This invite link has {reason}. Ask your coach to send a new one.', 'warning')
        return redirect(url_for('auth.login'))

    if current_user.is_authenticated:
        return _accept_invite_signed_in(invite)

    player_email = invite.player.email if invite.player and is_real_email(invite.player.email) else None
    if player_email and User.query.filter_by(email=player_email).first():
        player_email = None  # already used by another account

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = _clean_email(request.form.get('email'))
        password = request.form.get('password', '')
        errors = _new_account_errors(username, email, password, request.form.get('confirm_password', ''))

        if errors:
            _flash_all(errors)
            return render_template('auth/accept_invite.html', invite=invite, username=username,
                                   email=email or '', min_password=MIN_PASSWORD_LENGTH)

        # Create the user account
        user = User(
            username=username,
            email=email,
            role='player',
            is_superadmin=False,
            team_organization_id=invite.team_organization_id,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Link to player profile
        if invite.player:
            invite.player.user_id = user.id

        # Mark invite as used
        invite.used_at = datetime.utcnow()
        invite.used_by_user_id = user.id

        db.session.commit()

        login_user(user)
        flash(f'Welcome to Ultimate Coach, {username}! Your account is all set.', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/accept_invite.html', invite=invite, username='',
                           email=player_email or '', min_password=MIN_PASSWORD_LENGTH,
                           login_next=url_for('auth.accept_invite', token=token))


def _accept_invite_signed_in(invite):
    """Someone with an account follows an invite: add the team (and the
    player it's for) to their account once they confirm."""
    user = current_user._get_current_object()
    team_id = invite.team_organization_id
    player = invite.player
    linked_here = user.player_for(team_id)

    if player and player.user_account is not None and player.user_account is not user:
        flash('That player is already linked to another account. Ask your coach for help.', 'warning')
        return redirect(url_for('main.index'))
    if player and linked_here and linked_here is not player:
        flash(f'Your account is already linked to {linked_here.name} on {invite.team.name}. '
              'Ask your coach if that\'s wrong.', 'warning')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        user.join_team(team_id, 'player')
        if player:
            player.user_account = user
        invite.used_at = datetime.utcnow()
        invite.used_by_user_id = user.id
        db.session.commit()
        _switch_to(team_id)
        flash(f'{invite.team.name} has been added to your account. '
              'Switch between your teams from the menu.', 'success')
        return _after_joining(user, team_id)

    return render_template('auth/join_existing.html', title=f'Join {invite.team.name}',
                           team=invite.team, player=player,
                           action=url_for('auth.accept_invite', token=invite.token))


# ─────────────────────────────────────────────────────────────
# Team Self-Registration
# ─────────────────────────────────────────────────────────────

@bp.route('/register-team', methods=['GET', 'POST'])
@limiter.limit(TEAM_SIGNUP_LIMIT, methods=['POST'])
def register_team():
    """Public: a new club registers their team. Needs a sign-up link from a
    superadmin, unless a superadmin has opened sign-up to everyone."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    token = request.values.get('invite', '').strip()
    signup_invite = TeamSignupInvite.find_valid(token)
    if token and not signup_invite:
        flash('This team sign-up link has expired or was already used. '
              'Ask for a new one.', 'warning')
    is_open = SiteSettings.get().open_team_registration
    if not (is_open or signup_invite):
        return render_template('auth/register_team.html', closed=True, form_data={})

    def form_page(form_data):
        return render_template('auth/register_team.html', closed=False, invite_token=token if signup_invite else '',
                               form_data=form_data, min_password=MIN_PASSWORD_LENGTH)

    if request.method == 'POST':
        team_name  = request.form.get('team_name', '').strip()
        username   = request.form.get('username', '').strip()
        email      = _clean_email(request.form.get('email'))
        password   = request.form.get('password', '')

        errors = []
        if not team_name:
            errors.append('Team name is required.')
        elif len(team_name) > 100:
            errors.append('Team name must be 100 characters or fewer.')
        elif TeamOrganization.query.filter(
            db.func.lower(TeamOrganization.name) == team_name.lower()
        ).first():
            errors.append(f'A team called "{team_name}" already exists.')
        errors.extend(_new_account_errors(username, email, password,
                                          request.form.get('confirm_password', '')))

        if errors:
            _flash_all(errors)
            return form_page(request.form)

        # Create team
        slug = team_name.lower().replace(' ', '-')
        # Ensure unique slug
        base_slug, counter = slug, 1
        while TeamOrganization.query.filter_by(slug=slug).first():
            slug = f'{base_slug}-{counter}'
            counter += 1

        team = TeamOrganization(name=team_name, slug=slug)
        db.session.add(team)
        db.session.flush()

        # Create team settings with all features on
        settings = TeamSettings(team_id=team.id)
        db.session.add(settings)

        # The person who registers the team is its team admin, so they can
        # manage everyone they add, coaches included. (Team admin powers are
        # limited to their own team; site-wide tools are superadmin only.)
        user = User(
            username=username,
            email=email,
            role='admin',
            is_superadmin=False,
            team_organization_id=team.id,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if signup_invite:
            signup_invite.used_at = datetime.utcnow()
            signup_invite.used_by_user_id = user.id
            signup_invite.team_organization_id = team.id
        db.session.commit()

        _notify_admins_of_new_team(team, user, signup_invite)

        login_user(user)
        flash(f'Welcome! Your team "{team_name}" has been created. '
              'Start by importing your roster below.', 'success')
        return redirect(url_for('team.bulk_import'))

    return form_page({'email': signup_invite.email if signup_invite and signup_invite.email else ''})


def _notify_admins_of_new_team(team, user, signup_invite):
    """Let the site owner know a team signed up (when email is set up)."""
    how = (f'sign-up link "{signup_invite.note or signup_invite.email or signup_invite.id}"'
           if signup_invite else 'open registration')
    for admin_email in current_app.config.get('ADMINS', []):
        send_email(admin_email, f'New team on Ultimate Coach: {team.name}',
                   f'{team.name} just registered via {how}.\n\n'
                   f'Team admin: {user.username} ({user.email or "no email"})\n\n'
                   f'Manage teams: {url_for("team_organization.signups", _external=True)}\n')



# ---------------------------------------
# Two-step sign-in (superadmins)
# ---------------------------------------

TWO_FACTOR_SECONDS = 5 * 60
TWO_FACTOR_TRIES = 5


@bp.route('/two-factor', methods=['GET', 'POST'])
@limiter.limit(LOGIN_LIMIT, methods=['POST'])
def two_factor():
    """Second step of logging in: a code from the authenticator app, or a
    recovery code."""
    from app.models.user import load_user
    from app.utils import two_factor as tf
    pending = session.get('tfa_pending')
    user = load_user(pending['user']) if pending else None
    if user is None or time.time() - pending['at'] > TWO_FACTOR_SECONDS:
        session.pop('tfa_pending', None)
        flash('Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code', '')
        used_recovery = False
        ok = tf.verify_code(user, code)
        if not ok and tf.use_recovery_code(user, code):
            ok = used_recovery = True
        if ok:
            db.session.commit()
            session.pop('tfa_pending', None)
            login_user(user, remember=pending['remember'])
            if used_recovery:
                flash(f'Recovery code used: {tf.recovery_codes_left(user)} left. '
                      'If you lost your phone, set up your authenticator again from Account Settings.',
                      'warning')
            return redirect(pending['next'])
        pending['tries'] += 1
        session['tfa_pending'] = pending
        logger.warning(f'Wrong two-step code for user {user.id} (try {pending["tries"]})')
        if pending['tries'] >= TWO_FACTOR_TRIES:
            session.pop('tfa_pending', None)
            flash('Too many wrong codes. Log in again.', 'danger')
            return redirect(url_for('auth.login'))
        flash('That code didn\'t work. Check the time on your phone is right and try the newest code.',
              'danger')
    return render_template('auth/two_factor.html', title='Two-step sign-in', user=user)


@bp.route('/two-factor/setup', methods=['GET', 'POST'])
@login_required
def two_factor_setup():
    """Scan a QR code into an authenticator app and confirm with a code.
    Replacing an existing one needs the password too."""
    from app.utils import two_factor as tf
    user = current_user._get_current_object()
    if request.method == 'POST':
        secret = session.get('tfa_setup_secret')
        if not secret:
            return redirect(url_for('auth.two_factor_setup'))
        if user.two_factor_enabled and not user.check_password(request.form.get('password', '')):
            flash('Your password was incorrect.', 'danger')
        elif tf.matching_step(secret, request.form.get('code', '')) is None:
            flash('That code didn\'t match. Type the 6-digit code your app shows now.', 'danger')
        else:
            codes = tf.enable(user, secret)
            user.totp_last_step = tf.matching_step(secret, request.form.get('code', ''))
            db.session.commit()
            session.pop('tfa_setup_secret', None)
            login_user(user)  # the old session no longer matches; keep this one
            logger.info(f'Two-step sign-in set up for user {user.id}')
            return render_template('auth/recovery_codes.html', title='Recovery codes', codes=codes)
    else:
        session['tfa_setup_secret'] = tf.new_secret()
    secret = session['tfa_setup_secret']
    uri = tf.provisioning_uri(user, secret)
    return render_template('auth/two_factor_setup.html', title='Set up two-step sign-in',
                           secret=secret, qr=tf.qr_data_uri(uri))


@bp.route('/two-factor/recovery-codes', methods=['POST'])
@login_required
def new_recovery_codes():
    """Replace the recovery codes (the old ones stop working)."""
    from app.utils import two_factor as tf
    if not current_user.two_factor_enabled:
        return redirect(url_for('auth.account'))
    if not current_user.check_password(request.form.get('password', '')):
        flash('Your password was incorrect.', 'danger')
        return redirect(url_for('auth.account'))
    codes, current_user.totp_recovery_codes = tf.new_recovery_codes()
    db.session.commit()
    return render_template('auth/recovery_codes.html', title='Recovery codes', codes=codes)


@bp.route('/two-factor/disable', methods=['POST'])
@login_required
def disable_two_factor():
    """Turn it off again, while the site doesn't require it."""
    from app.utils import two_factor as tf
    user = current_user._get_current_object()
    if tf.required_for(user):
        flash('Two-step sign-in is required for superadmins on this site.', 'warning')
    elif not user.check_password(request.form.get('password', '')):
        flash('Your password was incorrect.', 'danger')
    else:
        tf.disable(user)
        db.session.commit()
        login_user(user)  # other devices are signed out; keep this one
        flash('Two-step sign-in is off. Logging in needs just your password.', 'success')
    return redirect(url_for('auth.account'))


@bp.before_app_request
def require_two_factor():
    """When the site requires it, superadmins set up two-step sign-in
    before anything else."""
    from app.utils import two_factor as tf
    if (not current_user.is_authenticated or current_user.two_factor_enabled
            or not tf.required_for(current_user)):
        return None
    if request.endpoint in ('auth.two_factor_setup', 'auth.logout', 'static', 'main.csp_report'):
        return None
    flash('This site requires two-step sign-in for superadmins. Set it up to continue.', 'warning')
    return redirect(url_for('auth.two_factor_setup'))
