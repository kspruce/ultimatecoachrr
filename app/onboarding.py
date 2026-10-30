# app/onboarding.py
"""The getting-started guide each role sees: a short welcome and a checklist.

Steps tick themselves off from the team's real data wherever they can
("Import your roster" is done once the team has players), so people who've
already done the work never have to tick anything. Steps that are only
"go and have a look" (manual) count as done once they're opened from the
checklist; that's the only progress we store, in UserOnboarding.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from flask import current_app, url_for

from app import db
from app.models.user import ROLE_ORDER
from app.utils.email import is_real_email


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    description: str
    endpoint: str
    icon: str = 'bi-check2-circle'
    # (user, team) -> bool; None makes it a manual "go and look" step
    check: Optional[Callable] = None
    # TeamSettings flag the step needs, e.g. 'sessions_enabled'
    feature: Optional[str] = None
    optional: bool = False
    # Needs the account linked to a roster player (and links to their page)
    needs_player: bool = False
    # Shown only when this returns True, e.g. Discord being set up
    available: Optional[Callable] = None
    url_kwargs: Optional[Callable] = None  # user -> dict


# ── Checks (one cheap query each; the dashboard runs them on every visit) ──

def _exists(query):
    return db.session.query(query.exists()).scalar()


def _team_has(model):
    return lambda user, team: _exists(model.query.filter_by(team_organization_id=team.id))


def _has_players(user, team):
    from app.models.player import Player
    return _exists(Player.query.filter_by(team_organization_id=team.id))


def _has_colours(user, team):
    return bool(team.settings and team.settings.primary_color)


def _has_staff(user, team):
    from app.models.team_membership import TeamMembership
    staff_roles = [r for r, level in ROLE_ORDER.items() if level >= ROLE_ORDER['coach']]
    return _exists(TeamMembership.query.filter(TeamMembership.team_organization_id == team.id,
                                               TeamMembership.user_id != user.id,
                                               TeamMembership.role.in_(staff_roles)))


def _players_invited(user, team):
    from app.models.invite_token import InviteToken
    return team.join_enabled or _exists(InviteToken.query.filter_by(team_organization_id=team.id))


def _has_event(user, team):
    from app.models.game import Game
    from app.models.tournament import Tournament
    return (_exists(Tournament.query.filter_by(team_organization_id=team.id))
            or _exists(Game.query.filter_by(team_organization_id=team.id)))


def _discord_on(user, team):
    return bool(team.settings and team.settings.discord_enabled)


def _discord_available(endpoint):
    def available(user, team):
        return endpoint in current_app.view_functions
    return available


def _player_discord_available(user, team):
    from app.discord.api import bot_ready
    return bot_ready() and _discord_on(user, team)


def _has_rsvp(user, team):
    from app.models.session import SessionRSVP
    from app.models.tournament_rsvp import TournamentRSVP
    player = user.player
    return bool(player) and (_exists(SessionRSVP.query.filter_by(player_id=player.id))
                             or _exists(TournamentRSVP.query.filter_by(player_id=player.id)))


def _has_fitness_result(user, team):
    from app.models.fitness import FitnessRecord
    return bool(user.player) and _exists(FitnessRecord.query.filter_by(player_id=user.player.id))


def _session_plan(user, team):
    from app.models.session import SessionPlan
    return _team_has(SessionPlan)(user, team)


def _saved_drill(user, team):
    from app.models.drill import SavedDrill
    return _team_has(SavedDrill)(user, team)


def _play(user, team):
    from app.models.playbook import Play
    return _team_has(Play)(user, team)


def _fitness_test_day(user, team):
    from app.models.fitness import FitnessRecord
    return _team_has(FitnessRecord)(user, team)


def _player_id(user):
    return {'player_id': user.player.id}


# ── Steps ────────────────────────────────────────────────────

STEPS = {s.key: s for s in [
    # Running the team
    Step('roster_imported', 'Import your roster',
         'Paste or upload your player list so stats, RSVPs and selection have names to work with.',
         'team.bulk_import', 'bi-people', check=_has_players),
    Step('team_branded', 'Add your team colours',
         'Your colours and crest go on every page, so the app feels like your club.',
         'team.colour_settings', 'bi-palette', check=_has_colours),
    Step('features_chosen', 'Choose the features you want',
         "Turn off anything your team won't use (fitness, scouting, clips...) to keep the menus tidy.",
         'team.feature_settings', 'bi-sliders'),
    Step('staff_added', 'Add your coaches and captains',
         'Give the people who help run the team their own accounts with the right role.',
         'auth.add_user', 'bi-person-badge', check=_has_staff),
    Step('players_invited', 'Get your players signed up',
         'Turn on the team join link and share it, or send each player a personal invite.',
         'auth.users', 'bi-link-45deg', check=_players_invited),
    Step('first_event', 'Add a tournament or game',
         'Put your next tournament or game in so players can RSVP and you can pick the squad.',
         'tournament.index', 'bi-trophy', check=_has_event),
    Step('discord', 'Connect Discord',
         'Post training to your team Discord with Yes / Maybe / No buttons, and remind the maybes there.',
         'discord.settings', 'bi-discord', check=_discord_on, optional=True,
         available=_discord_available('discord.settings')),

    # Coaching
    Step('roster_reviewed', 'Check the roster',
         'Make sure positions, numbers and who is active are right before the season starts.',
         'team.index', 'bi-person-lines-fill'),
    Step('first_session', 'Plan your first practice',
         'Build a session from drills and components, then share it with the team.',
         'session.index', 'bi-calendar-check', check=_session_plan, feature='sessions_enabled'),
    Step('first_drill', 'Save some drills',
         'Start your drill library so sessions are quick to put together.',
         'session.drills', 'bi-diagram-3', check=_saved_drill, feature='drills_enabled'),
    Step('first_play', 'Add a play to the playbook',
         'Draw up your offence and defence so players can learn their positions.',
         'playbook.index', 'bi-journal-richtext', check=_play, feature='playbook_enabled',
         optional=True),
    Step('fitness_setup', 'Run a fitness test day',
         'Take the squad through the four fitness tests and enter everyone\'s results in one go.',
         'fitness.test_day', 'bi-heart-pulse', check=_fitness_test_day,
         feature='fitness_enabled', optional=True),

    # Game day
    Step('gameday_tour', 'Learn the game-day stat tracker',
         'See how lines, points and stats are recorded on the sideline before your first game.',
         'gameday.index', 'bi-stopwatch', feature='gameday_enabled'),
    Step('squad_checked', "Check who's coming",
         "Look at RSVPs for upcoming tournaments and chase anyone who hasn't replied.",
         'tournament.index', 'bi-clipboard-check'),

    # Everyone on the roster
    Step('profile_linked', 'Pick your name from the roster',
         'Link your account to your player profile so your stats and RSVPs are yours.',
         'auth.link_player', 'bi-person-check', check=lambda user, team: user.player is not None),
    Step('email_added', 'Add your email',
         'So you can reset your password yourself if you ever forget it.',
         'auth.account', 'bi-envelope', check=lambda user, team: is_real_email(user.email)),
    Step('rsvp_given', 'RSVP to your next practice or tournament',
         'Let the team know if you can make it. It helps with planning and selection.',
         'calendar.index', 'bi-calendar-event', check=_has_rsvp, needs_player=True),
    Step('stats_viewed', 'See your stats',
         'Your points, goals, assists and more, updated after every game.',
         'team.player_detail', 'bi-graph-up', feature='stats_enabled', needs_player=True,
         url_kwargs=_player_id),
    Step('playbook_viewed', 'Pick your role in the playbook',
         'Choose the role you usually play, and every play shows what you do first.',
         'playbook.position_view', 'bi-journal-richtext', feature='playbook_enabled',
         optional=True),
    Step('fitness_goals', 'Log a fitness PB',
         'Record a result on one of the four fitness tests and set yourself a target.',
         'fitness.player_fitness', 'bi-heart-pulse', check=_has_fitness_result,
         feature='fitness_enabled', optional=True, needs_player=True, url_kwargs=_player_id),
    Step('discord_linked', 'Link your Discord',
         'Answer with the buttons in your team Discord and get reminders there.',
         'discord.connect', 'bi-discord', check=lambda user, team: bool(user.discord_id),
         optional=True, available=_player_discord_available),
]}


# ── What each role sees ──────────────────────────────────────

ROLES = {
    'admin': {
        'name': 'Team Admin',
        'intro': "You run this team on Ultimate Coach. Let's get it set up and your people in.",
        'can': ['Add captains, coaches and players, and manage their accounts',
                'Set colours, features and integrations',
                'Plan sessions, tournaments and selection',
                'Record and review stats'],
        'steps': ['roster_imported', 'team_branded', 'features_chosen', 'staff_added',
                  'players_invited', 'first_event', 'first_play', 'fitness_setup', 'discord'],
    },
    'captain': {
        'name': 'Captain',
        'intro': ('As captain you run the team: everything on Ultimate Coach for your team is '
                  'yours to manage, from the roster and staff to sessions and game day.'),
        'can': ['Add coaches and players, and manage their accounts',
                'Set colours, features and integrations',
                'Plan sessions, tournaments and selection',
                'Run the stat tracker on game day'],
        'steps': ['profile_linked', 'email_added', 'roster_imported', 'staff_added',
                  'players_invited', 'first_event', 'team_branded', 'features_chosen',
                  'gameday_tour', 'rsvp_given', 'first_play', 'fitness_setup', 'discord'],
    },
    'coach': {
        'name': 'Coach',
        'intro': 'Plan practices, build your playbook and track how the team is doing.',
        'can': ['Plan sessions and build the drill library',
                'Manage the roster and invite players',
                'Add tournaments and games, and pick squads',
                'Record and review stats on game day'],
        'steps': ['roster_reviewed', 'first_session', 'first_drill', 'first_event',
                  'players_invited', 'gameday_tour', 'squad_checked'],
    },
    'stat_taker': {
        'name': 'Stat Taker',
        'intro': 'You keep the stats on game day. Here is how to get ready.',
        'can': ['Record points and stats on game day', 'See the whole team\'s stats'],
        'steps': ['profile_linked', 'email_added', 'gameday_tour', 'rsvp_given'],
    },
    'player': {
        'name': 'Player',
        'intro': 'Your team uses Ultimate Coach for practices, RSVPs, stats and the playbook.',
        'can': ['RSVP to practices and tournaments', 'See your stats after every game',
                'Learn the playbook', 'Track your fitness goals'],
        'steps': ['profile_linked', 'email_added', 'rsvp_given', 'stats_viewed',
                  'playbook_viewed', 'fitness_goals', 'discord_linked'],
    },
}


def role_info(user):
    return ROLES.get(user.role)


# ── Progress ─────────────────────────────────────────────────

def get_record(user, create=False):
    from app.models.onboarding import UserOnboarding
    record = UserOnboarding.query.filter_by(user_id=user.id).first()
    if record is None and create:
        record = UserOnboarding(user_id=user.id, completed_steps=[])
        db.session.add(record)
    return record


def _feature_on(team, feature):
    if not feature:
        return True
    return team.settings is None or getattr(team.settings, feature, True) is not False


def steps_for(user, team):
    info = role_info(user)
    if not info or team is None:
        return []
    steps = []
    for key in info['steps']:
        step = STEPS[key]
        if not _feature_on(team, step.feature):
            continue
        if step.available and not step.available(user, team):
            continue
        steps.append(step)
    return steps


def progress(user, team, record=None):
    """The user's checklist with each step's state, or None if their role has none."""
    steps = steps_for(user, team)
    if not steps:
        return None
    if record is None:
        record = get_record(user)
    items = []
    for step in steps:
        blocked = step.needs_player and user.player is None
        if step.check:
            done = not blocked and bool(step.check(user, team))
        else:
            done = bool(record and record.has_completed(step.key))
        items.append({'step': step, 'done': done, 'blocked': blocked,
                      'url': None if blocked else url_for('onboarding.go', key=step.key)})
    required = [i for i in items if not i['step'].optional]
    done = sum(1 for i in required if i['done'])
    return {
        'role': role_info(user),
        'items': items,
        'done': done,
        'total': len(required),
        'percent': round(done / len(required) * 100) if required else 100,
        'complete': done == len(required),
        'dismissed': bool(record and record.dismissed_at),
    }


def step_target(user, step):
    kwargs = step.url_kwargs(user) if step.url_kwargs else {}
    return url_for(step.endpoint, **kwargs)


def needs_welcome(user):
    """New to the app, or promoted since they last saw the welcome."""
    if not user.is_authenticated or user.role not in ROLES:
        return False
    record = get_record(user)
    if record is None or not record.welcomed_role:
        return True
    if record.welcomed_role == user.role:
        return False
    return ROLE_ORDER.get(user.role, 0) >= ROLE_ORDER.get(record.welcomed_role, 0)


def mark_welcomed(user):
    record = get_record(user, create=True)
    if record.welcomed_role != user.role:
        record.welcomed_role = user.role
        # A new role brings a new checklist, so show the card again
        record.dismissed_at = None
    db.session.commit()


def mark_done(user, key):
    record = get_record(user, create=True)
    record.complete(key)
    db.session.commit()


def dismiss(user):
    record = get_record(user, create=True)
    record.dismissed_at = datetime.utcnow()
    db.session.commit()


def restore(user):
    record = get_record(user, create=True)
    record.dismissed_at = None
    db.session.commit()


# ── Team view for whoever runs the team ──────────────────────

def member_status(users):
    """{user_id: {'linked', 'email', 'rsvp'}} for the users page."""
    from app.models.session import SessionRSVP
    from app.models.tournament_rsvp import TournamentRSVP
    player_ids = [u.player.id for u in users if u.player]
    rsvped = set()
    if player_ids:
        rsvped |= {pid for (pid,) in db.session.query(SessionRSVP.player_id)
                   .filter(SessionRSVP.player_id.in_(player_ids)).distinct()}
        rsvped |= {pid for (pid,) in db.session.query(TournamentRSVP.player_id)
                   .filter(TournamentRSVP.player_id.in_(player_ids)).distinct()}
    return {u.id: {'linked': u.player is not None,
                   'email': is_real_email(u.email),
                   'rsvp': bool(u.player and u.player.id in rsvped)}
            for u in users}


def roster_signup(team_id):
    """Active roster players and which of them still have no account."""
    from app.models.player import Player
    players = (Player.query.filter_by(team_organization_id=team_id, active=True)
               .order_by(Player.name).all())
    waiting = [p for p in players if p.user_id is None]
    return {'active': len(players), 'joined': len(players) - len(waiting), 'waiting': waiting}


# ── Getting-started reminder ─────────────────────────────────

# New users who haven't finished their checklist get one reminder, this many
# days after their account was made; older accounts never get one. It goes by
# email, or by Discord message to people who linked Discord but have no
# email (or turned emails off).
NUDGE_AFTER_DAYS = 3
NUDGE_WITHIN_DAYS = 30


def _steps_left(checklist):
    return [i['step'] for i in checklist['items'] if not i['done'] and not i['step'].optional]


def _nudge_body(user, team, checklist, base):
    left = _steps_left(checklist)
    lines = [f'Hi {user.username},', '',
             f"You're set up on {team.name}'s Ultimate Coach. "
             f"{len(left)} thing{'s' if len(left) != 1 else ''} on your getting-started list "
             f"{'are' if len(left) != 1 else 'is'} still to do:", '']
    for step in left:
        lines += [f'- {step.title}: {step.description}']
    lines += ['', f'Your checklist: {base}/welcome',
              f'What everything does, and how to make the site yours: {base}/how-to-use',
              '', "This is the only reminder we'll send. You can turn emails off on your account page."]
    return '\n'.join(lines)


def _nudge_dm(team, checklist, base):
    left = _steps_left(checklist)
    return (f"You're set up on {team.name}'s Ultimate Coach. Still to do: "
            f"{', '.join(step.title for step in left)}.\n"
            f"Your checklist: {base}/welcome\nHow everything works: {base}/how-to-use\n"
            "This is the only reminder you'll get.")


def send_nudges(now=None):
    """Remind each new user whose checklist isn't done, once. The daily
    background job (app/scheduler.py) runs this. Returns how many were sent."""
    from sqlalchemy import or_

    from app.discord import api, messages, notify
    from app.models.team_organization import TeamOrganization
    from app.models.user import User
    from app.utils.email import email_configured, send_email

    can_email, can_dm = email_configured(), api.bot_ready()
    base = (current_app.config.get('BASE_URL') or '').rstrip('/')
    if not base or not (can_email or can_dm):
        return 0
    now = now or datetime.utcnow()
    users = User.query.filter(User.created_at <= now - timedelta(days=NUDGE_AFTER_DAYS),
                              User.created_at >= now - timedelta(days=NUDGE_WITHIN_DAYS),
                              or_(User.email.isnot(None), User.discord_id.isnot(None))).all()
    sent = 0
    # The checklist builds its links with url_for, which needs a request
    with current_app.test_request_context(base_url=base):
        for user in users:
            emailable = can_email and is_real_email(user.email) and user.email_event_updates
            if not (emailable or (can_dm and user.discord_id)) or user.role not in ROLES:
                continue
            record = get_record(user)
            if record and (record.nudged_at or record.dismissed_at):
                continue
            team = db.session.get(TeamOrganization, user.team_organization_id)
            if team is None:
                continue
            checklist = progress(user, team, record)
            if not checklist or checklist['complete']:
                continue
            if emailable:
                went = send_email(user.email, f'Getting started with {team.name} on Ultimate Coach',
                                  _nudge_body(user, team, checklist, base))
            else:
                went = notify.dm(user.discord_id, messages.plain(_nudge_dm(team, checklist, base)))
            if went:
                get_record(user, create=True).nudged_at = now
                sent += 1
        db.session.commit()
    return sent


# ── Players who haven't signed up ────────────────────────────

# A player sent an invite this recently isn't sent another
INVITE_AGAIN_AFTER_DAYS = 3


def _join_line(team):
    from app.discord import messages
    if team.join_enabled and team.join_code:
        return f"Join here: {messages.link('auth.join_team', code=team.join_code)}"
    return 'Check your email for your invite link, or ask a coach for it.'


def signup_note(team, waiting):
    """The Discord message listing who still needs to sign up."""
    names = ', '.join(p.name for p in waiting)
    count = f"{len(waiting)} player{'s' if len(waiting) != 1 else ''}"
    return (f"{count} still need{'s' if len(waiting) == 1 else ''} to sign up for {team.name} "
            f"on Ultimate Coach, where we do RSVPs, the playbook and stats: {names}. {_join_line(team)}")


def post_signup_note(team, settings=None):
    """Post who still needs to sign up to the team's Discord. True if it went."""
    from app.discord import messages, notify
    waiting = roster_signup(team.id)['waiting']
    if not waiting:
        return False
    return notify.post(team.id, messages.plain(signup_note(team, waiting)), settings)


def _invite_body(player, team, coach, link):
    lines = [f'Hi {player.name.split()[0]},', '',
             f"{coach.username} has added you to {team.name} on Ultimate Coach, where the team "
             "does RSVPs, the playbook, stats and feedback.", '',
             f'Set up your account here (the link works for 7 days): {link}', '',
             "Already on Ultimate Coach with another team? Log in first, then open the link, "
             "and the team is added to your account."]
    return '\n'.join(lines)


def remind_unjoined(team, coach, now=None):
    """Email each active roster player without an account their own invite
    link (not anyone sent one in the last few days), and post one note to
    the team's Discord. Needs a request (for the links). Returns counts:
    emailed, recent (skipped), no_email, and whether Discord went."""
    from app.models.invite_token import InviteToken
    from app.utils.email import send_email

    now = now or datetime.utcnow()
    waiting = roster_signup(team.id)['waiting']
    out = {'waiting': len(waiting), 'emailed': 0, 'recent': 0, 'no_email': [], 'discord': False}
    for player in waiting:
        if not is_real_email(player.email):
            out['no_email'].append(player.name)
            continue
        unused = InviteToken.query.filter_by(player_id=player.id, used_at=None).all()
        if any(t.created_at and t.created_at > now - timedelta(days=INVITE_AGAIN_AFTER_DAYS)
               and not t.is_expired for t in unused):
            out['recent'] += 1
            continue
        for token in unused:
            db.session.delete(token)
        invite = InviteToken.create(player_id=player.id, team_id=team.id, created_by_id=coach.id)
        db.session.add(invite)
        db.session.flush()
        link = url_for('auth.accept_invite', token=invite.token, _external=True)
        if send_email(player.email, f'Join {team.name} on Ultimate Coach',
                      _invite_body(player, team, coach, link)):
            out['emailed'] += 1
    db.session.commit()
    if waiting:
        out['discord'] = post_signup_note(team)
    return out
