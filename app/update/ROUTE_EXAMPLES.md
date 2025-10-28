# Complete Route Examples for Clip System

## Complete clip.py Routes File

Here's a complete example of how to integrate the new routes into your `app/routes/clip.py`:

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.clip import Clip, ClipTag
from app.models.annotation import ClipAnnotation, AnnotationTag
from app.models.game import Game
from app.models.point import Point
from app.models.player import Player
from app.models.user import User
from app.forms.clip_forms import ClipForm, ClipTagForm, ClipFilterForm
from app.forms.annotation_forms import AnnotationForm, QuickAnnotationForm, AnnotationFilterForm, AnnotationTagForm
from sqlalchemy import or_

bp = Blueprint('clip', __name__, url_prefix='/clips')


# ============================================================================
# CLIP ROUTES
# ============================================================================

@bp.route('/')
def index():
    """Display all clips with optional filtering"""
    form = ClipFilterForm(request.args)
    
    # Base query
    query = Clip.query
    
    # Apply filters
    if form.game_id.data and form.game_id.data > 0:
        query = query.filter_by(game_id=form.game_id.data)
    
    if form.tag_id.data and form.tag_id.data > 0:
        query = query.filter(Clip.tags.any(id=form.tag_id.data))
    
    if form.player_id.data and form.player_id.data > 0:
        query = query.filter(Clip.players.any(id=form.player_id.data))
    
    clips = query.order_by(Clip.created_at.desc()).all()
    
    return render_template('clip/index.html', clips=clips, form=form)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_clip():
    """Create a new clip"""
    form = ClipForm()
    
    if form.validate_on_submit():
        clip = Clip(
            title=form.title.data,
            youtube_link=form.youtube_link.data,
            video_source=form.video_source.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            description=form.description.data,
            game_id=form.game_id.data if form.game_id.data > 0 else None,
            point_id=form.point_id.data if form.point_id.data > 0 else None,
            created_by_id=current_user.id,
            team_organization_id=current_user.team_organization_id
        )
        
        # Add tags
        selected_tags = ClipTag.query.filter(ClipTag.id.in_(form.tags.data)).all()
        clip.tags = selected_tags
        
        # Add players
        selected_players = Player.query.filter(Player.id.in_(form.players.data)).all()
        clip.players = selected_players
        
        db.session.add(clip)
        db.session.commit()
        
        flash('Clip created successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip.id))
    
    tags_exist = ClipTag.query.count() > 0
    return render_template('clip/clip_form.html', form=form, title='Add Clip', tags_exist=tags_exist)


@bp.route('/<int:clip_id>')
def view_clip(clip_id):
    """View a single clip with all annotations"""
    clip = Clip.query.get_or_404(clip_id)
    
    # Increment view count
    clip.view_count += 1
    db.session.commit()
    
    # Get annotations with optional filtering
    query = ClipAnnotation.query.filter_by(clip_id=clip_id)
    
    # Apply visibility filters
    if not current_user.is_authenticated:
        query = query.filter_by(visibility='team')
    elif not (current_user.is_admin or current_user.is_coach):
        query = query.filter(
            or_(
                ClipAnnotation.visibility == 'team',
                ClipAnnotation.user_id == current_user.id
            )
        )
    
    # Apply request filters
    event_filter = request.args.get('event_filter')
    if event_filter:
        query = query.filter_by(event_type=event_filter)
    
    creator_filter = request.args.get('creator_filter')
    if creator_filter:
        query = query.filter_by(user_id=int(creator_filter))
    
    key_only = request.args.get('key_only')
    if key_only:
        query = query.filter_by(is_key_moment=True)
    
    annotations = query.order_by(ClipAnnotation.timestamp).all()
    
    # Get list of users who have created annotations for filter dropdown
    annotation_creators = db.session.query(User).join(
        ClipAnnotation, User.id == ClipAnnotation.user_id
    ).filter(ClipAnnotation.clip_id == clip_id).distinct().all()
    
    return render_template('clip/view_clip.html', 
                         clip=clip, 
                         annotations=annotations,
                         annotation_creators=annotation_creators)


@bp.route('/<int:clip_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_clip(clip_id):
    """Edit an existing clip"""
    clip = Clip.query.get_or_404(clip_id)
    
    # Check permissions
    if not (current_user.is_admin or current_user.is_coach or current_user.id == clip.created_by_id):
        flash('You do not have permission to edit this clip.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    form = ClipForm(obj=clip)
    
    if form.validate_on_submit():
        clip.title = form.title.data
        clip.youtube_link = form.youtube_link.data
        clip.video_source = form.video_source.data
        clip.start_time = form.start_time.data
        clip.end_time = form.end_time.data
        clip.description = form.description.data
        clip.game_id = form.game_id.data if form.game_id.data > 0 else None
        clip.point_id = form.point_id.data if form.point_id.data > 0 else None
        
        # Update tags
        selected_tags = ClipTag.query.filter(ClipTag.id.in_(form.tags.data)).all()
        clip.tags = selected_tags
        
        # Update players
        selected_players = Player.query.filter(Player.id.in_(form.players.data)).all()
        clip.players = selected_players
        
        db.session.commit()
        
        flash('Clip updated successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    # Pre-populate form
    form.tags.data = [tag.id for tag in clip.tags]
    form.players.data = [player.id for player in clip.players]
    
    tags_exist = ClipTag.query.count() > 0
    return render_template('clip/clip_form.html', form=form, title='Edit Clip', tags_exist=tags_exist)


@bp.route('/<int:clip_id>/delete', methods=['POST'])
@login_required
def delete_clip(clip_id):
    """Delete a clip and all its annotations"""
    clip = Clip.query.get_or_404(clip_id)
    
    # Check permissions
    if not (current_user.is_admin or current_user.is_coach or current_user.id == clip.created_by_id):
        flash('You do not have permission to delete this clip.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    db.session.delete(clip)
    db.session.commit()
    
    flash('Clip deleted successfully!', 'success')
    return redirect(url_for('clip.index'))


@bp.route('/game/<int:game_id>')
def game_clips(game_id):
    """View all clips for a specific game"""
    game = Game.query.get_or_404(game_id)
    clips = Clip.query.filter_by(game_id=game_id).order_by(Clip.created_at.desc()).all()
    return render_template('clip/game_clips.html', game=game, clips=clips)


@bp.route('/point/<int:point_id>')
def point_clips(point_id):
    """View all clips for a specific point"""
    point = Point.query.get_or_404(point_id)
    clips = Clip.query.filter_by(point_id=point_id).order_by(Clip.created_at.desc()).all()
    return render_template('clip/point_clips.html', point=point, clips=clips)


# ============================================================================
# ANNOTATION ROUTES
# ============================================================================

@bp.route('/<int:clip_id>/annotation/add', methods=['GET', 'POST'])
@login_required
def add_annotation(clip_id):
    """Add a new annotation to a clip"""
    clip = Clip.query.get_or_404(clip_id)
    form = AnnotationForm()
    
    if form.validate_on_submit():
        annotation = ClipAnnotation(
            clip_id=clip_id,
            user_id=current_user.id,
            timestamp=form.timestamp.data,
            title=form.title.data,
            event_type=form.event_type.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            offense=form.offense.data,
            defense=form.defense.data,
            notes=form.notes.data,
            is_key_moment=form.is_key_moment.data,
            visibility=form.visibility.data,
            team_organization_id=current_user.team_organization_id
        )
        
        # Add tags
        selected_tags = AnnotationTag.query.filter(
            AnnotationTag.id.in_(form.tags.data)
        ).all()
        annotation.tags = selected_tags
        
        # Add players
        selected_players = Player.query.filter(
            Player.id.in_(form.players.data)
        ).all()
        annotation.players = selected_players
        
        db.session.add(annotation)
        db.session.commit()
        
        flash('Annotation added successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    return render_template('clip/add_annotation.html', form=form, clip=clip)


@bp.route('/annotation/<int:annotation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_annotation(annotation_id):
    """Edit an existing annotation"""
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    
    # Check permissions
    if not (current_user.id == annotation.user_id or 
            current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to edit this annotation.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    form = AnnotationForm(obj=annotation)
    
    if form.validate_on_submit():
        annotation.timestamp = form.timestamp.data
        annotation.title = form.title.data
        annotation.event_type = form.event_type.data
        annotation.our_score = form.our_score.data
        annotation.their_score = form.their_score.data
        annotation.offense = form.offense.data
        annotation.defense = form.defense.data
        annotation.notes = form.notes.data
        annotation.is_key_moment = form.is_key_moment.data
        annotation.visibility = form.visibility.data
        
        # Update tags
        selected_tags = AnnotationTag.query.filter(
            AnnotationTag.id.in_(form.tags.data)
        ).all()
        annotation.tags = selected_tags
        
        # Update players
        selected_players = Player.query.filter(
            Player.id.in_(form.players.data)
        ).all()
        annotation.players = selected_players
        
        db.session.commit()
        flash('Annotation updated successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    # Pre-populate form
    form.tags.data = [tag.id for tag in annotation.tags]
    form.players.data = [player.id for player in annotation.players]
    
    return render_template('clip/edit_annotation.html', form=form, annotation=annotation)


@bp.route('/annotation/<int:annotation_id>/delete', methods=['POST'])
@login_required
def delete_annotation(annotation_id):
    """Delete an annotation"""
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    
    # Check permissions
    if not (current_user.id == annotation.user_id or 
            current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to delete this annotation.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    clip_id = annotation.clip_id
    db.session.delete(annotation)
    db.session.commit()
    
    flash('Annotation deleted successfully!', 'success')
    return redirect(url_for('clip.view_clip', clip_id=clip_id))


# ============================================================================
# TAG MANAGEMENT ROUTES
# ============================================================================

@bp.route('/tags')
@login_required
def tags():
    """View all clip tags"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to manage tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    tags = ClipTag.query.filter_by(
        team_organization_id=current_user.team_organization_id
    ).order_by(ClipTag.category, ClipTag.name).all()
    
    return render_template('clip/tags.html', tags=tags)


@bp.route('/tags/add', methods=['GET', 'POST'])
@login_required
def add_tag():
    """Add a new clip tag"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to add tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    form = ClipTagForm()
    
    if form.validate_on_submit():
        tag = ClipTag(
            name=form.name.data,
            team_organization_id=current_user.team_organization_id
        )
        db.session.add(tag)
        db.session.commit()
        
        flash('Tag created successfully!', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/tag_form.html', form=form, title='Add Tag')


@bp.route('/tags/<int:tag_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tag(tag_id):
    """Edit an existing clip tag"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to edit tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    tag = ClipTag.query.get_or_404(tag_id)
    form = ClipTagForm(obj=tag)
    
    if form.validate_on_submit():
        tag.name = form.name.data
        db.session.commit()
        
        flash('Tag updated successfully!', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/tag_form.html', form=form, title='Edit Tag')


@bp.route('/tags/<int:tag_id>/delete', methods=['POST'])
@login_required
def delete_tag(tag_id):
    """Delete a clip tag"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to delete tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    tag = ClipTag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    
    flash('Tag deleted successfully!', 'success')
    return redirect(url_for('clip.tags'))


# ============================================================================
# ANNOTATION TAG MANAGEMENT ROUTES
# ============================================================================

@bp.route('/annotation-tags')
@login_required
def annotation_tags():
    """View all annotation tags"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to manage annotation tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    # Get root tags and build hierarchy
    root_tags = AnnotationTag.query.filter_by(
        parent_tag_id=None,
        team_organization_id=current_user.team_organization_id
    ).order_by(AnnotationTag.category, AnnotationTag.name).all()
    
    return render_template('clip/annotation_tags.html', root_tags=root_tags)


@bp.route('/annotation-tags/add', methods=['GET', 'POST'])
@login_required
def add_annotation_tag():
    """Add a new annotation tag"""
    if not (current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to add annotation tags.', 'danger')
        return redirect(url_for('clip.index'))
    
    form = AnnotationTagForm()
    
    if form.validate_on_submit():
        tag = AnnotationTag(
            name=form.name.data,
            category=form.category.data,
            parent_tag_id=form.parent_tag_id.data if form.parent_tag_id.data > 0 else None,
            color=form.color.data,
            description=form.description.data,
            is_active=form.is_active.data,
            team_organization_id=current_user.team_organization_id
        )
        db.session.add(tag)
        db.session.commit()
        
        flash('Annotation tag created successfully!', 'success')
        return redirect(url_for('clip.annotation_tags'))
    
    return render_template('clip/annotation_tag_form.html', form=form, title='Add Annotation Tag')


# ============================================================================
# AJAX/API ROUTES
# ============================================================================

@bp.route('/get_points/<int:game_id>')
def get_points(game_id):
    """AJAX endpoint to get points for a game"""
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    return jsonify([{
        'id': p.id,
        'name': f"Point {p.point_number}"
    } for p in points])


@bp.route('/get_game_link/<int:game_id>')
def get_game_link(game_id):
    """AJAX endpoint to get YouTube link from game"""
    game = Game.query.get_or_404(game_id)
    return jsonify({
        'youtube_link': game.youtube_link if hasattr(game, 'youtube_link') else None
    })


# ============================================================================
# OPTIONAL: API ENDPOINTS FOR MOBILE/EXTERNAL ACCESS
# ============================================================================

@bp.route('/api/clip/<int:clip_id>/annotations')
def api_get_annotations(clip_id):
    """API endpoint to get all annotations for a clip (JSON)"""
    annotations = ClipAnnotation.query.filter_by(clip_id=clip_id).all()
    
    return jsonify([{
        'id': a.id,
        'timestamp': a.timestamp,
        'title': a.title,
        'event_type': a.event_type,
        'tags': [{'id': t.id, 'name': t.name, 'color': t.color} for t in a.tags],
        'players': [{'id': p.id, 'name': p.name, 'number': p.jersey_number} for p in a.players],
        'creator': a.created_by.username if a.created_by else None,
        'is_key_moment': a.is_key_moment,
        'notes': a.notes,
        'created_at': a.created_at.isoformat()
    } for a in annotations])
```

## Additional Helper Functions

Add these to your utils or as module-level functions:

```python
def user_can_edit_annotation(user, annotation):
    """Check if user can edit an annotation"""
    return (
        user.is_admin or 
        user.is_coach or 
        user.id == annotation.user_id
    )

def user_can_view_annotation(user, annotation):
    """Check if user can view an annotation based on visibility"""
    if annotation.visibility == 'team':
        return True
    elif annotation.visibility == 'coaches':
        return user.is_admin or user.is_coach
    elif annotation.visibility == 'private':
        return user.id == annotation.user_id
    return False

def get_annotation_stats(clip_id):
    """Get statistics for annotations on a clip"""
    annotations = ClipAnnotation.query.filter_by(clip_id=clip_id).all()
    
    return {
        'total': len(annotations),
        'key_moments': sum(1 for a in annotations if a.is_key_moment),
        'by_user': db.session.query(
            User.username,
            db.func.count(ClipAnnotation.id)
        ).join(ClipAnnotation).filter(
            ClipAnnotation.clip_id == clip_id
        ).group_by(User.username).all()
    }
```

## Remember to Update __init__.py

In your `app/models/__init__.py`, add:
```python
from app.models.annotation import ClipAnnotation, AnnotationTag
```

In your `app/routes/__init__.py`, the clip blueprint should already be imported.

## Testing Your Routes

Test with these curl commands:

```bash
# Get all clips
curl http://localhost:5000/clips/

# Get specific clip with annotations
curl http://localhost:5000/clips/1

# Get annotations as JSON
curl http://localhost:5000/clips/api/clip/1/annotations

# Get points for a game (AJAX)
curl http://localhost:5000/clips/get_points/1
```
