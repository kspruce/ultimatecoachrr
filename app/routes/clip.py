from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from app import db
from app.models import Clip, ClipTag, ClipAnnotation 
from app.models.game import Game
from app.models.point import Point
from app.models.player import Player
from app.models import ClipAnnotation 
from app.forms.annotation import AnnotationForm
from app.forms.clip import ClipForm, ClipTagForm, ClipFilterForm
import re
from app.utils.utils import admin_required

bp = Blueprint('clip', __name__, url_prefix='/clips')

@bp.route('/')
@login_required
def index():
    form = ClipFilterForm()
    delete_form = FlaskForm()

    # Get filter parameters
    game_id = request.args.get('game_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    player_id = request.args.get('player_id', type=int)

    # Build query based on filters
    query = Clip.query

    if game_id:
        query = query.filter(Clip.game_id == game_id)
    if tag_id:
        query = query.filter(Clip.tags.any(ClipTag.id == tag_id))
    if player_id:
        query = query.filter(Clip.players.any(Player.id == player_id))

    # Get clips and sort by creation date (newest first)
    clips = query.order_by(Clip.created_at.desc()).all()

    return render_template('clip/index.html', 
                         clips=clips, 
                         form=form, 
                         delete_form=delete_form)

@bp.route('/game/<int:game_id>')
@login_required
def game_clips(game_id):
    game = Game.query.get_or_404(game_id)
    clips = Clip.query.filter_by(game_id=game_id).order_by(Clip.created_at.desc()).all()
    return render_template('clip/game_clips.html', game=game, clips=clips)

@bp.route('/point/<int:point_id>')
@login_required
def point_clips(point_id):
    point = Point.query.get_or_404(point_id)
    clips = Clip.query.filter_by(point_id=point_id).order_by(Clip.created_at.desc()).all()
    return render_template('clip/point_clips.html', point=point, clips=clips)



@bp.route('/add_clip', methods=['GET', 'POST'])
@login_required
@admin_required
def add_clip():
    form = ClipForm()
    if form.validate_on_submit():
        clip = Clip(
            title=form.title.data,
            video_source=form.video_source.data,
            youtube_link=form.youtube_link.data,
            game_id=form.game_id.data if form.game_id.data else None,
            point_id=form.point_id.data if form.point_id.data else None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            description=form.description.data
        )

        # Add tags and players using the new relationship pattern
        if form.tags.data:
            tags = ClipTag.query.filter(ClipTag.id.in_(form.tags.data)).all()
            clip.tags = tags

        if form.players.data:
            players = Player.query.filter(Player.id.in_(form.players.data)).all()
            clip.players = players

        db.session.add(clip)
        db.session.commit()

        flash(f'Clip "{clip.title}" has been added!', 'success')
        return redirect(url_for('clip.index'))

def validate_veo_link(url):
    """Validate Veo video URL"""
    # Add Veo-specific URL validation
    veo_pattern = r'https?://app\.veo\.co/matches/[a-zA-Z0-9-]+'
    return bool(re.match(veo_pattern, url))

def get_veo_embed_url(url):
    """Convert Veo URL to embed URL"""
    # Implement Veo embed URL conversion
    # You'll need to check Veo's documentation for proper embed URL format
    match_id = url.split('matches/')[1]
    return f'https://app.veo.co/embed/{match_id}'

@bp.route('/edit/<int:clip_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_clip(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    form = ClipForm(obj=clip)
    
    # Check if there are any tags
    tags_exist = ClipTag.query.count() > 0
    
    if request.method == 'GET':
        # Pre-select tags and players using the new relationship pattern
        form.tags.data = [tag.id for tag in clip.tags]
        form.players.data = [player.id for player in clip.players]
        
        # If clip has a point, populate the point choices
        if clip.game_id:
            points = Point.query.filter_by(game_id=clip.game_id).all()
            form.point_id.choices = [(0, 'Select Point')] + [(p.id, f"Point {p.point_number}") for p in points]
    
    if form.validate_on_submit():
        clip.title = form.title.data
        clip.game_id = form.game_id.data if form.game_id.data and form.game_id.data > 0 else None
        clip.point_id = form.point_id.data if form.point_id.data and form.point_id.data > 0 else None
        clip.youtube_link = form.youtube_link.data
        clip.start_time = form.start_time.data
        clip.end_time = form.end_time.data
        clip.description = form.description.data
        
        # Update tags using the new relationship pattern
        if form.tags.data:
            tags = ClipTag.query.filter(ClipTag.id.in_(form.tags.data)).all()
            clip.tags = tags
        else:
            clip.tags = []
        
        # Update players using the new relationship pattern
        if form.players.data:
            players = Player.query.filter(Player.id.in_(form.players.data)).all()
            clip.players = players
        else:
            clip.players = []
        
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been updated!', 'success')
        return redirect(url_for('clip.index'))
    
    return render_template('clip/clip_form.html', form=form, clip=clip, title='Edit Clip', tags_exist=tags_exist)


@bp.route('/delete/<int:clip_id>', methods=['POST'])
@login_required
@admin_required
def delete_clip(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    title = clip.title

    # Clear relationships
    clip.tags = []
    clip.players = []
    
    db.session.delete(clip)
    db.session.commit()

    flash(f'Clip "{title}" has been deleted!', 'success')
    return redirect(url_for('clip.index'))

@bp.route('/view/<int:clip_id>')
@login_required
def view_clip(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    
    # Make sure we're explicitly querying for annotations
    annotations = ClipAnnotation.query.filter_by(clip_id=clip.id).order_by(ClipAnnotation.timestamp).all()
    
    # Print for debugging
    print(f"Found {len(annotations)} annotations for clip {clip_id}")
    
    form = AnnotationForm()
    return render_template('clip/view_clip.html', clip=clip, annotations=annotations, form=form)


@bp.route('/add_annotation/<int:clip_id>', methods=['POST'])
@login_required
@admin_required
def add_annotation(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    form = AnnotationForm()
    
    if form.validate_on_submit():
        # Convert timestamp to seconds
        seconds = timestamp_to_seconds(form.timestamp.data)
        if seconds is None:
            flash('Invalid timestamp format', 'danger')
            return redirect(url_for('clip.view_clip', clip_id=clip.id))
            
        annotation = ClipAnnotation(
            clip_id=clip.id,
            timestamp=seconds,  # Store as seconds in database
            event_type=form.event_type.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            offense=form.offense.data,
            defense=form.defense.data,
            notes=form.notes.data
        )
        
        db.session.add(annotation)
        db.session.commit()
        
        flash('Annotation added successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')
    
    return redirect(url_for('clip.view_clip', clip_id=clip.id))

@bp.route('/edit_annotation/<int:annotation_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_annotation(annotation_id):
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    form = AnnotationForm(obj=annotation)
    
    if request.method == 'GET':
        # Convert seconds to timestamp for display
        form.timestamp.data = seconds_to_timestamp(annotation.timestamp)
    
    if form.validate_on_submit():
        # Convert timestamp to seconds
        seconds = timestamp_to_seconds(form.timestamp.data)
        if seconds is None:
            flash('Invalid timestamp format', 'danger')
            return render_template('clip/edit_annotation.html', form=form, annotation=annotation)
            
        annotation.timestamp = seconds
        annotation.event_type = form.event_type.data
        annotation.our_score = form.our_score.data
        annotation.their_score = form.their_score.data
        annotation.offense = form.offense.data
        annotation.defense = form.defense.data
        annotation.notes = form.notes.data
        
        db.session.commit()
        flash('Annotation updated successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    return render_template('clip/edit_annotation.html', form=form, annotation=annotation)

@bp.route('/delete_annotation/<int:annotation_id>', methods=['POST'])
@login_required
@admin_required
def delete_annotation(annotation_id):
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    clip_id = annotation.clip_id
    
    db.session.delete(annotation)
    db.session.commit()
    
    flash('Annotation deleted successfully!', 'success')
    return redirect(url_for('clip.view_clip', clip_id=clip_id))

@bp.route('/tags')
@login_required
def tags():
    tags = ClipTag.query.order_by(ClipTag.name).all()
    return render_template('clip/tags.html', tags=tags)

@bp.route('/tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tag():
    form = ClipTagForm()
    
    if form.validate_on_submit():
        # Check if tag already exists
        existing_tag = ClipTag.query.filter_by(name=form.name.data).first()
        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Add Tag')
        
        tag = ClipTag(name=form.name.data)
        db.session.add(tag)
        db.session.commit()
        
        flash(f'Tag "{tag.name}" has been added!', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/tag_form.html', form=form, title='Add Tag')

@bp.route('/tags/edit/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_tag(tag_id):
    tag = ClipTag.query.get_or_404(tag_id)
    form = ClipTagForm(obj=tag)
    
    if form.validate_on_submit():
        # Check if tag already exists
        existing_tag = ClipTag.query.filter(ClipTag.name == form.name.data, ClipTag.id != tag_id).first()
        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Edit Tag')
        
        tag.name = form.name.data
        db.session.commit()
        
        flash(f'Tag "{tag.name}" has been updated!', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')

@bp.route('/tags/delete/<int:tag_id>', methods=['POST'])
@login_required
@admin_required
def delete_tag(tag_id):
    tag = ClipTag.query.get_or_404(tag_id)
    name = tag.name
    
    # Clear relationships using the new pattern
    for clip in tag.clips:
        clip.tags.remove(tag)
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Tag "{name}" has been deleted!', 'success')
    return redirect(url_for('clip.tags'))

@bp.route('/get_points/<int:game_id>')
@login_required
def get_points(game_id):
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    return jsonify([{'id': p.id, 'name': f'Point {p.point_number}'} for p in points])

def extract_youtube_id(url):
    """Extract YouTube video ID from URL."""
    # Regular expressions to match various YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/watch\?.*v=)([^&\n?#]+)',
        r'(?:youtube\.com\/shorts\/)([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def seconds_to_timestamp(seconds):
    """Convert seconds to HH:MM:SS format"""
    if seconds is None:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def timestamp_to_seconds(timestamp):
    """Convert HH:MM:SS format to seconds"""
    if not timestamp:
        return None
    try:
        # Split timestamp into components
        parts = timestamp.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        else:
            return int(parts[0])
    except (ValueError, IndexError):
        return None
