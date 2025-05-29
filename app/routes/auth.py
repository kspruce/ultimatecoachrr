from flask import Blueprint, render_template, redirect, url_for, flash, request
from urllib.parse import urlparse
from app import db
from app.models.user import User
from app.forms.auth import LoginForm, RegistrationForm
from flask_login import login_user, logout_user, current_user, login_required
import logging
from app.models.player import Player
from app.forms.auth import UserForm






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
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    users = User.query.all()
    return render_template('auth/users.html', users=users)

@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    form = UserForm()
    
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data
        )
        
        if form.password.data:
            user.set_password(form.password.data)
        
        db.session.add(user)
        
        # Link to player if selected
        if form.player_id.data > 0:
            player = Player.query.get(form.player_id.data)
            if player:
                player.user_id = user.id
        
        db.session.commit()
        
        flash(f'User {user.username} has been created!', 'success')
        return redirect(url_for('auth.users'))
    
    return render_template('auth/user_form.html', form=form, title='Add User')

@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    user = User.query.get_or_404(user_id)
    form = UserForm(original_username=user.username)
    
    if request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role
        if user.player:
            form.player_id.data = user.player.id
    
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        # Update player link
        if user.player and (form.player_id.data == 0 or form.player_id.data != user.player.id):
            # Unlink current player
            user.player.user_id = None
        
        if form.player_id.data > 0:
            player = Player.query.get(form.player_id.data)
            if player:
                # If player is already linked to another user, unlink it
                if player.user_id and player.user_id != user.id:
                    other_user = User.query.get(player.user_id)
                    if other_user:
                        flash(f'Player was unlinked from user {other_user.username}', 'warning')
                
                player.user_id = user.id
        
        db.session.commit()
        
        flash(f'User {user.username} has been updated!', 'success')
        return redirect(url_for('auth.users'))
    
    return render_template('auth/user_form.html', form=form, user=user, title='Edit User')

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('auth.users'))
    
    # Unlink any associated player
    if user.player:
        user.player.user_id = None
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {user.username} has been deleted!', 'success')
    return redirect(url_for('auth.users'))

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
    
    return render_template('auth/link_player.html', players=available_players)
