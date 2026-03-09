from flask import abort, Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from app import db
from app.models import Clip, ClipTag, ClipAnnotation
from app.models.annotation import AnnotationTag
from app.models.game import Game
from app.models.point import Point
from app.models.player import Player
from app.models.user import User
from app.forms.annotation import AnnotationForm
from app.forms.clip import ClipForm, ClipTagForm, ClipFilterForm
from app.models.clip import ClipPointSegment
from sqlalchemy import or_
import re
from app.utils.utils import admin_required
import csv
import io
from flask import send_file
from datetime import datetime
from flask import current_app
from itsdangerous import URLSafeSerializer, BadSignature
import time
from app.utils.team_filter import get_current_team_id

bp = Blueprint('clip', __name__, url_prefix='/clips')


def get_share_serializer():
    """Serializer for generating and verifying share tokens."""
    # Different salt for safety and future rotation
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='clip-share-v1')

# ============================================================================
# CLIP ROUTES
# ============================================================================

@bp.route('/')
@login_required
def index():
    from sqlalchemy import func  # ensure func is always available
    from app.models.clip import clip_tag_relation  # needed for tag stats

    form = ClipFilterForm()
    delete_form = FlaskForm()

    # Get filter parameters
    game_id = request.args.get('game_id', type=int)
    tag_ids = request.args.getlist('tags', type=int)
    # Support legacy ?tag_id=... links
    legacy_tag_id = request.args.get('tag_id', type=int)
    if legacy_tag_id and legacy_tag_id not in tag_ids:
        tag_ids.append(legacy_tag_id)

    tag_category = request.args.get('tag_category', type=str)
    player_id = request.args.get('player_id', type=int)
    video_source = request.args.get('video_source', type=str)
    is_featured = request.args.get('is_featured', type=str)
    sort_by = request.args.get('sort_by', default='created_desc', type=str)

    # Get current team ID
    team_id = get_current_team_id()

    # Build query based on filters
    query = Clip.query.filter_by(team_organization_id=team_id)

    # Apply filters
    if game_id and game_id > 0:
        query = query.filter(Clip.game_id == game_id)

    # Multi-tag filter (AND logic - clip must have ALL selected tags)
    if tag_ids:
        for tag_id in tag_ids:
            query = query.filter(Clip.tags.any(ClipTag.id == tag_id))

    # Tag category filter
    if tag_category:
        query = query.filter(Clip.tags.any(ClipTag.category == tag_category))

    if player_id and player_id > 0:
        query = query.filter(Clip.players.any(Player.id == player_id))

    if video_source:
        query = query.filter(Clip.video_source == video_source)

    if is_featured == '1':
        query = query.filter(Clip.is_featured == True)

    # Apply sorting
    if sort_by == 'created_desc':
        query = query.order_by(Clip.created_at.desc())
    elif sort_by == 'created_asc':
        query = query.order_by(Clip.created_at.asc())
    elif sort_by == 'title_asc':
        query = query.order_by(Clip.title.asc())
    elif sort_by == 'views_desc':
        query = query.order_by(Clip.view_count.desc())
    elif sort_by == 'annotations_desc':
        # Sort by annotation count
        query = (query
                 .outerjoin(ClipAnnotation)
                 .group_by(Clip.id)
                 .order_by(func.count(ClipAnnotation.id).desc()))

    # Get clips
    clips = query.all()

    # Get tag statistics for sidebar
    tag_stats = (db.session.query(
                    ClipTag.id,
                    ClipTag.name,
                    ClipTag.category,
                    ClipTag.color,
                    func.count(clip_tag_relation.c.clip_id).label('clip_count')
                 )
                 .join(clip_tag_relation, ClipTag.id == clip_tag_relation.c.tag_id)
                 .join(Clip, Clip.id == clip_tag_relation.c.clip_id)
                 .filter(
                    ClipTag.team_organization_id == team_id,
                    Clip.team_organization_id == team_id,
                    ClipTag.is_active == True
                 )
                 .group_by(ClipTag.id)
                 .order_by(ClipTag.category, func.count(clip_tag_relation.c.clip_id).desc())
                 .all())

    return render_template(
        'clip/index.html',
        clips=clips,
        form=form,
        delete_form=delete_form,
        tag_stats=tag_stats,
        active_filters={
            'game_id': game_id,
            'tag_ids': tag_ids,
            'tag_category': tag_category,
            'player_id': player_id,
            'video_source': video_source,
            'is_featured': is_featured,
            'sort_by': sort_by
        }
    )


@bp.route('/game/<int:game_id>')
@login_required
def game_clips(game_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Filter game by team
    game = Game.query.filter_by(id=game_id, team_organization_id=team_id).first_or_404()
    
    # Filter clips by game and team
    clips = Clip.query.filter_by(
        game_id=game_id,
        team_organization_id=team_id
    ).order_by(Clip.created_at.desc()).all()
    
    return render_template('clip/game_clips.html', game=game, clips=clips)

@bp.route('/point/<int:point_id>')
@login_required
def point_clips(point_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Get point and verify it belongs to the current team
    point = Point.query.get_or_404(point_id)
    
    # Check if the point's game belongs to the current team
    game = Game.query.filter_by(id=point.game_id, team_organization_id=team_id).first_or_404()
    
    # Filter clips by point and team
    clips = Clip.query.filter_by(
        point_id=point_id,
        team_organization_id=team_id
    ).order_by(Clip.created_at.desc()).all()
    
    return render_template('clip/point_clips.html', point=point, clips=clips)

@bp.route('/add_clip', methods=['GET', 'POST'])
@login_required
@admin_required
def add_clip():
    form = ClipForm()
    
    # Get current team ID
    team_id = get_current_team_id()
    
    # Check if there are any tags
    tags_exist = ClipTag.query.filter_by(team_organization_id=team_id).count() > 0
    
    if form.validate_on_submit():
        clip = Clip(
            title=form.title.data,
            video_source=form.video_source.data,
            youtube_link=form.youtube_link.data,
            game_id=form.game_id.data if form.game_id.data else None,
            point_id=form.point_id.data if form.point_id.data else None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            description=form.description.data,
            created_by_id=current_user.id,
            team_organization_id=team_id
        )

        # Add tags and players
        if form.tags.data:
            tags = ClipTag.query.filter(
                ClipTag.id.in_(form.tags.data),
                ClipTag.team_organization_id == team_id
            ).all()
            clip.tags = tags

        if form.players.data:
            players = Player.query.filter(
                Player.id.in_(form.players.data),
                Player.team_organization_id == team_id
            ).all()
            clip.players = players

        db.session.add(clip)
        db.session.commit()

        flash(f'Clip "{clip.title}" has been added!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip.id))
    
    return render_template('clip/clip_form.html', form=form, title='Add Clip', tags_exist=tags_exist)

@bp.route('/<int:clip_id>')
@login_required
def view_clip(clip_id):
    """View a single clip with all annotations"""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    
    # Increment view count
    clip.view_count = (clip.view_count or 0) + 1
    db.session.commit()
    
    # Get annotations with optional filtering
    query = ClipAnnotation.query.filter_by(clip_id=clip_id)
    
    # Apply visibility filters
    if not (current_user.is_admin or current_user.is_coach):
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

@bp.route('/edit/<int:clip_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_clip(clip_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Filter clip by team
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    
    form = ClipForm(obj=clip)
    
    # Check if there are any tags
    tags_exist = ClipTag.query.filter_by(team_organization_id=team_id).count() > 0
    
    if request.method == 'GET':
        # Pre-select tags and players
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
        
        # Update tags
        if form.tags.data:
            tags = ClipTag.query.filter(
                ClipTag.id.in_(form.tags.data),
                ClipTag.team_organization_id == team_id
            ).all()
            clip.tags = tags
        else:
            clip.tags = []
        
        # Update players
        if form.players.data:
            players = Player.query.filter(
                Player.id.in_(form.players.data),
                Player.team_organization_id == team_id
            ).all()
            clip.players = players
        else:
            clip.players = []
        
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been updated!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    return render_template('clip/clip_form.html', form=form, clip=clip, title='Edit Clip', tags_exist=tags_exist)

@bp.route('/delete/<int:clip_id>', methods=['POST'])
@login_required
@admin_required
def delete_clip(clip_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Filter clip by team
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    
    title = clip.title
    db.session.delete(clip)
    db.session.commit()
    
    flash(f'Clip "{title}" and all its annotations have been deleted!', 'success')
    return redirect(url_for('clip.index'))

@bp.route('/<int:clip_id>/segments', methods=['GET'])
@login_required
def get_segments(clip_id):
    clip = _get_clip_or_404(clip_id)
    segments = (ClipPointSegment.query
                .filter_by(clip_id=clip.id)
                .order_by(ClipPointSegment.point_number.asc())
                .all())
    return jsonify([{
        'id': s.id,
        'point_number': s.point_number,
        'start_time': s.start_time,
        'end_time': s.end_time
    } for s in segments])

@bp.route('/<int:clip_id>/segments/<int:segment_id>', methods=['DELETE'])
@login_required
def delete_segment(clip_id, segment_id):
    # Optional: restrict to admins/coaches
    if not (current_user.is_admin or current_user.is_coach):
        abort(403)
    seg = ClipPointSegment.query.filter_by(id=segment_id, clip_id=clip_id).first_or_404()
    db.session.delete(seg)
    db.session.commit()
    return ('', 204)

@bp.route('/<int:clip_id>/segments/<string:action>', methods=['POST'])
@login_required
def mark_segment(clip_id, action):
    clip = _get_clip_or_404(clip_id)
    team_id = get_current_team_id()
    
    data = request.get_json(silent=True) or {}
    timestamp = data.get('timestamp', None)
    if timestamp is None:
        return ('Missing timestamp', 400)

    if action == 'start':
        # Determine the next point number (last + 1)
        last_seg = (ClipPointSegment.query
                    .filter_by(clip_id=clip.id)
                    .order_by(ClipPointSegment.point_number.desc())
                    .first())
        next_num = (last_seg.point_number + 1) if last_seg else 1
        seg = ClipPointSegment(
            clip_id=clip.id,
            point_number=next_num,
            start_time=int(timestamp),
            end_time=None,
            created_by_id=current_user.id if current_user.is_authenticated else None,
            team_organization_id=team_id
        )
        db.session.add(seg)
        db.session.commit()
        return jsonify({'status': 'started', 'id': seg.id, 'point_number': seg.point_number})

    elif action == 'end':
        # Close the most recent open segment
        open_seg = (ClipPointSegment.query
                    .filter_by(clip_id=clip.id, end_time=None)
                    .order_by(ClipPointSegment.point_number.desc())
                    .first())
        if not open_seg:
            return ('No open point to end. Mark a start first.', 400)
        end_ts = int(timestamp)
        if end_ts < open_seg.start_time:
            return ('End time cannot be before start time.', 400)
        open_seg.end_time = end_ts
        db.session.commit()
        return jsonify({'status': 'ended', 'id': open_seg.id, 'point_number': open_seg.point_number})

    else:
        return ('Invalid action', 400)

def _get_clip_or_404(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    return clip

# ============================================================================
# ANNOTATION ROUTES
# ============================================================================

@bp.route('/<int:clip_id>/annotation/add', methods=['GET', 'POST'])
@login_required
def add_annotation(clip_id):
    """Add a new annotation to a clip"""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    form = AnnotationForm()
    
    # Prefill from query param t
    t = request.args.get('t', type=int)
    if t is not None and (form.timestamp.data is None or form.timestamp.data == 0):
        form.timestamp.data = t
    
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
            team_organization_id=team_id
        )
        
        # Add tags
        if form.tags.data:
            selected_tags = AnnotationTag.query.filter(
                AnnotationTag.id.in_(form.tags.data),
                AnnotationTag.team_organization_id == team_id
            ).all()
            annotation.tags = selected_tags
        
        # Add players
        if form.players.data:
            selected_players = Player.query.filter(
                Player.id.in_(form.players.data),
                Player.team_organization_id == team_id
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
    team_id = get_current_team_id()
    
    # Check permissions
    if not (current_user.id == annotation.user_id or 
            current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to edit this annotation.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    form = AnnotationForm(obj=annotation)
    
    if request.method == 'GET':
        # Pre-populate form
        form.tags.data = [tag.id for tag in annotation.tags]
        form.players.data = [player.id for player in annotation.players]
    
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
        if form.tags.data:
            selected_tags = AnnotationTag.query.filter(
                AnnotationTag.id.in_(form.tags.data),
                AnnotationTag.team_organization_id == team_id
            ).all()
            annotation.tags = selected_tags
        else:
            annotation.tags = []
        
        # Update players
        if form.players.data:
            selected_players = Player.query.filter(
                Player.id.in_(form.players.data),
                Player.team_organization_id == team_id
            ).all()
            annotation.players = selected_players
        else:
            annotation.players = []
        
        db.session.commit()
        flash('Annotation updated successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
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
@admin_required
def tags():
    """View all clip tags with statistics"""
    team_id = get_current_team_id()
    
    # Get tags with clip counts
    from sqlalchemy import func
    from app.models.clip import clip_tag_relation
    
    tags_query = db.session.query(
        ClipTag,
        func.count(clip_tag_relation.c.clip_id).label('clip_count')
    ).outerjoin(
        clip_tag_relation, ClipTag.id == clip_tag_relation.c.tag_id
    ).filter(
        ClipTag.team_organization_id == team_id
    ).group_by(
        ClipTag.id
    ).order_by(
        ClipTag.category,
        ClipTag.name
    )
    
    tags_with_counts = tags_query.all()
    
    # Group by category for display
    tags_by_category = {}
    for tag, count in tags_with_counts:
        category = tag.category or 'Uncategorized'
        if category not in tags_by_category:
            tags_by_category[category] = []
        tags_by_category[category].append((tag, count))
    
    return render_template('clip/tags.html', 
                         tags_by_category=tags_by_category)

@bp.route('/annotation-tags/bulk_create', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_create_annotation_tags():
    """Bulk create common annotation tags for video analysis"""
    team_id = get_current_team_id()

    # Define common annotation tag structure
    # Each top-level key is a category; we create a parent tag with the same name,
    # then create child tags under it. Colors are just reasonable defaults.
    common = {
        'Offense': {
            'color': '#1976D2',
            'children': [
                ('Handler Movement', '#1565C0'),
                ('Reset', '#1E88E5'),
                ('Break Side', '#42A5F5'),
                ('Deep Shot', '#64B5F6'),
                ('Give-and-Go', '#90CAF9'),
                ('Endzone Offense', '#0D47A1'),
            ]
        },
        'Defense': {
            'color': '#D32F2F',
            'children': [
                ('Force Flick', '#C62828'),
                ('Force Backhand', '#B71C1C'),
                ('No Around', '#EF5350'),
                ('Poach', '#E53935'),
                ('Help Defense', '#F44336'),
                ('Zone Defense', '#8E24AA'),
            ]
        },
        'Throws': {
            'color': '#388E3C',
            'children': [
                ('Backhand', '#2E7D32'),
                ('Forehand', '#43A047'),
                ('Hammer', '#66BB6A'),
                ('Scoober', '#81C784'),
                ('High Release', '#A5D6A7'),
                ('Inside', '#4CAF50'),
                ('Around', '#66BB6A'),
            ]
        },
        'Cuts': {
            'color': '#FFA000',
            'children': [
                ('Under', '#FB8C00'),
                ('Deep', '#F57C00'),
                ('Break', '#FFB300'),
                ('Continuation', '#FFCA28'),
                ('Upline', '#FF9800'),
            ]
        },
        'Turnovers': {
            'color': '#5D4037',
            'children': [
                ('Throwaway', '#6D4C41'),
                ('Drop', '#8D6E63'),
                ('Block', '#4E342E'),
                ('Stall Out', '#795548'),
                ('Misc Penalty', '#A1887F'),
            ]
        },
        'Outcomes': {
            'color': '#0097A7',
            'children': [
                ('Goal', '#00838F'),
                ('Assist', '#00ACC1'),
                ('Hockey Assist', '#26C6DA'),
                ('Break Point', '#00BCD4'),
                ('Hold', '#4DD0E1'),
            ]
        },
        'Review': {
            'color': '#7B1FA2',
            'children': [
                ('Good Example', '#6A1B9A'),
                ('Learning Opportunity', '#8E24AA'),
                ('Key Moment', '#AB47BC'),
                ('Tactical Breakdown', '#BA68C8'),
                ('Common Mistake', '#CE93D8'),
            ]
        }
    }

    if request.method == 'POST':
        created_count = 0
        skipped_count = 0

        def get_or_create_parent(name, category, color):
            existing = AnnotationTag.query.filter_by(
                name=name, team_organization_id=team_id
            ).first()
            if existing:
                return existing, False
            obj = AnnotationTag(
                name=name,
                category=category,
                parent_tag_id=None,
                color=color,
                description=None,
                is_active=True,
                team_organization_id=team_id
            )
            db.session.add(obj)
            return obj, True

        def get_or_create_child(name, category, color, parent_id):
            existing = AnnotationTag.query.filter_by(
                name=name, team_organization_id=team_id
            ).first()
            if existing:
                return existing, False
            obj = AnnotationTag(
                name=name,
                category=category,
                parent_tag_id=parent_id,
                color=color,
                description=None,
                is_active=True,
                team_organization_id=team_id
            )
            db.session.add(obj)
            return obj, True

        # Create parents and children
        for category, conf in common.items():
            parent, parent_created = get_or_create_parent(category, category, conf['color'])
            created_count += 1 if parent_created else 0
            skipped_count += 0 if parent_created else 1

            for child_name, child_color in conf['children']:
                _, child_created = get_or_create_child(child_name, category, child_color, parent.id)
                created_count += 1 if child_created else 0
                skipped_count += 0 if child_created else 1

        db.session.commit()

        flash(f'Created {created_count} annotation tags. Skipped {skipped_count} existing.', 'success')
        return redirect(url_for('clip.annotation_tags'))

    # GET => show preview page
    return render_template('clip/bulk_create_annotation_tags.html', common=common)


@bp.route('/tags/bulk_create', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_create_tags():
    """Bulk create common tags for video organization"""
    team_id = get_current_team_id()
    
    if request.method == 'POST':
        # Define common tag structure
        common_tags = {
            'Video Type': [
                ('Full Game', '#1976D2'),
                ('Highlight Reel', '#FFA000'),
                ('Training Session', '#388E3C'),
                ('Drill Demonstration', '#7B1FA2'),
                ('Team Meeting', '#0097A7'),
                ('Individual Footage', '#5D4037')
            ],
            'Game Context': [
                ('Tournament Game', '#D32F2F'),
                ('League Game', '#C2185B'),
                ('Scrimmage', '#7B1FA2'),
                ('Championship', '#FFD700'),
                ('Qualifier', '#512DA8')
            ],
            'Training Type': [
                ('Offensive Practice', '#1976D2'),
                ('Defensive Practice', '#D32F2F'),
                ('Conditioning', '#388E3C'),
                ('Skills Training', '#FFA000'),
                ('Strategy Session', '#5D4037'),
                ('Film Review', '#0097A7')
            ],
            'Skill Focus': [
                ('Throwing', '#1976D2'),
                ('Cutting', '#388E3C'),
                ('Marking', '#D32F2F'),
                ('Handler Movement', '#7B1FA2'),
                ('Positioning', '#FFA000'),
                ('Communication', '#0097A7')
            ],
            'Strategic Focus': [
                ('Offensive Sets', '#1976D2'),
                ('Defensive Sets', '#D32F2F'),
                ('Zone Offense', '#388E3C'),
                ('Zone Defense', '#C2185B'),
                ('Transition', '#FFA000'),
                ('Endzone Plays', '#7B1FA2')
            ],
            'Player Development': [
                ('Rookie Training', '#4CAF50'),
                ('Advanced Skills', '#FF5722'),
                ('Captain Development', '#FFD700'),
                ('Position-Specific', '#3F51B5'),
                ('Fitness', '#8BC34A')
            ],
            'Analysis': [
                ('Good Example', '#4CAF50'),
                ('Learning Opportunity', '#FFA000'),
                ('Key Moment', '#FFD700'),
                ('Tactical Breakdown', '#3F51B5'),
                ('Common Mistake', '#F44336')
            ]
        }
        
        created_count = 0
        skipped_count = 0
        
        for category, tags in common_tags.items():
            for tag_name, color in tags:
                # Check if tag already exists
                existing = ClipTag.query.filter_by(
                    name=tag_name,
                    team_organization_id=team_id
                ).first()
                
                if not existing:
                    new_tag = ClipTag(
                        name=tag_name,
                        category=category,
                        color=color,
                        team_organization_id=team_id,
                        is_active=True
                    )
                    db.session.add(new_tag)
                    created_count += 1
                else:
                    skipped_count += 1
        
        db.session.commit()
        
        flash(f'Created {created_count} new tags. Skipped {skipped_count} existing tags.', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/bulk_create_tags.html')

@bp.route('/tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tag():
    """Add a new clip tag"""
    team_id = get_current_team_id()
    form = ClipTagForm()

    if form.validate_on_submit():
        # Check if tag already exists in this team (by name)
        existing_tag = ClipTag.query.filter_by(
            name=form.name.data,
            team_organization_id=team_id
        ).first()

        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Add Tag')

        # Resolve parent tag (optional, 0 means None)
        parent_id = form.parent_tag_id.data if hasattr(form, 'parent_tag_id') else 0
        if parent_id and parent_id > 0:
            parent = ClipTag.query.filter_by(id=parent_id, team_organization_id=team_id).first()
            parent_tag_id = parent.id if parent else None
        else:
            parent_tag_id = None

        tag = ClipTag(
            name=form.name.data,
            category=form.category.data if hasattr(form, 'category') else None,
            color=form.color.data if hasattr(form, 'color') else None,
            description=form.description.data if hasattr(form, 'description') else None,
            is_active=form.is_active.data if hasattr(form, 'is_active') else True,
            parent_tag_id=parent_tag_id,
            team_organization_id=team_id
        )
        db.session.add(tag)
        db.session.commit()

        flash(f'Tag "{tag.name}" has been added!', 'success')
        return redirect(url_for('clip.tags'))

    return render_template('clip/tag_form.html', form=form, title='Add Tag')


@bp.route('/tags/edit/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_tag(tag_id):
    # Get current team ID
    team_id = get_current_team_id()

    # Filter tag by team
    tag = ClipTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()

    form = ClipTagForm(obj=tag)

    if form.validate_on_submit():
        # Check if tag already exists in this team (same name, different id)
        existing_tag = ClipTag.query.filter(
            ClipTag.name == form.name.data,
            ClipTag.id != tag_id,
            ClipTag.team_organization_id == team_id
        ).first()

        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Edit Tag')

        # Resolve and validate parent tag (optional)
        parent_tag_id = None
        if hasattr(form, 'parent_tag_id'):
            raw_parent_id = form.parent_tag_id.data
            if raw_parent_id and raw_parent_id > 0:
                # Cannot set itself as parent
                if raw_parent_id == tag_id:
                    flash('A tag cannot be its own parent.', 'danger')
                    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')

                potential_parent = ClipTag.query.filter_by(
                    id=raw_parent_id, team_organization_id=team_id
                ).first()

                if not potential_parent:
                    flash('Selected parent tag was not found in your team.', 'danger')
                    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')

                # Check for circular parent relationship by walking up ancestors
                current_check = potential_parent
                while current_check:
                    if current_check.id == tag_id:
                        flash('Cannot set parent tag: This would create a circular relationship!', 'danger')
                        return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')
                    current_check = getattr(current_check, 'parent', None)

                parent_tag_id = potential_parent.id

        # Persist fields
        tag.name = form.name.data
        if hasattr(form, 'category'):
            tag.category = form.category.data
        if hasattr(form, 'color'):
            tag.color = form.color.data
        if hasattr(form, 'description'):
            tag.description = form.description.data
        if hasattr(form, 'is_active'):
            tag.is_active = form.is_active.data
        if hasattr(form, 'parent_tag_id'):
            tag.parent_tag_id = parent_tag_id

        db.session.commit()

        flash(f'Tag "{tag.name}" has been updated!', 'success')
        return redirect(url_for('clip.tags'))

    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')


@bp.route('/tags/delete/<int:tag_id>', methods=['POST'])
@login_required
@admin_required
def delete_tag(tag_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Filter tag by team
    tag = ClipTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    name = tag.name
    
    # Clear relationships
    for clip in tag.clips:
        clip.tags.remove(tag)
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Tag "{name}" has been deleted!', 'success')
    return redirect(url_for('clip.tags'))

# ============================================================================
# AJAX/API ROUTES
# ============================================================================

@bp.route('/get_points/<int:game_id>')
@login_required
def get_points(game_id):
    """AJAX endpoint to get points for a game"""
    team_id = get_current_team_id()
    
    # Verify the game belongs to the current team
    game = Game.query.filter_by(id=game_id, team_organization_id=team_id).first_or_404()
    
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    return jsonify([{'id': p.id, 'name': f'Point {p.point_number}'} for p in points])

@bp.route('/get_game_link/<int:game_id>')
@login_required
def get_game_link(game_id):
    """AJAX endpoint to get YouTube link from game"""
    team_id = get_current_team_id()
    
    # Filter game by team
    game = Game.query.filter_by(id=game_id, team_organization_id=team_id).first_or_404()
    
    return jsonify({
        'youtube_link': game.youtube_link or ''
    })

@bp.route('/api/clip/<int:clip_id>/annotations')
@login_required
def api_get_annotations(clip_id):
    """API endpoint to get all annotations for a clip (JSON)"""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    
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

@bp.route('/<int:clip_id>/share_link', methods=['POST'])
@login_required
def create_share_link(clip_id):
    """
    Create a signed, time-limited share link for a clip's annotations.
    By default expires in 7 days. Adjust by sending form field 'expires_days'.
    """
    # Only allow admins/coaches or the clip creator to create share links
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()

    if not (current_user.is_admin or getattr(current_user, 'is_coach', False) or clip.created_by_id == current_user.id):
        return jsonify({'error': 'Not authorized'}), 403

    try:
        expires_days = int(request.form.get('expires_days', 7))
        expires_days = max(1, min(90, expires_days))  # clamp between 1 and 90 days
    except (ValueError, TypeError):
        expires_days = 7

    payload = {
        'clip_id': clip.id,
        'team_id': team_id,
        'exp': int(time.time()) + expires_days * 86400  # unix timestamp expiry
    }
    s = get_share_serializer()
    token = s.dumps(payload)

    share_url = url_for('clip.shared_clip_view', token=token, _external=True)
    return jsonify({'url': share_url, 'expires_days': expires_days})


@bp.route('/share/<token>')
def shared_clip_view(token):
    """
    Public, read-only view of a clip and its annotations, accessible via signed token.
    No login required.
    """
    s = get_share_serializer()
    try:
        data = s.loads(token)
    except BadSignature:
        return render_template('errors/share_invalid.html'), 400

    # Check expiry
    if int(time.time()) > int(data.get('exp', 0)):
        return render_template('errors/share_expired.html'), 410

    clip_id = data.get('clip_id')
    team_id = data.get('team_id')
    if not clip_id or not team_id:
        return render_template('errors/share_invalid.html'), 400

    # Enforce team scoping
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()

    # Which annotations to show:
    # If you have a 'public' visibility option, uncomment to show only public:
    # annotations = (ClipAnnotation.query
    #                .filter_by(clip_id=clip.id, visibility='public')
    #                .order_by(ClipAnnotation.timestamp).all())

    # Otherwise, show all annotations for now (read-only). You can refine later.
    annotations = (ClipAnnotation.query
                   .filter_by(clip_id=clip.id)
                   .order_by(ClipAnnotation.timestamp).all())

    # Build an embed URL for YouTube/Veo if possible
    embed_url = None
    if clip.youtube_link:
        yt_id = extract_youtube_id(clip.youtube_link)
        if yt_id:
            embed_url = f"https://www.youtube.com/embed/{yt_id}"
    elif clip.video_source == 'veo' and clip.youtube_link:
        # If you store Veo links in youtube_link field or another, adapt as needed
        try:
            embed_url = get_veo_embed_url(clip.youtube_link)
        except Exception:
            embed_url = None

    # Human-readable expiry
    expires_at = datetime.fromtimestamp(int(data['exp']))

    return render_template(
        'clip/shared_clip.html',
        clip=clip,
        annotations=annotations,
        embed_url=embed_url,
        expires_at=expires_at,
        seconds_to_timestamp=seconds_to_timestamp  # pass helper for formatting
    )


@bp.route('/export_annotations_md/<int:clip_id>')
@login_required
def export_annotations_markdown(clip_id):
    """
    Export annotations as Markdown for easy sharing/pasting.
    """
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()

    annotations = (ClipAnnotation.query
                   .filter_by(clip_id=clip.id)
                   .order_by(ClipAnnotation.timestamp).all())

    lines = []
    lines.append(f"# {clip.title}")
    if clip.game:
        g_date = clip.game.date.strftime('%Y-%m-%d') if clip.game.date else ''
        lines.append(f"- Game: vs {clip.game.opponent}{f' ({g_date})' if g_date else ''}")
    if clip.point:
        lines.append(f"- Point: {clip.point.point_number}")
    if clip.youtube_link:
        lines.append(f"- Video: {clip.youtube_link}")
    lines.append("")  # blank line
    lines.append("## Annotations")
    lines.append("")

    for a in annotations:
        ts = seconds_to_timestamp(a.timestamp)
        title = a.title or ''
        event = (a.event_type.replace('_', ' ').title() if a.event_type else '')
        tags_str = ', '.join([t.name for t in a.tags]) if a.tags else ''
        players_str = ', '.join([p.name for p in a.players]) if a.players else ''
        creator = a.created_by.username if a.created_by else 'Unknown'
        key = " ⭐" if a.is_key_moment else ""
        notes = a.notes or ""

        lines.append(f"- [{ts}] {title}{key}")
        meta_bits = []
        if event: meta_bits.append(event)
        if tags_str: meta_bits.append(f"Tags: {tags_str}")
        if players_str: meta_bits.append(f"Players: {players_str}")
        meta_bits.append(f"By: {creator}")
        lines.append(f"  - " + " | ".join(meta_bits))
        if notes:
            # indent notes as a block
            for line in notes.splitlines():
                lines.append(f"  > {line}")
        lines.append("")  # blank line between annotations

    md = "\n".join(lines)
    return current_app.response_class(md, mimetype='text/markdown')


# ============================================================================
# EXPORT ROUTES
# ============================================================================

@bp.route('/export_annotations_csv/<int:clip_id>')
@login_required
def export_annotations_csv(clip_id):
    """Export clip annotations to CSV"""
    team_id = get_current_team_id()
    
    # Filter clip by team
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    
    annotations = ClipAnnotation.query.filter_by(clip_id=clip.id).order_by(ClipAnnotation.timestamp).all()
    
    # Create a file-like buffer
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    
    # Write header with clip information
    writer.writerow(['Clip Information'])
    writer.writerow(['Title', clip.title])
    
    if clip.game:
        writer.writerow(['Game', f'vs {clip.game.opponent}'])
        if clip.game.date:
            writer.writerow(['Date', clip.game.date.strftime('%Y-%m-%d')])
    
    if clip.point:
        writer.writerow(['Point', clip.point.point_number])
    
    writer.writerow(['Video Link', clip.youtube_link])
    writer.writerow([])  # Empty row as separator
    
    # Write annotations header
    writer.writerow(['Timestamp', 'Title', 'Event Type', 'Our Score', 'Their Score', 
                    'Offense', 'Defense', 'Tags', 'Players', 'Creator', 'Key Moment', 'Notes'])
    
    # Write annotation data
    for annotation in annotations:
        # Format offense for display
        offense_display = ""
        if annotation.offense == 'horo':
            offense_display = "Horizontal"
        elif annotation.offense == 'vert':
            offense_display = "Vertical"
        elif annotation.offense == 'flow':
            offense_display = "Flow"
        else:
            offense_display = annotation.offense or ""
            
        # Format defense for display
        defense_display = ""
        if annotation.defense == 'match_flick':
            defense_display = "Match Flick"
        elif annotation.defense == 'match_backhand':
            defense_display = "Match Backhand"
        elif annotation.defense == 'match_middle':
            defense_display = "Match Middle"
        elif annotation.defense == 'zone':
            defense_display = "Zone"
        else:
            defense_display = annotation.defense or ""
        
        # Get tags
        tags_str = ', '.join([tag.name for tag in annotation.tags]) if annotation.tags else ''
        
        # Get players
        players_str = ', '.join([f"{p.name} (#{p.jersey_number})" for p in annotation.players]) if annotation.players else ''
        
        # Get creator
        creator = annotation.created_by.username if annotation.created_by else 'Unknown'
        
        writer.writerow([
            seconds_to_timestamp(annotation.timestamp),
            annotation.title or '',
            annotation.event_type.replace('_', ' ').title() if annotation.event_type else '',
            annotation.our_score or '',
            annotation.their_score or '',
            offense_display,
            defense_display,
            tags_str,
            players_str,
            creator,
            'Yes' if annotation.is_key_moment else 'No',
            annotation.notes or ""
        ])
    
    # Move to beginning of file
    buffer.seek(0)
    
    # Create filename with clip title (sanitized) and date
    safe_title = re.sub(r'[^\w\s-]', '', clip.title).strip().replace(' ', '_')
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"{safe_title}_{date_str}_annotations.csv"
    
    return send_file(
        io.BytesIO(buffer.getvalue().encode()),
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )

# ============================================================================
# ANNOTATION TAG MANAGEMENT ROUTES
# ============================================================================

@bp.route('/annotation-tags')
@login_required
@admin_required
def annotation_tags():
    """View all annotation tags"""
    team_id = get_current_team_id()
    tags = AnnotationTag.query.filter_by(team_organization_id=team_id).order_by(
        AnnotationTag.category, AnnotationTag.name
    ).all()
    return render_template('clip/annotation_tags.html', tags=tags)

@bp.route('/annotation-tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_annotation_tag():
    """Add a new annotation tag"""
    from app.forms.annotation import AnnotationTagForm
    team_id = get_current_team_id()
    form = AnnotationTagForm()
    
    # Filter parent tag choices to only show tags from current team
    form.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
        (t.id, t.full_path) for t in AnnotationTag.query.filter_by(
            team_organization_id=team_id,
            is_active=True
        ).order_by(AnnotationTag.name).all()
    ]
    
    if form.validate_on_submit():
        # Check if tag already exists in this team
        existing_tag = AnnotationTag.query.filter_by(
            name=form.name.data,
            team_organization_id=team_id
        ).first()
        
        if existing_tag:
            flash(f'Annotation tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/annotation_tag_form.html', form=form, title='Add Annotation Tag')
        
        tag = AnnotationTag(
            name=form.name.data,
            category=form.category.data,
            parent_tag_id=form.parent_tag_id.data if form.parent_tag_id.data > 0 else None,
            color=form.color.data,
            description=form.description.data,
            is_active=form.is_active.data,
            team_organization_id=team_id
        )
        db.session.add(tag)
        db.session.commit()
        
        flash(f'Annotation tag "{tag.name}" has been added!', 'success')
        return redirect(url_for('clip.annotation_tags'))
    
    return render_template('clip/annotation_tag_form.html', form=form, title='Add Annotation Tag')

@bp.route('/annotation-tags/edit/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_annotation_tag(tag_id):
    """Edit an annotation tag"""
    from app.forms.annotation import AnnotationTagForm
    team_id = get_current_team_id()
    tag = AnnotationTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    form = AnnotationTagForm(obj=tag)
    
    # Filter parent tag choices to only show tags from current team (excluding self)
    form.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
        (t.id, t.full_path) for t in AnnotationTag.query.filter(
            AnnotationTag.team_organization_id == team_id,
            AnnotationTag.is_active == True,
            AnnotationTag.id != tag_id  # Don't allow tag to be its own parent
        ).order_by(AnnotationTag.name).all()
    ]
    
    if request.method == 'GET':
        # Pre-populate form with existing data
        if tag.parent_tag_id:
            form.parent_tag_id.data = tag.parent_tag_id
        else:
            form.parent_tag_id.data = 0
    
    if form.validate_on_submit():
        # Check if tag name already exists in this team (excluding current tag)
        existing_tag = AnnotationTag.query.filter(
            AnnotationTag.name == form.name.data,
            AnnotationTag.id != tag_id,
            AnnotationTag.team_organization_id == team_id
        ).first()
        
        if existing_tag:
            flash(f'Annotation tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')
        
        # Check for circular parent relationship
        parent_id = form.parent_tag_id.data if form.parent_tag_id.data > 0 else None
        if parent_id:
            # Check if the new parent is actually a descendant of this tag
            potential_parent = AnnotationTag.query.get(parent_id)
            current_check = potential_parent
            while current_check:
                if current_check.id == tag_id:
                    flash('Cannot set parent tag: This would create a circular relationship!', 'danger')
                    return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')
                current_check = current_check.parent
        
        tag.name = form.name.data
        tag.category = form.category.data
        tag.parent_tag_id = parent_id
        tag.color = form.color.data
        tag.description = form.description.data
        tag.is_active = form.is_active.data
        
        db.session.commit()
        
        flash(f'Annotation tag "{tag.name}" has been updated!', 'success')
        return redirect(url_for('clip.annotation_tags'))
    
    return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')

@bp.route('/annotation-tags/delete/<int:tag_id>', methods=['POST'])
@login_required
@admin_required
def delete_annotation_tag(tag_id):
    """Delete an annotation tag"""
    team_id = get_current_team_id()
    tag = AnnotationTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    name = tag.name
    
    # Clear relationships with annotations
    for annotation in tag.annotations:
        annotation.tags.remove(tag)
    
    # Update child tags to have no parent
    for child in tag.children:
        child.parent_tag_id = None
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Annotation tag "{name}" has been deleted!', 'success')
    return redirect(url_for('clip.annotation_tags'))

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def extract_youtube_id(url):
    """Extract YouTube video ID from URL."""
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
        return "00:00:00"
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    secs = int(seconds) % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def timestamp_to_seconds(timestamp):
    """Convert HH:MM:SS format to seconds"""
    if not timestamp:
        return None
    try:
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

def validate_veo_link(url):
    """Validate Veo video URL"""
    veo_pattern = r'https?://app\.veo\.co/matches/[a-zA-Z0-9-]+'
    return bool(re.match(veo_pattern, url))

def get_veo_embed_url(url):
    """Convert Veo URL to embed URL"""
    match_id = url.split('matches/')[1]
    return f'https://app.veo.co/embed/{match_id}'