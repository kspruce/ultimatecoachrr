"""Players' answers for training sessions: who is coming.

Every way of answering (the availability page, a session's page, the
coach's grid, a CSV import, a Discord button) saves through set_rsvp, so
answers are stored one way: SessionRSVP.status is 'attending', 'maybe' or
'not_attending'.

A player who hasn't answered for a date can still have a usual answer for
its schedule ("usually at Saturdays"); answers() fills that in, marked as
usual, for every page that shows who is coming.
"""
from dataclasses import dataclass
from datetime import date

from app import db
from app.models.player import Player
from app.models.schedule import ScheduleAvailability
from app.models.season import Season, SeasonRoster
from app.models.session import SessionPlan, SessionRSVP

ATTENDING, MAYBE, NOT_ATTENDING = 'attending', 'maybe', 'not_attending'
STATUSES = (ATTENDING, MAYBE, NOT_ATTENDING)
LABELS = {ATTENDING: 'Yes', MAYBE: 'Maybe', NOT_ATTENDING: 'No'}

_ALIASES = {
    ATTENDING: ATTENDING, 'yes': ATTENDING, 'y': ATTENDING, 'going': ATTENDING, '✅': ATTENDING,
    MAYBE: MAYBE, 'm': MAYBE, '?': MAYBE, 'unsure': MAYBE, '❓': MAYBE,
    NOT_ATTENDING: NOT_ATTENDING, 'no': NOT_ATTENDING, 'n': NOT_ATTENDING, 'not attending': NOT_ATTENDING,
    'cant': NOT_ATTENDING, "can't": NOT_ATTENDING, '❌': NOT_ATTENDING,
}


def normalise(value):
    """'Yes', 'y', 'attending', '✅' ... -> 'attending' (likewise maybe and
    no); anything else -> None."""
    if value is None:
        return None
    return _ALIASES.get(str(value).strip().lower())


@dataclass
class Answer:
    status: str
    notes: str = None
    usual: bool = False  # from the player's usual answer, not given for this date

    @property
    def label(self):
        return LABELS[self.status]


def set_rsvp(session, player, status, notes=None, keep_notes=True):
    """Save a player's answer for a session (status None clears it). The
    caller commits. Raises ValueError for another team's player or a status
    that isn't yes, maybe or no."""
    if player.team_organization_id != session.team_organization_id:
        raise ValueError('That player is not on this team.')
    rsvp = SessionRSVP.query.filter_by(session_id=session.id, player_id=player.id).first()
    if status is None:
        if rsvp is not None:
            db.session.delete(rsvp)
        return None
    status = normalise(status)
    if status is None:
        raise ValueError('Answer yes, maybe or no.')
    if rsvp is None:
        rsvp = SessionRSVP(session_id=session.id, player_id=player.id,
                           team_organization_id=session.team_organization_id, status=status)
        db.session.add(rsvp)
    rsvp.status = status
    rsvp.team_organization_id = session.team_organization_id
    if notes is not None or not keep_notes:
        rsvp.notes = (notes or '').strip()[:500] or None
    return rsvp


def set_usual(schedule, player, status):
    """Save (or clear, with None) a player's usual answer for a schedule.
    The caller commits."""
    if player.team_organization_id != schedule.team_organization_id:
        raise ValueError('That player is not on this team.')
    row = ScheduleAvailability.query.filter_by(schedule_id=schedule.id, player_id=player.id).first()
    status = normalise(status)
    if status is None:
        if row is not None:
            db.session.delete(row)
        return None
    if row is None:
        row = ScheduleAvailability(schedule_id=schedule.id, player_id=player.id, status=status,
                                   team_organization_id=schedule.team_organization_id)
        db.session.add(row)
    row.status = status
    return row


def usual_answers(player):
    """{schedule_id: status} for one player."""
    return {r.schedule_id: r.status for r in ScheduleAvailability.query.filter_by(player_id=player.id)}


def answers(sessions, player_ids=None):
    """{(session_id, player_id): Answer} for the given sessions: what each
    player said, else their usual answer for the session's schedule."""
    sessions = list(sessions)
    if not sessions:
        return {}
    ids = [s.id for s in sessions]
    query = SessionRSVP.query.filter(SessionRSVP.session_id.in_(ids))
    if player_ids is not None:
        query = query.filter(SessionRSVP.player_id.in_(list(player_ids)))
    out = {}
    for r in query:
        if r.status in STATUSES:
            out[(r.session_id, r.player_id)] = Answer(r.status, r.notes)

    schedule_ids = {s.schedule_id for s in sessions if s.schedule_id}
    if schedule_ids:
        usual = ScheduleAvailability.query.filter(ScheduleAvailability.schedule_id.in_(schedule_ids))
        if player_ids is not None:
            usual = usual.filter(ScheduleAvailability.player_id.in_(list(player_ids)))
        by_schedule = {}
        for row in usual:
            by_schedule.setdefault(row.schedule_id, []).append(row)
        for s in sessions:
            for row in by_schedule.get(s.schedule_id, []):
                out.setdefault((s.id, row.player_id), Answer(row.status, usual=True))
    return out


def answer_for(session, player):
    return answers([session], [player.id]).get((session.id, player.id))


# ── Who a session is for ───────────────────────────────────────────────────

def player_squads(team_id):
    """{player_id: squad_id or None} from the current season's roster."""
    season = Season.query.filter_by(team_organization_id=team_id, is_current=True).first()
    if season is None:
        return {}
    rows = db.session.query(SeasonRoster.player_id, SeasonRoster.squad_id).filter(
        SeasonRoster.season_id == season.id, SeasonRoster.status != 'left')
    return dict(rows)


def is_for(session, squad_id):
    """Is a session for someone in this squad? Sessions without squads are
    for everyone."""
    return not session.squads or squad_id in {s.id for s in session.squads}


def can_join(session, squad_id):
    """Can someone from this squad say they're coming (their own squad's
    session, or another squad's that welcomes others)?"""
    return is_for(session, squad_id) or bool(session.schedule and session.schedule.others_welcome)


def team_players(team_id):
    """The players training is for: this season's active roster."""
    return (Player.query.filter_by(team_organization_id=team_id, active=True)
            .order_by(Player.name).all())


def expected_players(session, players=None, squads=None, answered=None):
    """The players a session is for: active players in its squads, plus
    anyone else who has said they're coming."""
    players = players if players is not None else team_players(session.team_organization_id)
    squads = squads if squads is not None else player_squads(session.team_organization_id)
    answered = answered if answered is not None else {
        pid for (pid,) in db.session.query(SessionRSVP.player_id).filter_by(session_id=session.id)}
    return [p for p in players if is_for(session, squads.get(p.id)) or p.id in answered]


def counts(session, answer_map=None, players=None, squads=None):
    """{'attending': n, 'maybe': n, 'not_attending': n, 'none': n} over the
    players the session is for."""
    answer_map = answer_map if answer_map is not None else answers([session])
    answered = {pid for (sid, pid) in answer_map if sid == session.id}
    out = {ATTENDING: 0, MAYBE: 0, NOT_ATTENDING: 0, 'none': 0}
    for p in expected_players(session, players, squads, answered):
        a = answer_map.get((session.id, p.id))
        out[a.status if a else 'none'] += 1
    return out


def upcoming_sessions(team_id, start=None, end=None, include_cancelled=False):
    query = SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                     SessionPlan.date >= (start or date.today()))
    if end is not None:
        query = query.filter(SessionPlan.date <= end)
    if not include_cancelled:
        query = query.filter(SessionPlan.status != SessionPlan.STATUS_CANCELLED)
    return query.order_by(SessionPlan.date, SessionPlan.start_time, SessionPlan.id).all()


# ── What players may see ───────────────────────────────────────────────────

def attendee_visibility(team_id):
    from app.models.team_settings import TeamSettings
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    return (settings.attendee_visibility if settings else None) or 'names'


def plan_visible(session, user, today=None):
    """Can this user see the session's plan (its blocks)? Coaches always
    can; players once it's published and, if the team set it, within that
    many days of the session."""
    if user.is_coach:
        return True
    if not session.is_published:
        return False
    from app.models.team_settings import TeamSettings
    settings = TeamSettings.query.filter_by(team_id=session.team_organization_id).first()
    days = settings.plan_visible_days if settings else None
    if days is None or session.date is None:
        return True
    return (session.date - (today or date.today())).days <= days
