# app/routes/playbook.py
from flask import (
    Blueprint, render_template, redirect, url_for, flash, 
    request, jsonify, current_app
)
from flask_login import login_required, current_user
from app import db
from app.models.playbook import Play, Formation, PlayTag
from app.forms.playbook import PlayForm, FormationForm
from werkzeug.utils import secure_filename
import os
import json
from app.utils.storage import store_file, delete_file, get_file_url

bp = Blueprint('playbook', __name__, url_prefix='/playbook')

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
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    form = PlayForm()
    
    if form.validate_on_submit():
        play = Play(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            notes=form.notes.data,
            ultiplay_embed=form.ultiplay_embed.data,
            created_by=current_user.id
        )
        
        if form.formation_id.data and form.formation_id.data > 0:
            play.formation_id = form.formation_id.data
            
        # Handle tags if any are selected
        if form.tags.data:
            for tag_id in form.tags.data:
                tag = PlayTag.query.get(tag_id)
                if tag:
                    play.tags.append(tag)

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
            try:
                # Delete old file if it exists
                if play.s3_key:
                    delete_file(play.s3_key)
                
                # Upload new file
                url, path = store_file(
                    file=form.diagram_file.data,
                    folder='plays',
                    allowed_types=current_app.config['ALLOWED_EXTENSIONS']['image']
                )
                if url:
                    play.diagram_url = url
                    play.s3_key = path
                else:
                    flash('Failed to upload new diagram', 'error')
            except Exception as e:
                current_app.logger.error(f"Error updating play diagram: {str(e)}")
                flash('Error updating diagram', 'error')
        
        db.session.commit()
        flash(f'Play "{play.name}" has been updated!', 'success')
        return redirect(url_for('playbook.view_play', play_id=play.id))
        
    return render_template('playbook/play_form.html', form=form, play=play, title='Edit Play')

@bp.route('/plays/<int:play_id>/delete', methods=['POST'])
@login_required
def delete_play(play_id):
    try:
        play = Play.query.get_or_404(play_id)
        
        # Check permissions
        if play.created_by != current_user.id and not current_user.is_admin:
            return jsonify({
                'success': False,
                'message': 'Permission denied'
            }), 403
        
        # Delete file from storage if exists
        if play.s3_key:
            if not delete_file(play.s3_key):
                current_app.logger.error(f"Failed to delete file: {play.s3_key}")
        
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

# Formation Routes
@bp.route('/formations/add', methods=['GET', 'POST'])
@login_required
def add_formation():
    form = FormationForm()
    if form.validate_on_submit():
        formation = Formation(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            ultiplay_embed=form.ultiplay_embed.data,  # Add this line
            created_by=current_user.id
        )
        
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

@bp.route('/formations/edit/<int:formation_id>', methods=['GET', 'POST'])
@login_required
def edit_formation(formation_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    formation = Formation.query.get_or_404(formation_id)
    form = FormationForm(obj=formation)
    
    if form.validate_on_submit():
        formation.name = form.name.data
        formation.type = form.type.data
        formation.description = form.description.data
        
        # Handle ultiplay embed update
        if form.ultiplay_embed.data:
            formation.ultiplay_embed = form.ultiplay_embed.data
        
        db.session.commit()
        flash(f'Formation "{formation.name}" has been updated!', 'success')
        return redirect(url_for('playbook.index'))
    
    return render_template(
        'playbook/formation_form.html',
        form=form,
        formation=formation,
        title='Edit Formation'
    )

# Also add a delete route for formations
@bp.route('/formations/delete/<int:formation_id>', methods=['POST'])
@login_required
def delete_formation(formation_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    formation = Formation.query.get_or_404(formation_id)
    
    # Check if formation is being used by any plays
    if formation.plays:
        flash('Cannot delete formation that is being used by plays.', 'danger')
        return redirect(url_for('playbook.index'))
    
    name = formation.name
    db.session.delete(formation)
    db.session.commit()
    
    flash(f'Formation "{name}" has been deleted!', 'success')
    return redirect(url_for('playbook.index'))