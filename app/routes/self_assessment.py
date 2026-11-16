# app/routes/self_assessment.py
"""Player check-ins: a quick self-assessment rubric (offence, cutting,
handling, defence, mental & spirit) plus the player's own notes.

Players fill them in whenever they like, or when a coach nudges the team.
Coaches always see them, edit the team's rubric statements and see what the
team says about itself."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.player import Player
from app.models.self_assessment import (
    SCALE, SECTIONS, CheckInRequest, RubricItem, SelfAssessment,
)
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.utils import self_assessment as sau
from app.utils.team_filter import get_current_team_id

bp = Blueprint('checkin', __name__)


def _require_coach():
    if not current_user.is_coach:
        abort(403)


def _my_player():
    player = current_user.player
    if player is None or player.team_organization_id != get_current_team_id():
        abort(404)
    return player


def _check_in_or_404(check_in_id):
    """A check-in the signed-in user may see: their own, or any of the
    team's for coaches."""
    a = SelfAssessment.query.filter_by(id=check_in_id, team_organization_id=get_current_team_id()).first_or_404()
    is_own = a.player.user_id and a.player.user_id == current_user.id
    if not (is_own or current_user.is_coach):
        abort(404)
    return a, bool(is_own)


def _team_row(model, raw):
    try:
        row_id = int(raw)
    except (TypeError, ValueError):
        return None
    return model.query.filter_by(id=row_id, team_organization_id=get_current_team_id()).first()


def _recent_events(team_id):
    """Recent tournaments and sessions a check-in could be about."""
    today = date.today()
    tournaments = (Tournament.query.filter(Tournament.team_organization_id == team_id,
                                           Tournament.start_date.isnot(None),
                                           Tournament.start_date <= today + timedelta(days=3),
                                           Tournament.start_date >= today - timedelta(days=90))
                   .order_by(Tournament.start_date.desc()).limit(6).all())
    sessions = (SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                         SessionPlan.date.isnot(None),
                                         SessionPlan.date <= today,
                                         SessionPlan.date >= today - timedelta(days=21))
                .order_by(SessionPlan.date.desc()).limit(6).all())
    return tournaments, sessions


def _fill(a, items):
    a.notes = (request.form.get('notes') or '').strip()[:5000] or None
    a.title = ' '.join((request.form.get('title') or '').split())[:120] or None
    about = request.form.get('about') or ''
    if about.startswith('t:'):
        t = _team_row(Tournament, about[2:])
        a.tournament_id, a.session_id = (t.id if t else None), None
    elif about.startswith('s:'):
        s = _team_row(SessionPlan, about[2:])
        a.session_id, a.tournament_id = (s.id if s else None), None
    elif about == 'none':
        a.session_id = a.tournament_id = None
    sau.save_scores(a, items, request.form)
    focus = request.form.get('focus_item', type=int)
    a.focus_item_id = focus if focus in {i.id for i in items} else None


def _form(player, a, req, items):
    tournaments, sessions = _recent_events(player.team_organization_id)
    return render_template('feedback/checkin_form.html', player=player, check_in=a, req=req,
                           sections=sau.items_by_section(items), scale=SCALE,
                           scores=a.score_map() if a else {}, tournaments=tournaments, sessions=sessions,
                           last=sau.player_check_ins(player.id, limit=1))


# ── The player fills one in ──────────────────────────────────────────────────

@bp.route('/check-in/new', methods=['GET', 'POST'])
@login_required
def new():
    player = _my_player()
    items = [i for i in sau.ensure_items(player.team_organization_id) if i.active]
    req = _team_row(CheckInRequest, request.values.get('request'))
    if req is not None and SelfAssessment.query.filter_by(player_id=player.id, request_id=req.id).first():
        done = SelfAssessment.query.filter_by(player_id=player.id, request_id=req.id).first()
        flash('You already filled this one in. You can change it here.', 'info')
        return redirect(url_for('checkin.edit', check_in_id=done.id))
    if request.method == 'POST':
        a = SelfAssessment(team_organization_id=player.team_organization_id, player_id=player.id,
                           request_id=req.id if req else None)
        if req is not None:
            a.tournament_id, a.session_id = req.tournament_id, req.session_id
        _fill(a, items)
        if not a.scores and not a.notes:
            flash('Tap a few statements or write a note first.', 'warning')
            return _form(player, a, req, items)
        db.session.add(a)
        db.session.commit()
        flash('Check-in saved. Your coaches can see it.', 'success')
        return redirect(url_for('checkin.view', check_in_id=a.id))
    return _form(player, None, req, items)


@bp.route('/check-in/<int:check_in_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(check_in_id):
    a, is_own = _check_in_or_404(check_in_id)
    if not is_own:
        abort(403)
    items = sau.ensure_items(a.team_organization_id)
    # The statements showing now, plus any hidden since that this one answered
    answered = set(a.score_map())
    items = [i for i in items if i.active or i.id in answered]
    if request.method == 'POST':
        _fill(a, items)
        db.session.commit()
        flash('Check-in saved.', 'success')
        return redirect(url_for('checkin.view', check_in_id=a.id))
    return _form(a.player, a, a.request, items)


@bp.route('/check-in/<int:check_in_id>')
@login_required
def view(check_in_id):
    a, is_own = _check_in_or_404(check_in_id)
    if current_user.is_coach and not is_own and a.seen_by_coach_at is None:
        a.seen_by_coach_at = datetime.utcnow()
        db.session.commit()
    scores = a.score_map()
    items = [i for i in sau.ensure_items(a.team_organization_id) if i.id in scores]
    earlier = (SelfAssessment.query.filter(SelfAssessment.player_id == a.player_id,
                                           SelfAssessment.created_at < a.created_at)
               .order_by(SelfAssessment.created_at.desc()).first())
    return render_template('feedback/checkin_view.html', check_in=a, is_own=is_own,
                           sections=sau.items_by_section(items, active_only=False), scores=scores,
                           scale=dict(SCALE), averages=a.section_averages(),
                           earlier=earlier.section_averages() if earlier else {}, section_list=SECTIONS)


@bp.route('/check-in/<int:check_in_id>/delete', methods=['POST'])
@login_required
def delete(check_in_id):
    a, is_own = _check_in_or_404(check_in_id)
    player_id = a.player_id
    db.session.delete(a)
    db.session.commit()
    flash('Check-in deleted.', 'success')
    if is_own:
        return redirect(url_for('feedback.mine'))
    return redirect(url_for('team.player_detail', player_id=player_id, _anchor='development'))


# ── Coaches: what the team says, nudges, the rubric ──────────────────────────

@bp.route('/check-ins')
@login_required
def team():
    _require_coach()
    team_id = get_current_team_id()
    sau.ensure_items(team_id)
    req = _team_row(CheckInRequest, request.args.get('request'))
    days = request.args.get('days', type=int)
    if days not in (30, 90, 365):
        days = None
    item_rows, player_rows, count = sau.team_overview(team_id, request_id=req.id if req else None,
                                                      days=None if req else days)
    requests = (CheckInRequest.query.filter_by(team_organization_id=team_id)
                .order_by(CheckInRequest.created_at.desc()).limit(12).all())
    active_players = sum(1 for p, _, _ in player_rows)
    answered = {r.id: len({a.player_id for a in r.assessments}) for r in requests}
    recent = (SelfAssessment.query.filter_by(team_organization_id=team_id)
              .order_by(SelfAssessment.created_at.desc()).limit(10).all())
    tournaments, sessions = _recent_events(team_id)
    if req is not None:
        done = {a.player_id for a in req.assessments}
        waiting = [p for p, _, _ in player_rows if p.id not in done]
    else:
        waiting = []
    return render_template('feedback/checkin_team.html', item_rows=item_rows, player_rows=player_rows,
                           count=count, requests=requests, answered=answered, active_players=active_players,
                           recent=recent, req=req, days=days, waiting=waiting, sections=SECTIONS,
                           tournaments=tournaments, sessions=sessions, now=datetime.utcnow(),
                           discord_ready=_discord_ready(team_id))


def _discord_ready(team_id):
    try:
        from app.discord import notify
        return notify.channel_target(notify.team_settings(team_id)) is not None
    except Exception:  # noqa: BLE001 - Discord is optional
        return False


@bp.route('/check-ins/nudge', methods=['POST'])
@login_required
def nudge():
    _require_coach()
    team_id = get_current_team_id()
    title = ' '.join((request.form.get('title') or '').split())[:120]
    if not title:
        flash('Give the check-in a name, e.g. "After Nationals".', 'warning')
        return redirect(url_for('checkin.team'))
    about = request.form.get('about') or ''
    t = _team_row(Tournament, about[2:]) if about.startswith('t:') else None
    s = _team_row(SessionPlan, about[2:]) if about.startswith('s:') else None
    req = CheckInRequest(team_organization_id=team_id, title=title, created_by=current_user.id,
                         message=(request.form.get('message') or '').strip()[:1000] or None,
                         tournament_id=t.id if t else None, session_id=s.id if s else None)
    db.session.add(req)
    db.session.commit()
    posted = False
    if request.form.get('discord'):
        try:
            from app.discord import messages, notify
            posted = notify.post(team_id, messages.announcement(
                f'Check-in: {title}', (req.message or 'How did you go? Takes about a minute.'),
                messages.link('checkin.new', request=req.id)))
        except Exception:  # noqa: BLE001 - a Discord problem never blocks the nudge
            posted = False
    flash(f'Nudge sent: players will see "{title}" on My Feedback'
          + (' and in Discord.' if posted else '.'), 'success')
    return redirect(url_for('checkin.team', request=req.id))


@bp.route('/check-ins/nudge/<int:request_id>/close', methods=['POST'])
@login_required
def close_nudge(request_id):
    _require_coach()
    req = _team_row(CheckInRequest, request_id) or abort(404)
    req.closed_at = None if req.closed_at else datetime.utcnow()
    db.session.commit()
    flash('Nudge closed: players no longer see it.' if req.closed_at else 'Nudge reopened.', 'success')
    return redirect(url_for('checkin.team', request=req.id))


@bp.route('/check-ins/rubric', methods=['GET', 'POST'])
@login_required
def rubric():
    _require_coach()
    team_id = get_current_team_id()
    items = sau.ensure_items(team_id)
    if request.method == 'POST':
        by_id = {i.id: i for i in items}
        for item in items:
            text = ' '.join((request.form.get(f'text-{item.id}') or '').split())[:200]
            if text:
                item.text = text
            item.active = bool(request.form.get(f'active-{item.id}'))
        for section, _ in SECTIONS:
            text = ' '.join((request.form.get(f'new-{section}') or '').split())[:200]
            if text:
                last = max([i.position for i in items if i.section == section] + [-1])
                db.session.add(RubricItem(team_organization_id=team_id, section=section, text=text,
                                          position=last + 1))
        move = request.form.get('move') or ''
        item_id, _, direction = move.partition(':')
        item = by_id.get(int(item_id)) if item_id.isdigit() else None
        if item is not None:
            same = sorted((i for i in items if i.section == item.section), key=lambda i: (i.position, i.id))
            for pos, i in enumerate(same):
                i.position = pos
            # Swap with the next statement that's showing (or hidden) like it
            peers = [i for i in same if i.active == item.active]
            idx = peers.index(item)
            other = idx - 1 if direction == 'up' else idx + 1
            if 0 <= other < len(peers):
                item.position, peers[other].position = peers[other].position, item.position
        db.session.commit()
        if not move:
            flash('Rubric saved.', 'success')
        return redirect(url_for('checkin.rubric', _anchor=f'sec-{item.section}' if item else None))
    return render_template('feedback/checkin_rubric.html',
                           sections=sau.items_by_section(items, active_only=False))


@bp.route('/check-ins/rubric/restore', methods=['POST'])
@login_required
def restore_rubric():
    _require_coach()
    added = sau.restore_defaults(get_current_team_id())
    flash(f'Brought back {added} base statement{"s" if added != 1 else ""}.' if added
          else 'All the base statements are already showing.', 'success')
    return redirect(url_for('checkin.rubric'))
