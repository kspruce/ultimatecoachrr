# app/routes/feedback.py
from datetime import datetime

from flask import (
    Blueprint, abort, render_template, redirect, url_for,
    flash, request, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models.session import SessionPlan
from app.models.player import Player
from app.models.feedback import PlayerFeedback
from app.models.clip import Clip
from app.models.game import Game
from app.utils.team_filter import get_current_team_id, team_row_or_404

bp = Blueprint('feedback', __name__)


def _require_coach():
    """Abort with 403 unless the current user is a coach or admin."""
    if not current_user.is_coach:
        abort(403)


def _safe_next(target, fallback):
    """Only ever redirect back to a page on this site."""
    if target and target.startswith(request.host_url):
        target = '/' + target[len(request.host_url):]
    if target and target.startswith('/') and not target.startswith(('//', '/\\')):
        return target
    return fallback


def _team_feedback():
    """The current team's feedback notes (they belong to the team through
    the player)."""
    return (PlayerFeedback.query.join(Player, PlayerFeedback.player_id == Player.id)
            .filter(Player.team_organization_id == get_current_team_id()))


def _team_row_id(model, raw):
    """The id of one of the team's rows, or None."""
    try:
        row_id = int(raw)
    except (TypeError, ValueError):
        return None
    row = model.query.filter_by(id=row_id, team_organization_id=get_current_team_id()).first()
    return row.id if row else None


def unseen_count(user):
    """Shared notes the signed-in player hasn't opened yet."""
    player = user.player if user.is_authenticated else None
    if player is None:
        return 0
    return PlayerFeedback.query.filter_by(player_id=player.id, shared=True, seen_at=None).count()


@bp.app_context_processor
def feedback_nav():
    return {'unseen_feedback_count': lambda: unseen_count(current_user)}


# ── Feedback Hub ─────────────────────────────────────────────────────────────

@bp.route('/feedback/')
@login_required
def hub():
    _require_coach()

    team_id = get_current_team_id()

    # Recent sessions for this team — most recent first, up to 8
    recent_sessions = (
        SessionPlan.query
        .filter_by(team_organization_id=team_id)
        .order_by(SessionPlan.date.desc().nullslast(), SessionPlan.created_at.desc())
        .limit(8)
        .all()
    )

    # Active players for this team ordered by name
    players = (
        Player.query
        .filter_by(active=True, team_organization_id=team_id)
        .order_by(Player.name)
        .all()
    )

    # Aggregate feedback counts per player (all time)
    team_notes = (db.session.query(PlayerFeedback)
                  .join(Player, PlayerFeedback.player_id == Player.id)
                  .filter(Player.team_organization_id == team_id))
    player_counts: dict[int, int] = dict(
        team_notes.with_entities(PlayerFeedback.player_id, func.count(PlayerFeedback.id))
        .group_by(PlayerFeedback.player_id)
        .all()
    )

    # Per-session note counts (so we can show "X notes" on each session card)
    session_counts: dict[int, int] = dict(
        team_notes.with_entities(PlayerFeedback.session_id, func.count(PlayerFeedback.id))
        .filter(PlayerFeedback.session_id.isnot(None))
        .group_by(PlayerFeedback.session_id)
        .all()
    )

    return render_template(
        'feedback/hub.html',
        recent_sessions=recent_sessions,
        players=players,
        player_counts=player_counts,
        session_counts=session_counts,
    )


# ── Quick-capture page ───────────────────────────────────────────────────────

@bp.route('/sessions/<int:session_id>/feedback/quick')
@login_required
def quick_capture(session_id):
    _require_coach()

    session_obj = team_row_or_404(SessionPlan, session_id)

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

    team_id = get_current_team_id()

    if all_player_ids:
        players = (
            Player.query
            .filter(
                Player.id.in_(all_player_ids),
                Player.team_organization_id == team_id
            )
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
    if not current_user.is_coach:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    # Verify session exists
    session_obj = team_row_or_404(SessionPlan, session_id)

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

    player = Player.query.filter_by(id=player_id, team_organization_id=get_current_team_id()).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    fb = PlayerFeedback(
        player_id=player.id,
        coach_id=current_user.id,
        session_id=session_id,
        content=content,
        context_tag=context_tag,
        shared=bool(data.get('shared')),
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
    _require_coach()

    player = team_row_or_404(Player, player_id)

    entries = (
        PlayerFeedback.query
        .filter_by(player_id=player_id)
        .order_by(PlayerFeedback.created_at.desc())
        .all()
    )
    games = (Game.query.filter_by(team_organization_id=get_current_team_id())
             .order_by(Game.date.desc().nullslast(), Game.id.desc()).limit(30).all())

    return render_template(
        'feedback/player_feedback.html',
        player=player,
        entries=entries,
        games=games,
        context_tags=PlayerFeedback.CONTEXT_TAGS,
        game_id=request.args.get('game_id', type=int),
    )


# ── Add a note from any page (player page, game, clip) ───────────────────────

@bp.route('/players/<int:player_id>/feedback/add', methods=['POST'])
@login_required
def add_feedback(player_id):
    _require_coach()

    player = team_row_or_404(Player, player_id)
    back = _safe_next(request.form.get('next'), url_for('feedback.player_feedback', player_id=player.id))
    content = (request.form.get('content') or '').strip()
    if not content:
        flash('Write a note first.', 'warning')
        return redirect(back)
    context_tag = request.form.get('context_tag')
    if context_tag not in PlayerFeedback.CONTEXT_TAGS:
        context_tag = 'General'

    db.session.add(PlayerFeedback(
        player_id=player.id,
        coach_id=current_user.id,
        session_id=_team_row_id(SessionPlan, request.form.get('session_id')),
        game_id=_team_row_id(Game, request.form.get('game_id')),
        clip_id=_team_row_id(Clip, request.form.get('clip_id')),
        content=content,
        context_tag=context_tag,
        shared=bool(request.form.get('shared')),
    ))
    db.session.commit()
    flash(f'Note saved for {player.name}'
          + (' and shared with them.' if request.form.get('shared') else ' (coaches only).'), 'success')
    return redirect(back)


@bp.route('/feedback/<int:feedback_id>/share', methods=['POST'])
@login_required
def toggle_share(feedback_id):
    _require_coach()

    fb = _team_feedback().filter(PlayerFeedback.id == feedback_id).first_or_404()
    fb.shared = not fb.shared
    if not fb.shared:
        fb.seen_at = None
    db.session.commit()
    flash('Shared with the player.' if fb.shared else 'Now for coaches only.', 'success')
    return redirect(_safe_next(request.form.get('next'),
                               url_for('feedback.player_feedback', player_id=fb.player_id)))


# ── A player's own feedback ──────────────────────────────────────────────────

@bp.route('/feedback/mine')
@login_required
def mine():
    player = current_user.player
    if player is None:
        abort(404)

    entries = (PlayerFeedback.query.filter_by(player_id=player.id, shared=True)
               .order_by(PlayerFeedback.created_at.desc()).all())
    new_ids = {e.id for e in entries if e.seen_at is None}
    if new_ids:
        now = datetime.utcnow()
        for e in entries:
            if e.id in new_ids:
                e.seen_at = now
        db.session.commit()

    return render_template('feedback/mine.html', player=player, entries=entries, new_ids=new_ids)


# ── Delete a single feedback entry ───────────────────────────────────────────

@bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
def delete_feedback(feedback_id):
    _require_coach()

    fb = _team_feedback().filter(PlayerFeedback.id == feedback_id).first_or_404()
    player_id = fb.player_id
    db.session.delete(fb)
    db.session.commit()

    flash('Feedback note deleted.', 'success')
    return redirect(_safe_next(request.form.get('next'),
                               url_for('feedback.player_feedback', player_id=player_id)))
