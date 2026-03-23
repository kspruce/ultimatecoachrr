# app/utils.py
import os
from werkzeug.utils import secure_filename
from flask import current_app, flash, redirect, url_for
from PIL import Image
import uuid
from datetime import datetime
from functools import wraps
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('You do not have permission to perform this action.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def coach_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_coach:
            flash('You need coach privileges to access this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def stat_taker_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Admins, coaches, captains, and stat_takers all have access.
        # Players and guests do not.
        if not current_user.is_stat_taker:
            flash('You need at least stat taker privileges to access this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file, folder):
    """Save an uploaded file and return the relative path"""
    if file:
        # Generate unique filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        
        # Create the full path for saving
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Save the file
        file.save(save_path)
        
        # Return only the filename for database storage
        return unique_filename
    return None

def delete_file(relative_path):
    """
    Delete a file given its relative path
    """
    if relative_path:
        absolute_path = os.path.join(current_app.static_folder, relative_path)
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
