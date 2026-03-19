# app/routes/feedback.py
from flask import (
    Blueprint, abort, render_template, redirect, url_for,
    flash, request, jsonify
)
from flask_login import login_required, current_user
from app import db
from app.models.session import SessionPlan, Attendance, SessionRSVP
from app.models.player import Player
from app.models.feedback import PlayerFeedback

bp = Blueprint('feedback', __name__)


def _require_admin():
    """Abort with 403 if the current user is not an admin."""
    if not current_user.is_admin:
        abort(403)


# ── Quick-capture page ───────────────────────────────────────────────────────

@bp.route('/sessions/<int:session_id>/feedback/quick')
@login_required
def quick_capture(session_id):
    _require_admin()

    session_obj = SessionPlan.query.get_or_404(session_id)

    # Collect players via attendance records *and* 'attending' RSVPs
    attended_ids = {
        a.player_id
        for a in session_obj.attendances.all()
    }
    rsvp_yes_ids = {
        r.player_id
        for r in session_obj.rsvps.filter_by(status='attending').all()
    }
    all_player_ids = attended_ids | rsvp_yes_ids

    if all_player_ids:
        players = (
            Player.query
            .filter(Player.id.in_(all_player_ids))
            .order_by(Player.name)
            .all()
        )
    else:
        players = []

    # Pre-compute per-player note counts for this session
    feedback_counts: dict[int, int] = {}
    for fb in PlayerFeedback.query.filter_by(session_id=session_id).all():
        feedback_counts[fb.player_id] = feedback_counts.get(fb.player_id, 0) + 1

    return render_template(
        'feedback/quick_capture.html',
        session=session_obj,
        players=players,
        feedback_counts=feedback_counts,
        context_tags=PlayerFeedback.CONTEXT_TAGS,
    )


# ── AJAX save endpoint ───────────────────────────────────────────────────────

@bp.route('/sessions/<int:session_id>/feedback/save', methods=['POST'])
@login_required
def save_feedback(session_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    # Verify session exists
    session_obj = SessionPlan.query.get_or_404(session_id)

    data = request.get_json(silent=True) or {}
    player_id = data.get('player_id')
    content = (data.get('content') or '').strip()
    context_tag = (data.get('context_tag') or 'General').strip()

    if not player_id:
        return jsonify({'success': False, 'message': 'player_id is required'}), 400
    if not content:
        return jsonify({'success': False, 'message': 'Note content cannot be empty'}), 400
    if context_tag not in PlayerFeedback.CONTEXT_TAGS:
        context_tag = 'General'

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    fb = PlayerFeedback(
        player_id=player_id,
        coach_id=current_user.id,
        session_id=session_id,
        content=content,
        context_tag=context_tag,
    )
    db.session.add(fb)
    db.session.commit()

    note_count = PlayerFeedback.query.filter_by(
        session_id=session_id,
        player_id=player_id
    ).count()

    return jsonify({
        'success': True,
        'note_count': note_count,
        'feedback_id': fb.id,
    })


# ── Full feedback view (per player) ─────────────────────────────────────────

@bp.route('/players/<int:player_id>/feedback')
@login_required
def player_feedback(player_id):
    _require_admin()

    player = Player.query.get_or_404(player_id)

    entries = (
        PlayerFeedback.query
        .filter_by(player_id=player_id)
        .order_by(PlayerFeedback.created_at.desc())
        .all()
    )

    return render_template(
        'feedback/player_feedback.html',
        player=player,
        entries=entries,
    )


# ── Delete a single feedback entry ───────────────────────────────────────────

@bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
def delete_feedback(feedback_id):
    _require_admin()

    fb = PlayerFeedback.query.get_or_404(feedback_id)
    player_id = fb.player_id
    db.session.delete(fb)
    db.session.commit()

    flash('Feedback note deleted.', 'success')
    return redirect(url_for('feedback.player_feedback', player_id=player_id))
