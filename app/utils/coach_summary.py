"""An email to coaches who have asked for one, listing what's waiting on
them: the home page's "Needs attention" (app/utils/dashboard.py).

Nothing is sent when nothing is outstanding. A coach hears about each
thing once, when it first appears; if things are still open a week after
the last email they get one reminder of what's left. Off unless the coach
turns it on from their account page (User.email_coach_summary)."""
import logging
from datetime import date, datetime, timedelta

from flask import current_app

from app import db
from app.models.team_organization import TeamOrganization
from app.models.user import ROLE_ORDER, User
from app.utils.email import email_configured, is_real_email, send_email

logger = logging.getLogger(__name__)

REPEAT_DAYS = 7  # still open this long after the last email: say so once more
REMINDED = '__reminded__'  # in summary_keys once that reminder has gone


def outstanding(team_id, today=None):
    """The team's "Needs attention" list, each item with a `key` that stays
    the same from day to day and a full link."""
    from app import onboarding
    from app.models.team_settings import TeamSettings
    from app.utils import dashboard

    today = today or date.today()
    base = (current_app.config.get('BASE_URL') or '').rstrip('/')
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    # url_for needs a request; nobody is signed in for this one
    with current_app.test_request_context(base_url=base or None):
        coming, _ = dashboard.coming_up(team_id, today, None, True, settings)
        items = dashboard.needs_attention(team_id, today, coming, settings, onboarding.roster_signup(team_id))
    for item in items:
        item['key'] = f"{item['icon']}|{item['url']}"
        item['link'] = f"{base}{item['url']}" if base else ''
    return items


def _body(user, team, items, fresh):
    lines = [f'Hi {user.username.split()[0]},', '',
             f'{len(items)} thing{"s" if len(items) != 1 else ""} at {team.name} '
             f'{"are" if len(items) != 1 else "is"} waiting on a coach:', '']
    for item in items:
        new = ' (new)' if item['key'] in fresh and len(fresh) != len(items) else ''
        lines.append(f'- {item["title"]}{new}')
        if item.get('detail'):
            lines.append(f'  {item["detail"]}')
        if item['link']:
            lines.append(f'  {item["link"]}')
    base = (current_app.config.get('BASE_URL') or '').rstrip('/')
    lines += ['', 'You get this because you turned on coach summary emails. It only comes when '
              'something new needs you, with one reminder a week later if it\'s still open.',
              'Turn it off on your account page' + (f': {base}/auth/account' if base else '.')]
    return '\n'.join(lines)


def send_due(today=None, now=None):
    """Email every opted-in coach whose team has something new waiting (or
    still waiting a week on). Commits. Returns how many emails went."""
    if not email_configured():
        return 0
    today = today or date.today()
    now = now or datetime.utcnow()
    sent = 0
    by_team = {}
    users = User.query.filter(User.email_coach_summary.is_(True), User.email.isnot(None)).all()
    for user in users:
        if not is_real_email(user.email) or getattr(user, 'is_demo', False):
            continue
        for membership in user.memberships:
            if ROLE_ORDER.get(membership.role, 0) < ROLE_ORDER['coach']:
                continue
            team_id = membership.team_organization_id
            try:
                if team_id not in by_team:
                    by_team[team_id] = outstanding(team_id, today)
                sent += _send_one(user, membership, by_team[team_id], now)
            except Exception:
                logger.exception('Coach summary for user %s, team %s failed', user.id, team_id)
                db.session.rollback()
    return sent


def _send_one(user, membership, items, now):
    keys = [i['key'] for i in items]
    before = set(membership.summary_keys or [])
    fresh = [k for k in keys if k not in before]
    last = membership.summary_sent_at
    if last is not None and last.date() == now.date():
        return 0  # never more than one a day
    # One reminder only: after that they hear again when something new comes up
    stale = (bool(keys) and last is not None and REMINDED not in before
             and now - last >= timedelta(days=REPEAT_DAYS))
    if not keys or not (fresh or stale):
        if not keys and before:
            # All dealt with: the next thing to come up counts as new
            membership.summary_keys = []
            db.session.commit()
        return 0
    team = db.session.get(TeamOrganization, membership.team_organization_id)
    subject = (f'{team.name}: {items[0]["title"]}' if len(items) == 1
               else f'{team.name}: {len(items)} things need a coach')
    if not send_email(user.email, subject, _body(user, team, items, set(fresh))):
        return 0
    membership.summary_sent_at = now
    membership.summary_keys = keys + ([] if fresh else [REMINDED])
    db.session.commit()
    return 1
