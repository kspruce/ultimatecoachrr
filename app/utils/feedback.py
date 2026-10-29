"""Coach feedback helpers: a player's "Keep in mind", the coming events it
can be for, and what the coaches should follow up on."""
from datetime import date, datetime, timedelta

from app import db
from app.models.feedback import FeedbackReply, PlayerFeedback, PlayerFocus

QUIET_WEEKS = 4  # no note shared with a player for this long: worth a word


def current_focus(player_id):
    return (PlayerFocus.query.filter_by(player_id=player_id, active=True)
            .order_by(PlayerFocus.created_at.desc()).first())


def focus_history(player_id, limit=5):
    return (PlayerFocus.query.filter_by(player_id=player_id, active=False)
            .order_by(PlayerFocus.created_at.desc()).limit(limit).all())


def coming_events(team_id, today=None):
    """([sessions], [tournaments]) in the next couple of months, to set a
    focus for."""
    from app.models.session import SessionPlan
    from app.models.tournament import Tournament
    today = today or date.today()
    soon = today + timedelta(days=70)
    sessions = (SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                         SessionPlan.date >= today, SessionPlan.date <= soon)
                .order_by(SessionPlan.date).limit(10).all())
    tournaments = (Tournament.query.filter(Tournament.team_organization_id == team_id,
                                           Tournament.start_date >= today, Tournament.start_date <= soon)
                   .order_by(Tournament.start_date).all())
    return sessions, tournaments


def unread_replies(team_id):
    """{player id: count} of players' replies the coaches haven't read."""
    from app.models.player import Player
    rows = (db.session.query(PlayerFeedback.player_id, db.func.count(FeedbackReply.id))
            .join(FeedbackReply, FeedbackReply.feedback_id == PlayerFeedback.id)
            .join(Player, Player.id == PlayerFeedback.player_id)
            .filter(Player.team_organization_id == team_id, FeedbackReply.from_player.is_(True),
                    FeedbackReply.seen_at.is_(None))
            .group_by(PlayerFeedback.player_id).all())
    return dict(rows)


def follow_ups(players, today=None):
    """{player id: [reasons]} for the coaches: no focus set, a focus for an
    event that's been, nothing shared with them for a while, or no review
    for a few months."""
    today = today or date.today()
    ids = [p.id for p in players]
    if not ids:
        return {}
    focus = {}
    for f in PlayerFocus.query.filter(PlayerFocus.player_id.in_(ids), PlayerFocus.active.is_(True)):
        focus[f.player_id] = f
    last_shared = dict(db.session.query(PlayerFeedback.player_id, db.func.max(PlayerFeedback.created_at))
                       .filter(PlayerFeedback.player_id.in_(ids), PlayerFeedback.shared.is_(True))
                       .group_by(PlayerFeedback.player_id).all())
    quiet = datetime.utcnow() - timedelta(weeks=QUIET_WEEKS)
    from app.models.feedback import PlayerReview
    last_review = dict(db.session.query(PlayerReview.player_id, db.func.max(PlayerReview.created_at))
                       .filter(PlayerReview.player_id.in_(ids)).group_by(PlayerReview.player_id).all())
    review_due = datetime.utcnow() - timedelta(days=30 * REVIEW_MONTHS)
    out = {}
    for p in players:
        reasons = []
        f = focus.get(p.id)
        if f is None:
            reasons.append('No "keep in mind" yet')
        elif f.is_past(today):
            reasons.append(f'Keep in mind was {f.for_label[0].lower()}{f.for_label[1:]}: time for a new one')
        if not last_shared.get(p.id) or last_shared[p.id] < quiet:
            reasons.append(f'Nothing shared with them in {QUIET_WEEKS}+ weeks')
        if last_review.get(p.id) is None or last_review[p.id] < review_due:
            reasons.append(f'No review in {REVIEW_MONTHS}+ months')
        if reasons:
            out[p.id] = reasons
    return out


# ── Goals and reviews ──────────────────────────────────────────────────────

REVIEW_MONTHS = 3  # no review for this long: worth one


def goals_from_text(player, text, horizon, user_id=None):
    """One goal per non-empty line of the old free-text boxes (used by the
    migration's twin and by the old goals form)."""
    from app.models.feedback import PlayerGoal
    made = []
    for line in (text or '').splitlines():
        line = line.strip(' -•*\t')
        if line:
            goal = PlayerGoal(team_organization_id=player.team_organization_id, player_id=player.id,
                              title=line[:200], horizon=horizon, created_by=user_id)
            db.session.add(goal)
            made.append(goal)
    return made


def player_goals(player_id):
    """(active goals, finished goals): newest first within each."""
    from app.models.feedback import PlayerGoal
    order = {'short': 0, 'mid': 1, 'long': 2, 'skill': 3}
    goals = PlayerGoal.query.filter_by(player_id=player_id).order_by(PlayerGoal.created_at.desc()).all()
    active = sorted((g for g in goals if g.status == 'active'), key=lambda g: order.get(g.horizon, 9))
    return active, [g for g in goals if g.status != 'active']


def player_reviews(player_id, shared_only=False):
    from app.models.feedback import PlayerReview
    query = PlayerReview.query.filter_by(player_id=player_id)
    if shared_only:
        query = query.filter_by(shared=True)
    return query.order_by(PlayerReview.created_at.desc()).all()
