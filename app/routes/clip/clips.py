"""Clip library pages: browsing, adding, editing, hiding and point segments."""

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app import db
from app.forms.clip import ClipFilterForm, ClipForm
from app.models import Clip, ClipAnnotation, ClipTag
from app.models.clip import ClipPointSegment
from app.models.clip_playlist import ClipPlaylist
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point
from app.models.user import User
from app.routes.clip import bp
from app.routes.clip.helpers import get_clip_or_404, sees_hidden_clips, visible_annotations
from app.utils.clip_video import check_link
from app.utils.team_filter import get_current_team_id
from app.utils.utils import admin_required


CLIPS_PER_PAGE = 24


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
    search = request.args.get('q', default='', type=str).strip()
    page = request.args.get('page', default=1, type=int)

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

    if search:
        escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        like = f'%{escaped}%'
        query = query.filter(or_(Clip.title.ilike(like, escape='\\'),
                                 Clip.description.ilike(like, escape='\\')))

    # Priority key: flagged for sharing floats to top (0), hidden sinks to bottom (2), rest in middle (1).
    # This is always applied as the primary sort so admins get a clear grouped view.
    from sqlalchemy import case as sa_case
    priority_key = sa_case(
        (Clip.is_flagged_for_sharing == True, 0),
        (Clip.is_hidden == True, 2),
        else_=1
    )

    # Apply sorting — priority key always leads, user-chosen sort is the tiebreaker
    if sort_by == 'created_desc':
        query = query.order_by(priority_key, Clip.created_at.desc())
    elif sort_by == 'created_asc':
        query = query.order_by(priority_key, Clip.created_at.asc())
    elif sort_by == 'title_asc':
        query = query.order_by(priority_key, Clip.title.asc())
    elif sort_by == 'views_desc':
        query = query.order_by(priority_key, Clip.view_count.desc())
    elif sort_by == 'annotations_desc':
        # Sort by annotation count, still respecting priority grouping
        query = (query
                 .outerjoin(ClipAnnotation)
                 .group_by(Clip.id)
                 .order_by(priority_key, func.count(ClipAnnotation.id).desc()))
    else:
        # Fallback default
        query = query.order_by(priority_key, Clip.created_at.desc())

    # Non-admins and non-coaches never see hidden clips
    if not sees_hidden_clips():
        query = query.filter(Clip.is_hidden == False)

    # Get clips
    query = query.options(selectinload(Clip.tags), selectinload(Clip.game))
    pagination = query.paginate(page=page, per_page=CLIPS_PER_PAGE, error_out=False)
    clips = pagination.items

    # Annotation and key-moment counts for this page's cards, in one query
    counts = dict.fromkeys([c.id for c in clips], (0, 0))
    if clips:
        counts.update({
            clip_id: (total, key or 0) for clip_id, total, key in
            db.session.query(ClipAnnotation.clip_id, func.count(ClipAnnotation.id),
                             func.sum(sa_case((ClipAnnotation.is_key_moment == True, 1), else_=0)))
            .filter(ClipAnnotation.clip_id.in_(counts))
            .group_by(ClipAnnotation.clip_id)
        })

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
                    ClipTag.is_active == True,
                    or_(Clip.is_hidden == False, sees_hidden_clips())
                 )
                 .group_by(ClipTag.id)
                 .order_by(ClipTag.category, func.count(clip_tag_relation.c.clip_id).desc())
                 .all())

    return render_template(
        'clip/index.html',
        clips=clips,
        pagination=pagination,
        counts=counts,
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
            'sort_by': sort_by,
            'q': search
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
    query = Clip.query.filter_by(game_id=game_id, team_organization_id=team_id)
    if not sees_hidden_clips():
        query = query.filter(Clip.is_hidden == False)
    clips = query.order_by(Clip.created_at.desc()).all()
    
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
    query = Clip.query.filter_by(point_id=point_id, team_organization_id=team_id)
    if not sees_hidden_clips():
        query = query.filter(Clip.is_hidden == False)
    clips = query.order_by(Clip.created_at.desc()).all()
    
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
            is_featured=form.is_featured.data,
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


def clip_feedback(clip, team_id):
    """Coaches' notes about this clip, for its Feedback tab. The clip's own
    players come first in the picker."""
    if not current_user.is_coach:
        return {}
    from app.models.feedback import PlayerFeedback
    in_clip = {p.id for p in clip.players}
    players = Player.query.filter_by(team_organization_id=team_id, active=True).all()
    players.sort(key=lambda p: (p.id not in in_clip, p.name))
    notes = (PlayerFeedback.query.filter_by(clip_id=clip.id)
             .order_by(PlayerFeedback.created_at.desc()).all())
    return {'clip_notes': notes, 'note_players': players,
            'feedback_tags': PlayerFeedback.CONTEXT_TAGS}


@bp.route('/<int:clip_id>')
@login_required
def view_clip(clip_id):
    """View a single clip with all annotations"""
    team_id = get_current_team_id()
    clip = get_clip_or_404(clip_id)

    # Count a view once per visitor session, not on every reload or filter change
    viewed = session.get('viewed_clips', [])
    if clip.id not in viewed:
        clip.view_count = (clip.view_count or 0) + 1
        db.session.commit()
        session['viewed_clips'] = (viewed + [clip.id])[-50:]
    
    query = visible_annotations(ClipAnnotation.query.filter_by(clip_id=clip_id))
    
    # Apply request filters
    event_filter = request.args.get('event_filter')
    if event_filter:
        query = query.filter_by(event_type=event_filter)
    
    creator_filter = request.args.get('creator_filter', type=int)
    if creator_filter:
        query = query.filter_by(user_id=creator_filter)
    
    key_only = request.args.get('key_only')
    if key_only:
        query = query.filter_by(is_key_moment=True)
    
    annotations = query.order_by(ClipAnnotation.timestamp).all()
    
    # Get list of users who have created annotations for filter dropdown
    annotation_creators = db.session.query(User).join(
        ClipAnnotation, User.id == ClipAnnotation.user_id
    ).filter(ClipAnnotation.clip_id == clip_id).distinct().all()

    # Annotation form (rendered inline in the offcanvas on this page)
    from app.forms.annotation import AnnotationForm
    ann_form = AnnotationForm()

    # Team users list — used in the offcanvas "specific player" selector
    team_users = (User.query
                  .filter_by(team_organization_id=team_id)
                  .order_by(User.username)
                  .all())

    playlists = []
    if sees_hidden_clips():
        playlists = (ClipPlaylist.query.filter_by(team_organization_id=team_id)
                     .order_by(ClipPlaylist.updated_at.desc()).all())

    return render_template('clip/view_clip.html',
                         clip=clip,
                         playlists=playlists,
                         annotations=annotations,
                         annotation_creators=annotation_creators,
                         ann_form=ann_form,
                         team_users=team_users,
                         **clip_feedback(clip, team_id))


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
    
    if form.validate_on_submit():
        clip.title = form.title.data
        clip.game_id = form.game_id.data if form.game_id.data and form.game_id.data > 0 else None
        clip.point_id = form.point_id.data if form.point_id.data and form.point_id.data > 0 else None
        clip.video_source = form.video_source.data
        clip.youtube_link = form.youtube_link.data
        clip.start_time = form.start_time.data
        clip.end_time = form.end_time.data
        clip.description = form.description.data
        clip.is_featured = form.is_featured.data
        
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
    clip = get_clip_or_404(clip_id)
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
    Clip.query.filter_by(id=clip_id, team_organization_id=get_current_team_id()).first_or_404()
    seg = ClipPointSegment.query.filter_by(id=segment_id, clip_id=clip_id).first_or_404()
    db.session.delete(seg)
    db.session.commit()
    return ('', 204)


@bp.route('/<int:clip_id>/segments/<string:action>', methods=['POST'])
@login_required
def mark_segment(clip_id, action):
    if not (current_user.is_admin or current_user.is_coach):
        abort(403)
    clip = get_clip_or_404(clip_id)
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


@bp.route('/<int:clip_id>/toggle_hidden', methods=['POST'])
@login_required
@admin_required
def toggle_hidden(clip_id):
    """Admin: toggle visibility of a clip from players."""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    clip.is_hidden = not clip.is_hidden
    db.session.commit()
    state = 'hidden' if clip.is_hidden else 'visible'
    flash(f'Clip "{clip.title}" is now {state}.', 'info')
    return redirect(url_for('clip.view_clip', clip_id=clip_id))


@bp.route('/<int:clip_id>/toggle_share_flag', methods=['POST'])
@login_required
@admin_required
def toggle_share_flag(clip_id):
    """Admin: flag/unflag a clip as ready to share externally."""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    clip.is_flagged_for_sharing = not clip.is_flagged_for_sharing
    db.session.commit()
    state = 'flagged for sharing' if clip.is_flagged_for_sharing else 'unflagged'
    flash(f'Clip "{clip.title}" has been {state}.', 'info')
    return redirect(url_for('clip.view_clip', clip_id=clip_id))


@bp.route('/get_points/<int:game_id>')
@login_required
def get_points(game_id):
    """AJAX endpoint to get points for a game"""
    team_id = get_current_team_id()
    
    # Verify the game belongs to the current team
    game = Game.query.filter_by(id=game_id, team_organization_id=team_id).first_or_404()
    
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    return jsonify([{'id': p.id, 'name': f'Point {p.point_number}'} for p in points])


@bp.route('/check_link')
@login_required
def check_video_link():
    """AJAX: can this link be played, and with what player (clip form preview)."""
    return jsonify(check_link(request.args.get('source', 'youtube'), request.args.get('url', '')))

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
