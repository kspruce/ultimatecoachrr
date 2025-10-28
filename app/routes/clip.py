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

bp = Blueprint('clip', __name__, url_prefix='/clips')

# Helper function to get current team ID
def get_current_team_id():
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

# ============================================================================
# CLIP ROUTES
# ============================================================================

@bp.route('/')
@login_required
def index():
    form = ClipFilterForm()
    delete_form = FlaskForm()

    # Get filter parameters
    game_id = request.args.get('game_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    player_id = request.args.get('player_id', type=int)

    # Get current team ID
    team_id = get_current_team_id()

    # Build query based on filters
    query = Clip.query.filter_by(team_organization_id=team_id)

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
    """View all clip tags"""
    team_id = get_current_team_id()
    tags = ClipTag.query.filter_by(team_organization_id=team_id).order_by(ClipTag.category, ClipTag.name).all()
    return render_template('clip/tags.html', tags=tags)

@bp.route('/tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tag():
    """Add a new clip tag"""
    team_id = get_current_team_id()
    form = ClipTagForm()
    
    if form.validate_on_submit():
        # Check if tag already exists in this team
        existing_tag = ClipTag.query.filter_by(
            name=form.name.data,
            team_organization_id=team_id
        ).first()
        
        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Add Tag')
        
        tag = ClipTag(
            name=form.name.data,
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
        # Check if tag already exists in this team
        existing_tag = ClipTag.query.filter(
            ClipTag.name == form.name.data,
            ClipTag.id != tag_id,
            ClipTag.team_organization_id == team_id
        ).first()
        
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