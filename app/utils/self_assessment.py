"""Helpers for player check-ins (self-assessment rubric)."""
from datetime import datetime, timedelta

from app import db
from app.models.player import Player
from app.models.self_assessment import (
    DEFAULT_ITEMS, SECTIONS, CheckInRequest, RubricItem, SelfAssessment, SelfAssessmentScore,
)


def ensure_items(team_id):
    """The team's rubric, seeded with the base statements the first time."""
    if not RubricItem.query.filter_by(team_organization_id=team_id).first():
        for section, _ in SECTIONS:
            for pos, text in enumerate(DEFAULT_ITEMS[section]):
                db.session.add(RubricItem(team_organization_id=team_id, section=section, text=text, position=pos))
        db.session.commit()
    return RubricItem.query.filter_by(team_organization_id=team_id).order_by(RubricItem.position, RubricItem.id).all()


def items_by_section(items, active_only=True):
    """[(section, label, [items])] in rubric order, skipping empty sections."""
    out = []
    for section, label in SECTIONS:
        rows = [i for i in items if i.section == section and (i.active or not active_only)]
        if rows or not active_only:
            out.append((section, label, rows))
    return out


def restore_defaults(team_id):
    """Bring back any base statement the team no longer has showing."""
    items = ensure_items(team_id)
    added = 0
    for section, _ in SECTIONS:
        mine = [i for i in items if i.section == section]
        showing = {i.text for i in mine if i.active}
        for text in DEFAULT_ITEMS[section]:
            if text in showing:
                continue
            hidden = next((i for i in mine if i.text == text), None)
            if hidden is not None:
                hidden.active = True
            else:
                db.session.add(RubricItem(team_organization_id=team_id, section=section, text=text,
                                          position=max([i.position for i in mine] + [-1]) + 1))
            added += 1
    db.session.commit()
    return added


def open_requests(team_id):
    now = datetime.utcnow()
    since = now - timedelta(days=CheckInRequest.OPEN_DAYS)
    return (CheckInRequest.query
            .filter(CheckInRequest.team_organization_id == team_id, CheckInRequest.closed_at.is_(None),
                    CheckInRequest.created_at >= since)
            .order_by(CheckInRequest.created_at.desc()).all())


def pending_requests(player):
    """Open nudges this player hasn't answered yet."""
    if player is None or not player.active:
        return []
    answered = {a.request_id for a in SelfAssessment.query.filter_by(player_id=player.id)
                .filter(SelfAssessment.request_id.isnot(None))}
    return [r for r in open_requests(player.team_organization_id) if r.id not in answered]


def player_check_ins(player_id, limit=None):
    q = SelfAssessment.query.filter_by(player_id=player_id).order_by(SelfAssessment.created_at.desc())
    return q.limit(limit).all() if limit else q.all()


def unseen_by_coaches(team_id):
    return (SelfAssessment.query.filter_by(team_organization_id=team_id, seen_by_coach_at=None)
            .count())


def save_scores(assessment, items, form):
    """Store the taps from the form (score-<item id> = 1..4; blank = didn't
    come up)."""
    existing = {s.item_id: s for s in assessment.scores}
    for item in items:
        raw = form.get(f'score-{item.id}')
        try:
            score = int(raw) if raw else None
        except ValueError:
            score = None
        if score not in (1, 2, 3, 4):
            score = None
        row = existing.get(item.id)
        if score is None:
            if row is not None:
                assessment.scores.remove(row)
        elif row is None:
            assessment.scores.append(SelfAssessmentScore(item_id=item.id, score=score))
        else:
            row.score = score


def team_overview(team_id, request_id=None, days=None):
    """What the team says about itself.

    Returns (item_rows, player_rows, count):
      item_rows: [(item, average, answers)] lowest average first
      player_rows: [(player, latest check-in or None, {section: average})]
    """
    q = SelfAssessment.query.filter_by(team_organization_id=team_id)
    if request_id:
        q = q.filter_by(request_id=request_id)
    if days:
        q = q.filter(SelfAssessment.created_at >= datetime.utcnow() - timedelta(days=days))
    assessments = q.order_by(SelfAssessment.created_at.desc()).all()

    totals = {}
    for a in assessments:
        for s in a.scores:
            t = totals.setdefault(s.item_id, [0, 0])
            t[0] += s.score
            t[1] += 1
    items = {i.id: i for i in RubricItem.query.filter(RubricItem.id.in_(list(totals) or [0]))}
    item_rows = sorted(((items[i], round(a / n, 1), n) for i, (a, n) in totals.items() if i in items),
                       key=lambda r: (r[1], -r[2]))

    latest = {}
    for a in assessments:
        latest.setdefault(a.player_id, a)
    players = (Player.query.filter_by(team_organization_id=team_id, active=True).order_by(Player.name).all())
    player_rows = [(p, latest.get(p.id), latest[p.id].section_averages() if p.id in latest else {})
                   for p in players]
    return item_rows, player_rows, len(assessments)


def section_trend(check_ins):
    """[(check-in, {section: average})] oldest first, for a player's trend."""
    return [(a, a.section_averages()) for a in reversed(check_ins)]
