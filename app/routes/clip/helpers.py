"""Who can see which clips and annotations."""
from flask import abort
from flask_login import current_user
from sqlalchemy import or_

from app.models import Clip, ClipAnnotation
from app.utils.team_filter import get_current_team_id


def sees_hidden_clips():
    """Admins and coaches see clips hidden from players, and every annotation."""
    return current_user.is_admin or current_user.is_coach


def get_clip_or_404(clip_id):
    """Return clip only if it belongs to the current user's team and, for
    players, isn't hidden."""
    team_id = get_current_team_id()
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    if clip.is_hidden and not sees_hidden_clips():
        abort(404)
    return clip


def visible_annotations(query):
    """Narrow an annotation query to what the current user may see: coaches see
    everything; players see team notes, their own, and ones aimed at them."""
    if sees_hidden_clips():
        return query
    return query.filter(or_(
        ClipAnnotation.visibility == 'team',
        ClipAnnotation.user_id == current_user.id,
        (ClipAnnotation.visibility == 'specific') & (ClipAnnotation.target_user_id == current_user.id)
    ))
