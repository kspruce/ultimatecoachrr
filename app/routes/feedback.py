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
from app.models.feedback import FeedbackReply, PlayerFeedback, PlayerFocus
from app.models.tournament import Tournament
from app.utils import feedback as fbu
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
    """Shared notes, coaches' replies and a "keep in mind" the signed-in
    player hasn't opened yet."""
    player = user.player if user.is_authenticated else None
    if player is None:
        return 0
    notes = PlayerFeedback.query.filter_by(player_id=player.id, shared=True, seen_at=None).count()
    replies = (FeedbackReply.query.join(PlayerFeedback, PlayerFeedback.id == FeedbackReply.feedback_id)
               .filter(PlayerFeedback.player_id == player.id, PlayerFeedback.shared.is_(True),
                       FeedbackReply.from_player.is_(False), FeedbackReply.seen_at.is_(None)).count())
    focus = PlayerFocus.query.filter_by(player_id=player.id, active=True, seen_at=None).count()
    return notes + replies + focus


@bp.app_context_processor
def feedback_nav():
    def my_focus_for(kind, row_id):
        """The signed-in player's "keep in mind" if it's for this session or
        tournament, or not for any one event."""
        player = current_user.player if current_user.is_authenticated else None
        focus = fbu.current_focus(player.id) if player is not None else None
        if focus is None:
            return None
        if not focus.session_id and not focus.tournament_id:
            return focus
        return focus if (kind == 'session' and focus.session_id == row_id) or \
            (kind == 'tournament' and focus.tournament_id == row_id) else None
    return {'unseen_feedback_count': lambda: unseen_count(current_user), 'my_focus_for': my_focus_for}


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
        follow_count=len(fbu.follow_ups(players)),
        reply_count=sum(fbu.unread_replies(team_id).values()),
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
    new_reply_ids = _mark_seen([r for e in entries for r in e.replies if r.from_player])
    sessions, tournaments = fbu.coming_events(player.team_organization_id)

    return render_template(
        'feedback/player_feedback.html',
        focus=fbu.current_focus(player.id), focus_history=fbu.focus_history(player.id),
        coming_sessions=sessions, coming_tournaments=tournaments, new_reply_ids=new_reply_ids,
        kinds=PlayerFeedback.KINDS,
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
    kind = request.form.get('kind') if request.form.get('kind') in dict(PlayerFeedback.KINDS) else 'note'

    db.session.add(PlayerFeedback(
        player_id=player.id,
        coach_id=current_user.id,
        session_id=_team_row_id(SessionPlan, request.form.get('session_id')),
        game_id=_team_row_id(Game, request.form.get('game_id')),
        clip_id=_team_row_id(Clip, request.form.get('clip_id')),
        content=content,
        context_tag=context_tag,
        kind=kind,
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
    now = datetime.utcnow()
    for e in entries:
        if e.id in new_ids:
            e.seen_at = now
    new_reply_ids = _mark_seen([r for e in entries for r in e.replies if not r.from_player])
    focus = fbu.current_focus(player.id)
    new_focus = focus is not None and focus.seen_at is None
    if new_focus:
        focus.seen_at = now
    db.session.commit()

    return render_template('feedback/mine.html', player=player, entries=entries, new_ids=new_ids,
                           new_reply_ids=new_reply_ids, focus=focus, new_focus=new_focus,
                           focus_history=fbu.focus_history(player.id))


def _mark_seen(replies):
    """Mark the other side's replies read; returns the ids that were new."""
    now = datetime.utcnow()
    new = {r.id for r in replies if r.seen_at is None}
    for r in replies:
        if r.id in new:
            r.seen_at = now
    if new:
        db.session.commit()
    return new


# ── Replies ──────────────────────────────────────────────────────────────────

@bp.route('/feedback/<int:feedback_id>/reply', methods=['POST'])
@login_required
def reply(feedback_id):
    """The player replies to a note shared with them; a coach replies back."""
    fb = _team_feedback().filter(PlayerFeedback.id == feedback_id).first_or_404()
    player = current_user.player
    is_player = player is not None and player.id == fb.player_id and fb.shared
    if not (is_player or current_user.is_coach):
        abort(403)
    back = _safe_next(request.form.get('next'), url_for('feedback.mine') if is_player and not current_user.is_coach
                      else url_for('feedback.player_feedback', player_id=fb.player_id))
    content = (request.form.get('content') or '').strip()[:2000]
    if not content:
        flash('Write a reply first.', 'warning')
        return redirect(back)
    db.session.add(FeedbackReply(feedback_id=fb.id, user_id=current_user.id, content=content,
                                 from_player=is_player and not current_user.is_coach))
    db.session.commit()
    flash('Reply sent.', 'success')
    return redirect(back + f'#note-{fb.id}')


# ── Keep in mind: a player's focus for the next training or tournament ───────

@bp.route('/players/<int:player_id>/focus', methods=['POST'])
@login_required
def set_focus(player_id):
    _require_coach()
    player = team_row_or_404(Player, player_id)
    back = _safe_next(request.form.get('next'), url_for('feedback.player_feedback', player_id=player.id))
    content = (request.form.get('content') or '').strip()[:1000]
    if not content:
        flash('Write what they should keep in mind.', 'warning')
        return redirect(back)
    event = request.form.get('event') or ''
    session_id = _team_row_id(SessionPlan, event[1:]) if event.startswith('s') else None
    tournament_id = _team_row_id(Tournament, event[1:]) if event.startswith('t') else None
    for old in PlayerFocus.query.filter_by(player_id=player.id, active=True):
        old.active = False
    db.session.add(PlayerFocus(team_organization_id=player.team_organization_id, player_id=player.id,
                               content=content, session_id=session_id, tournament_id=tournament_id,
                               set_by=current_user.id))
    db.session.commit()
    flash(f'"Keep in mind" set for {player.name}.', 'success')
    return redirect(back)


@bp.route('/players/<int:player_id>/focus/clear', methods=['POST'])
@login_required
def clear_focus(player_id):
    _require_coach()
    player = team_row_or_404(Player, player_id)
    for old in PlayerFocus.query.filter_by(player_id=player.id, active=True):
        old.active = False
    db.session.commit()
    flash(f'Cleared {player.name}\'s "keep in mind".', 'success')
    return redirect(_safe_next(request.form.get('next'), url_for('feedback.player_feedback', player_id=player.id)))


@bp.route('/feedback/focus')
@login_required
def focus_board():
    """Every active player's "keep in mind", and who needs a word."""
    _require_coach()
    team_id = get_current_team_id()
    players = Player.query.filter_by(active=True, team_organization_id=team_id).order_by(Player.name).all()
    focus = {f.player_id: f for f in PlayerFocus.query.filter(PlayerFocus.team_organization_id == team_id,
                                                               PlayerFocus.active.is_(True))}
    sessions, tournaments = fbu.coming_events(team_id)
    follow = fbu.follow_ups(players)
    only = request.args.get('show') == 'follow'
    return render_template('feedback/focus.html', players=[p for p in players if not only or p.id in follow],
                           focus=focus, follow=follow, replies=fbu.unread_replies(team_id), only=only,
                           coming_sessions=sessions, coming_tournaments=tournaments,
                           today=datetime.utcnow().date(), all_count=len(players))


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
