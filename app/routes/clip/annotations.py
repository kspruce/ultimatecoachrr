"""Annotations on a clip."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.annotation import AnnotationForm
from app.models import Clip, ClipAnnotation
from app.models.annotation import AnnotationTag
from app.models.player import Player
from app.models.user import User
from app.models.team_membership import TeamMembership
from app.routes.clip import bp
from app.routes.clip.helpers import get_clip_or_404, sees_hidden_clips, visible_annotations
from app.utils.team_filter import get_current_team_id


@bp.route('/<int:clip_id>/annotation/add', methods=['GET', 'POST'])
@login_required
def add_annotation(clip_id):
    """Add a new annotation to a clip"""
    team_id = get_current_team_id()
    clip = get_clip_or_404(clip_id)
    form = AnnotationForm()
    
    # Prefill from query param t
    t = request.args.get('t', type=int)
    if t is not None and (form.timestamp.data is None or form.timestamp.data == 0):
        form.timestamp.data = t
    
    if form.validate_on_submit():
        # Clamp visibility: only coaches/admins may set 'coaches' or 'specific'
        requested_visibility = form.visibility.data
        is_coach_or_admin = current_user.is_admin or getattr(current_user, 'is_coach', False)
        if requested_visibility in ('coaches', 'specific') and not is_coach_or_admin:
            requested_visibility = 'team'

        # Resolve target_user_id — read directly from request.form (not WTForms)
        target_user_id = None
        if requested_visibility == 'specific':
            raw_target = request.form.get('target_user_id', 0, type=int)
            if raw_target and raw_target > 0:
                target_u = User.query.filter(User.id == raw_target, User.memberships.any(TeamMembership.team_organization_id == team_id)).first()
                target_user_id = target_u.id if target_u else None
            if not target_user_id:
                # Fallback: treat as coaches-only if no valid target selected
                requested_visibility = 'coaches'

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
            visibility=requested_visibility,
            target_user_id=target_user_id,
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

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'success': True})

        flash('Annotation added successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    team_users = User.query.filter(User.memberships.any(TeamMembership.team_organization_id == team_id)).order_by(User.username).all()
    return render_template('clip/add_annotation.html', form=form, clip=clip, team_users=team_users)


@bp.route('/annotation/<int:annotation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_annotation(annotation_id):
    """Edit an existing annotation"""
    team_id = get_current_team_id()
    # Verify the annotation belongs to a clip owned by this team
    annotation = (ClipAnnotation.query
                  .join(Clip, Clip.id == ClipAnnotation.clip_id)
                  .filter(ClipAnnotation.id == annotation_id,
                          Clip.team_organization_id == team_id)
                  .first_or_404())
    if annotation.clip.is_hidden and not sees_hidden_clips():
        abort(404)

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
        # Clamp visibility: only coaches/admins may set 'coaches' or 'specific'
        requested_visibility = form.visibility.data
        is_coach_or_admin = current_user.is_admin or getattr(current_user, 'is_coach', False)
        if requested_visibility in ('coaches', 'specific') and not is_coach_or_admin:
            requested_visibility = 'team'

        # Resolve target_user_id — read directly from request.form (not WTForms)
        target_user_id = annotation.target_user_id  # preserve existing by default
        if requested_visibility == 'specific':
            raw_target = request.form.get('target_user_id', 0, type=int)
            if raw_target and raw_target > 0:
                target_u = User.query.filter(User.id == raw_target, User.memberships.any(TeamMembership.team_organization_id == team_id)).first()
                target_user_id = target_u.id if target_u else None
            if not target_user_id:
                requested_visibility = 'coaches'
        else:
            target_user_id = None  # clear when switching away from 'specific'

        annotation.target_user_id = target_user_id
        annotation.timestamp = form.timestamp.data
        annotation.title = form.title.data
        annotation.event_type = form.event_type.data
        annotation.our_score = form.our_score.data
        annotation.their_score = form.their_score.data
        annotation.offense = form.offense.data
        annotation.defense = form.defense.data
        annotation.notes = form.notes.data
        annotation.is_key_moment = form.is_key_moment.data
        annotation.visibility = requested_visibility
        
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
    
    team_users = User.query.filter(User.memberships.any(TeamMembership.team_organization_id == team_id)).order_by(User.username).all()
    return render_template('clip/edit_annotation.html', form=form, annotation=annotation, team_users=team_users)


@bp.route('/annotation/<int:annotation_id>/delete', methods=['POST'])
@login_required
def delete_annotation(annotation_id):
    """Delete an annotation"""
    team_id = get_current_team_id()
    # Verify the annotation belongs to a clip owned by this team
    annotation = (ClipAnnotation.query
                  .join(Clip, Clip.id == ClipAnnotation.clip_id)
                  .filter(ClipAnnotation.id == annotation_id,
                          Clip.team_organization_id == team_id)
                  .first_or_404())
    if annotation.clip.is_hidden and not sees_hidden_clips():
        abort(404)

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


@bp.route('/api/clip/<int:clip_id>/annotations')
@login_required
def api_get_annotations(clip_id):
    """API endpoint to get all annotations for a clip (JSON)"""
    get_clip_or_404(clip_id)

    ann_query = visible_annotations(ClipAnnotation.query.filter_by(clip_id=clip_id))
    annotations = ann_query.all()

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
