from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.clip import Clip, ClipTag, ClipTagRelation, ClipPlayer
from app.models.game import Game
from app.models.point import Point
from app.models.player import Player
from app.models.annotation import ClipAnnotation
from app.forms.annotation import AnnotationForm
from app.forms.clip import ClipForm, ClipTagForm, ClipFilterForm
import re

bp = Blueprint('clip', __name__, url_prefix='/clips')

@bp.route('/')
@login_required
def index():
    form = ClipFilterForm()
    
    # Get filter parameters
    game_id = request.args.get('game_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    player_id = request.args.get('player_id', type=int)
    
    # Set form values from query parameters
    if game_id:
        form.game_id.data = game_id
    if tag_id:
        form.tag_id.data = tag_id
    if player_id:
        form.player_id.data = player_id
    
    # Build query based on filters
    query = Clip.query
    
    if game_id:
        query = query.filter(Clip.game_id == game_id)
    if tag_id:
        query = query.join(ClipTagRelation).filter(ClipTagRelation.tag_id == tag_id)
    if player_id:
        query = query.join(ClipPlayer).filter(ClipPlayer.player_id == player_id)
    
    # Get clips and sort by creation date (newest first)
    clips = query.order_by(Clip.created_at.desc()).all()
    
    return render_template('clip/index.html', clips=clips, form=form)

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

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_clip():
    form = ClipForm()
    
    # Check if there are any tags
    tags_exist = ClipTag.query.count() > 0
    
    if form.validate_on_submit():
        # Extract video ID from YouTube link
        youtube_link = form.youtube_link.data
        video_id = extract_youtube_id(youtube_link)
        
        if not video_id:
            flash('Invalid YouTube link. Please provide a valid YouTube URL.', 'danger')
            return render_template('clip/clip_form.html', form=form, title='Add Clip', tags_exist=tags_exist)
        
        # Create standardized YouTube link
        standard_link = f'https://www.youtube.com/watch?v={video_id}'
        
        clip = Clip(
            title=form.title.data,
            game_id=form.game_id.data if form.game_id.data and form.game_id.data > 0 else None,
            point_id=form.point_id.data if form.point_id.data and form.point_id.data > 0 else None,
            youtube_link=standard_link,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            description=form.description.data
        )
        
        db.session.add(clip)
        db.session.commit()
        
        # Add tags if selected
        if form.tags.data:
            for tag_id in form.tags.data:
                tag_relation = ClipTagRelation(clip_id=clip.id, tag_id=tag_id)
                db.session.add(tag_relation)
        
        # Add players if selected
        if form.players.data:
            for player_id in form.players.data:
                player_relation = ClipPlayer(clip_id=clip.id, player_id=player_id)
                db.session.add(player_relation)
        
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been added!', 'success')
        return redirect(url_for('clip.index'))
    
    # Pre-select game and point if coming from game or point page
    game_id = request.args.get('game_id', type=int)
    point_id = request.args.get('point_id', type=int)
    
    if game_id:
        form.game_id.data = game_id
    if point_id:
        point = Point.query.get(point_id)
        if point:
            form.game_id.data = point.game_id
            form.point_id.data = point_id
    
    return render_template('clip/clip_form.html', form=form, title='Add Clip', tags_exist=tags_exist)


@bp.route('/edit/<int:clip_id>', methods=['GET', 'POST'])
@login_required
def edit_clip(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    form = ClipForm(obj=clip)
    
    # Check if there are any tags
    tags_exist = ClipTag.query.count() > 0
    
    if request.method == 'GET':
        # Pre-select tags and players
        form.tags.data = [relation.tag_id for relation in clip.tags]
        form.players.data = [relation.player_id for relation in clip.players]
        
        # If clip has a point, populate the point choices
        if clip.game_id:
            points = Point.query.filter_by(game_id=clip.game_id).all()
            form.point_id.choices = [(0, 'Select Point')] + [(p.id, f"Point {p.point_number}") for p in points]
    
    if form.validate_on_submit():
        # Extract video ID from YouTube link
        youtube_link = form.youtube_link.data
        video_id = extract_youtube_id(youtube_link)
        
        if not video_id:
            flash('Invalid YouTube link. Please provide a valid YouTube URL.', 'danger')
            return render_template('clip/clip_form.html', form=form, title='Edit Clip', tags_exist=tags_exist)
        
        # Create standardized YouTube link
        standard_link = f'https://www.youtube.com/watch?v={video_id}'
        
        clip.title = form.title.data
        clip.game_id = form.game_id.data if form.game_id.data and form.game_id.data > 0 else None
        clip.point_id = form.point_id.data if form.point_id.data and form.point_id.data > 0 else None
        clip.youtube_link = standard_link
        clip.start_time = form.start_time.data
        clip.end_time = form.end_time.data
        clip.description = form.description.data
        
        # Update tags
        ClipTagRelation.query.filter_by(clip_id=clip.id).delete()
        if form.tags.data:
            for tag_id in form.tags.data:
                tag_relation = ClipTagRelation(clip_id=clip.id, tag_id=tag_id)
                db.session.add(tag_relation)
        
        # Update players
        ClipPlayer.query.filter_by(clip_id=clip.id).delete()
        if form.players.data:
            for player_id in form.players.data:
                player_relation = ClipPlayer(clip_id=clip.id, player_id=player_id)
                db.session.add(player_relation)
        
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been updated!', 'success')
        return redirect(url_for('clip.index'))
    
    return render_template('clip/clip_form.html', form=form, clip=clip, title='Edit Clip', tags_exist=tags_exist)


@bp.route('/delete/<int:clip_id>', methods=['POST'])
@login_required
def delete_clip(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    title = clip.title
    
    # Delete related records
    ClipTagRelation.query.filter_by(clip_id=clip.id).delete()
    ClipPlayer.query.filter_by(clip_id=clip.id).delete()
    
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
def add_annotation(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    form = AnnotationForm()
    
    if form.validate_on_submit():
        annotation = ClipAnnotation(
            clip_id=clip.id,
            timestamp=form.timestamp.data,
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
def edit_annotation(annotation_id):
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    form = AnnotationForm(obj=annotation)
    
    if form.validate_on_submit():
        annotation.timestamp = form.timestamp.data
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
def delete_tag(tag_id):
    tag = ClipTag.query.get_or_404(tag_id)
    name = tag.name
    
    # Delete related records
    ClipTagRelation.query.filter_by(tag_id=tag.id).delete()
    
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
