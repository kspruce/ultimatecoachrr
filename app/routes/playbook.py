# app/routes/playbook.py
from flask import (
    Blueprint, render_template, redirect, url_for, flash, 
    request, jsonify, current_app
)
from flask_login import login_required, current_user
from app import db
from app.models.playbook import Play, Formation, PlayTag
from app.forms.playbook import PlayForm, FormationForm
from app.utils.utils import save_uploaded_file, delete_file
from werkzeug.utils import secure_filename
import os
import json

bp = Blueprint('playbook', __name__, url_prefix='/playbook')

# Helper Functions
def save_diagram(file, folder_type, item_id):
    """Save a diagram file and return the path"""
    if not file:
        return None
    
    try:
        # Create specific folder for plays or formations
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], folder_type, str(item_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        # Return relative path for database storage
        return os.path.join(folder_type, str(item_id), filename)
    except Exception as e:
        current_app.logger.error(f"Error saving diagram: {str(e)}")
        return None

# Main Routes
@bp.route('/')
@login_required
def index():
    """Display playbook overview"""
    offensive_plays = Play.query.filter_by(type='offense').all()
    defensive_plays = Play.query.filter_by(type='defense').all()
    formations = Formation.query.all()
    
    return render_template('playbook/index.html',
                         offensive_plays=offensive_plays,
                         defensive_plays=defensive_plays,
                         formations=formations)

# Play Routes
@bp.route('/plays/add', methods=['GET', 'POST'])
@login_required
def add_play():
    form = PlayForm()
    
    # Populate formation choices
    form.formation_id.choices = [(0, 'None')] + [
        (f.id, f.name) for f in Formation.query.order_by(Formation.name).all()
    ]
    
    # Populate tag choices if you have any
    form.tags.choices = [(t.id, t.name) for t in PlayTag.query.order_by(PlayTag.name).all()]
    
    if form.validate_on_submit():
        play = Play(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            notes=form.notes.data,
            created_by=current_user.id
        )
        
        if form.formation_id.data and form.formation_id.data > 0:
            play.formation_id = form.formation_id.data
            
        # Handle diagram upload
        if form.diagram_file.data:
            diagram_path = save_diagram(form.diagram_file.data, 'plays', play.id)
            if diagram_path:
                play.diagram_url = diagram_path
        
        db.session.add(play)
        db.session.commit()
        
        flash(f'Play "{play.name}" has been created!', 'success')
        return redirect(url_for('playbook.index'))
        
    return render_template('playbook/play_form.html', form=form, title='Add Play')

@bp.route('/plays/<int:play_id>')
@login_required
def view_play(play_id):
    play = Play.query.get_or_404(play_id)
    return render_template('playbook/play_detail.html', play=play)

@bp.route('/plays/<int:play_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_play(play_id):
    play = Play.query.get_or_404(play_id)
    form = PlayForm(obj=play)
    
    # Populate choices as in add_play
    form.formation_id.choices = [(0, 'None')] + [
        (f.id, f.name) for f in Formation.query.order_by(Formation.name).all()
    ]
    form.tags.choices = [(t.id, t.name) for t in PlayTag.query.order_by(PlayTag.name).all()]
    
    if form.validate_on_submit():
        play.name = form.name.data
        play.type = form.type.data
        play.description = form.description.data
        play.notes = form.notes.data
        
        if form.formation_id.data and form.formation_id.data > 0:
            play.formation_id = form.formation_id.data
        else:
            play.formation_id = None
            
        if form.diagram_file.data:
            # Delete old diagram if it exists
            if play.diagram_url:
                old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], play.diagram_url)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            # Save new diagram
            diagram_path = save_diagram(form.diagram_file.data, 'plays', play.id)
            if diagram_path:
                play.diagram_url = diagram_path
        
        db.session.commit()
        flash(f'Play "{play.name}" has been updated!', 'success')
        return redirect(url_for('playbook.view_play', play_id=play.id))
        
    return render_template('playbook/play_form.html', form=form, play=play, title='Edit Play')

@bp.route('/plays/<int:play_id>/delete', methods=['POST'])
@login_required
def delete_play(play_id):
    """Delete a play with CSRF protection"""
    if not request.is_json:
        # If it's a form submission, verify CSRF token
        form = PlayForm()
        if not form.validate():
            flash('CSRF token missing or invalid', 'danger')
            return redirect(url_for('playbook.index'))
    
    try:
        play = Play.query.get_or_404(play_id)
        
        # Check permissions
        if play.created_by != current_user.id and not current_user.is_admin:
            return jsonify({
                'success': False,
                'message': 'Permission denied'
            }), 403
        
        # Delete associated diagram if it exists
        if play.diagram_url:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], play.diagram_url)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        name = play.name
        db.session.delete(play)
        db.session.commit()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': f'Play "{name}" has been deleted!'
            })
        
        flash(f'Play "{name}" has been deleted!', 'success')
        return redirect(url_for('playbook.index'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting play {play_id}: {str(e)}")
        
        if request.is_json:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500
            
        flash(f'Error deleting play: {str(e)}', 'danger')
        return redirect(url_for('playbook.index'))

# Formation Routes (similar structure to Play routes)
@bp.route('/formations/add', methods=['GET', 'POST'])
@login_required
def add_formation():
    form = FormationForm()
    if form.validate_on_submit():
        formation = Formation(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            created_by=current_user.id
        )
        
        if form.diagram_file.data:
            diagram_path = save_diagram(form.diagram_file.data, 'formations', formation.id)
            if diagram_path:
                formation.diagram_url = diagram_path
        
        db.session.add(formation)
        db.session.commit()
        
        flash(f'Formation "{formation.name}" has been created!', 'success')
        return redirect(url_for('playbook.index'))
        
    return render_template('playbook/formation_form.html', form=form, title='Add Formation')

# Error handlers
@bp.errorhandler(404)
def not_found_error(error):
    if request.is_json:
        return jsonify({
            'success': False,
            'message': 'Resource not found'
        }), 404
    return render_template('404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.is_json:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    return render_template('500.html'), 500
