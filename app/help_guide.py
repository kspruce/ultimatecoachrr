# app/help_guide.py
"""What's on the site and how to use it, in one place.

The How to Use guide, the public About page, the Features settings page and
the "How this page works" link in the navbar all read from here, so a
feature is described once. Features are grouped by when a team uses them
(setting up, planning, training, teaching, game day, review) rather than by
menu, and each one names the TeamSettings flag that turns it on.

Steps may hold a little HTML (<em>, <strong>); they're written here, never
taken from users, so they're marked safe.
"""
from dataclasses import dataclass, field
from typing import Optional

from markupsafe import Markup


@dataclass(frozen=True)
class Feature:
    key: str            # page anchor on the guide, e.g. 'playbook'
    title: str
    icon: str
    summary: str        # what you get from it, in a sentence
    endpoint: str       # where the button goes
    link_label: str
    section: str
    steps: tuple = ()
    coach_steps: tuple = ()  # extra steps only coaches see
    flag: Optional[str] = None       # TeamSettings flag that turns it on
    coach_only: bool = False         # players never see it
    # A Jinja global that must also say yes (e.g. programmes_nav), for
    # features that only show when there's something in them
    nav_check: Optional[str] = None
    # Endpoint prefixes whose pages this feature explains (longest wins)
    pages: tuple = field(default_factory=tuple)
    # Where coaches go instead, when that's a different page
    coach_endpoint: Optional[str] = None
    coach_link_label: Optional[str] = None


def _m(*lines):
    return tuple(Markup(line) for line in lines)


SECTIONS = [
    {'key': 'setup', 'title': 'Set up the team', 'icon': 'bi-people-fill',
     'pitch': 'Your roster, seasons, squads and the roles people play, all in one place.'},
    {'key': 'plan', 'title': 'Plan the season', 'icon': 'bi-calendar-range-fill',
     'pitch': 'Tournaments, the calendar, a week-by-week season plan and off-season programmes.'},
    {'key': 'training', 'title': 'Run training', 'icon': 'bi-lightning-charge-fill',
     'pitch': "Session plans built from your drills, who's coming, fitness tests and feedback."},
    {'key': 'teach', 'title': 'Teach how you play', 'icon': 'bi-book-fill',
     'pitch': 'An animated playbook and written theory, so everyone learns the same game.'},
    {'key': 'gameday', 'title': 'Game day', 'icon': 'bi-controller',
     'pitch': 'Scout the opposition, pick the line and record every point from the sideline.'},
    {'key': 'review', 'title': 'Review and improve', 'icon': 'bi-graph-up',
     'pitch': "Stats that build themselves as you record, and video clips to learn from."},
]


FEATURES = [
    # ── Set up the team ──────────────────────────────────────
    Feature('roster', 'Team Roster', 'bi-people', 'Every player on the team, with their number, '
            'position and the account they log in with.', 'team.index', 'Open Roster', 'setup',
            steps=_m('Go to Club → Team Roster',
                     'Add players one at a time, or paste a whole spreadsheet with <strong>Bulk Import</strong>',
                     'Click a player for their profile, stats and roles'),
            coach_steps=_m('Tick <em>Auto-create login accounts</em> on Bulk Import to make logins for everyone with an email',
                           'Or turn on the team join link under Members and share it in the team chat'),
            pages=('team.index', 'team.add_player', 'team.bulk_import', 'team.player_detail',
                   'team.edit_player')),
    Feature('seasons', 'Seasons & Squads', 'bi-calendar3', 'Start a new season without losing '
            'anything; every page shows the season you pick.', 'seasons.index', 'Seasons & Squads',
            'setup', coach_only=True,
            steps=_m('Pick a season (or All time) from the season menu at the top',
                     "Start a new season from Seasons &amp; squads: last season's roster carries over",
                     'Add squads (1s, 2s) so sessions, tournaments and stats can be split by squad'),
            pages=('seasons.',)),
    Feature('roles', 'Roles', 'bi-diagram-3', 'Your team\'s roles, like O-line initiation cutter, '
            'and who plays each one this season.', 'roles.index', 'Roles', 'setup', coach_only=True,
            steps=_m('Start from the suggested roles under Club → Roles, then rename and add your own',
                     "Add players to each role, first choice first; the star marks each player's main role",
                     'Watch for roles with nobody, only one player, or only one gender',
                     "Players say which roles they'd like on their profile; the playbook says what each role does in each play"),
            pages=('roles.',)),

    # ── Plan the season ──────────────────────────────────────
    Feature('tournaments', 'Tournaments', 'bi-trophy', "One page per tournament: who's coming, "
            'the squad, the games and the stats.', 'tournament.index', 'View Tournaments', 'plan',
            steps=_m("Players answer I'm in / Maybe / Can't on the tournament's Overview",
                     'Everyone sees the squad and their game times once they\'re announced'),
            coach_steps=_m('Create a tournament with dates, location and a reply-by date; anyone who hasn\'t replied gets one reminder',
                           'Pick the squad on the Squad tab and set each game\'s line-up on Games',
                           "Stat takers find the tournament's Game Day numbers on its Stats tab"),
            pages=('tournament.',)),
    Feature('calendar', 'Team Calendar', 'bi-calendar3', 'Every game, practice and tournament in '
            'one calendar, and on your phone.', 'calendar.index', 'Open Calendar', 'plan',
            steps=_m('Browse upcoming events by month',
                     'Click any event for details and to say if you can make it',
                     'Subscribe from Google, Apple or Outlook calendar so your sessions and tournaments show on your phone'),
            pages=('calendar.',)),
    Feature('season_plan', 'Season Plan', 'bi-calendar-range-fill', "The season's phases, every "
            "week's themes for each squad, and the full session notes.", 'season_plan.index',
            'Season Plan', 'plan', flag='season_plan_enabled', nav_check='season_plan_nav',
            steps=_m("Open the overview to see this week and what's coming up",
                     'Filter the week list by phase or squad',
                     'Open a week for its full session notes',
                     "Open Classroom for each off-pitch session's prep, join link, recording and summary"),
            coach_steps=_m('Choose what players can see under Player access',),
            pages=('season_plan.',)),
    Feature('programmes', 'Programmes', 'bi-journal-check', 'Off-season and gym programmes, week '
            "by week, with each player's log.", 'programmes.index', 'Programmes', 'plan',
            nav_check='programmes_nav',
            steps=_m("Open a programme to see this week and what's next",
                     'Log each session as you do it, from your phone'),
            coach_steps=_m("Build programmes, publish new versions, and see who's keeping up on the dashboard",),
            pages=('programmes.',)),
    Feature('handbook', 'Leadership Handbook', 'bi-book', 'How you lead, coach and build the team, '
            'for captains and coaches only.', 'handbook.index', 'Handbook', 'plan',
            flag='leadership_handbook_enabled', coach_only=True, nav_check='handbook_nav',
            steps=_m('Read it section by section, or search it',
                     'Edit a page when the way you do things changes'),
            pages=('handbook.',)),

    # ── Run training ─────────────────────────────────────────
    Feature('sessions', 'Session Plans', 'bi-calendar-check', "Regular training dates, who's "
            'coming, plans and attendance.', 'session.index', 'Session Plans', 'training',
            flag='sessions_enabled',
            steps=_m('Answer under Training → My Availability, for one date or as your usual',
                     'Published plans show what the session covers before you arrive'),
            coach_steps=_m('Set up a Training Schedule (e.g. Saturdays for everyone, Wednesdays for the 1s) and the dates appear',
                           "Who's Coming shows everyone's answers at once; Maybes get one reminder",
                           'Build the plan from the library\'s drills, then take the register from the answers'),
            pages=('session.', 'training.')),
    Feature('drills', 'Drill Library', 'bi-clipboard2-check', 'Store and reuse drills across '
            'sessions, drawn and animated on the field.', 'session.drills', 'Drill Library',
            'training', flag='drills_enabled',
            steps=_m('Browse the library to find drills by type',
                     'Open a drill to watch its stages play as an animation'),
            coach_steps=_m('Add a drill with a description, category and diagram',
                           'Draw it in stages: press <em>Next stage</em> and players move to the ends of their arrows',
                           'Attach drills to session plans'),
            pages=('session.drill', 'session.add_drill', 'session.edit_drill', 'session.create_drill',
                   'session.manage_drill')),
    Feature('fitness', 'Fitness', 'bi-heart-pulse', "Four ultimate fitness tests, everyone's PBs "
            'and an opt-in leaderboard.', 'fitness.index', 'Fitness', 'training',
            flag='fitness_enabled',
            steps=_m('Log your own results and set yourself targets',
                     'Choose whether you appear on the leaderboard'),
            coach_steps=_m('Run a test day: 10 m sprint, pro agility, broad jump and the Yo-Yo test, and enter everyone at once',),
            pages=('fitness.',)),
    Feature('feedback', 'Player Feedback', 'bi-chat-square-heart', "Coaches' notes on each "
            'player. They stay with the coaches until a coach shares them.', 'feedback.mine',
            'My Feedback', 'training',
            steps=_m('Read shared notes under Training → My Feedback; new ones show on the home page',),
            coach_endpoint='feedback.hub', coach_link_label='Player Feedback',
            coach_steps=_m('Write notes from a session (Quick Feedback), a game, a clip\'s Feedback tab or the player\'s page',
                           'Tick <em>Share with the player</em> for the ones they should read'),
            pages=('feedback.',)),

    # ── Teach how you play ───────────────────────────────────
    Feature('playbook', 'Playbook', 'bi-book-fill', 'Your offence and defence plays, drawn on the '
            'field in stages so players can watch them move.', 'playbook.index', 'Playbook',
            'teach', flag='playbook_enabled',
            steps=_m('See your own role first, or pick a role to see just that path',
                     'Fade or hide the defence, mark plays as learned and flick through the Game-day cards',
                     "Tap a play's picture in the list, a session or a card to watch it there; <em>Video</em> under the animation saves it to send in a chat"),
            coach_steps=_m('<em>New play</em> → <em>Draw a Play</em> opens the editor: place players, draw cuts and throws, add a stage for each step; right-click or long-press a player to give them a team role',
                           '<em>Edit details</em> adds the call, the hand signal, what each role does, and links to theory, drills and clips',
                           'Moving plays over from Ultiplays: <em>New play</em> → <em>Add from Ultiplays</em> adds them as drafts to redraw',
                           'Ask the team to learn a play by a date, see who has, and retire plays you stop using',
                           "Before a game, pick its plays on the game's <em>Call sheet</em>; in Game Day, choose the <em>Play called</em> each point, and <em>How our plays went</em> shows what's working"),
            pages=('playbook.',)),
    Feature('theory', 'Theory', 'bi-mortarboard-fill', 'The ideas behind how you play, written '
            'down so everyone learns the same game.', 'theory.index', 'Theory', 'teach',
            flag='theory_enabled',
            steps=_m('Read it section by section with Previous / Next, or search it',
                     'Each topic links the drills that practise it and clips that show it'),
            coach_steps=_m('Add sections and topics, written in Markdown',),
            pages=('theory.',)),

    # ── Game day ─────────────────────────────────────────────
    Feature('scouting', 'Scouting Reports', 'bi-binoculars-fill', 'Dossiers on upcoming opponents '
            'to help prepare your team.', 'scouting.index', 'Scouting Reports', 'gameday',
            flag='scouting_enabled',
            steps=_m("Open the report's phone card on the sideline",),
            coach_steps=_m('Create a scouting report linked to an upcoming game',
                           'Log their looks, key players and who marks them on the matchup board',
                           'Write the game plan and pick the plays to run against them; they become the Game-day cards for that game'),
            pages=('scouting.',)),
    Feature('games', 'Games', 'bi-controller', 'Every game, its result, its points and the stats '
            'from it.', 'game.index', 'View Games', 'gameday',
            steps=_m('Open a game for its score, points and stats',),
            coach_steps=_m('Create a game with date, opponent and location (or add it to a tournament)',
                           'On game day open it in Game Day mode to record each point'),
            pages=('game.', 'point.')),
    Feature('gameday', 'Live Game Day Tracker', 'bi-lightning-charge-fill', 'Record points in '
            'real time on the sideline: lines, throws, scores and the play called.',
            'gameday.index', 'Record', 'gameday', flag='gameday_enabled', coach_only=True,
            steps=_m('Go to <strong>Record</strong> in the menu, find the game and press <strong>Game Day</strong>',
                     'Before each point pick the seven on the field; <em>Save</em> a line and use <em>Load saved line…</em> next time',
                     'Log throws, catches, turnovers and the score; <em>Undo</em> takes back the last point and <em>Halftime</em> marks the half',
                     'Stats update straight away, so the Stats pages are ready the moment the game ends'),
            pages=('gameday.',)),

    # ── Review and improve ───────────────────────────────────
    Feature('stats', 'Statistics', 'bi-graph-up', 'Player and team numbers: holds, breaks, PER '
            'ratings and heatmaps.', 'stats_dashboard.index', 'Stats Dashboard', 'review',
            flag='stats_enabled',
            steps=_m('Stats are built automatically as points are recorded',
                     "Visit the Stats dashboard for team-wide numbers, for the season you've picked",
                     'Click any player to see their profile, where they turn it over and what to work on'),
            coach_steps=_m('Stat takers find the quick Game Day tallies under Stats → Game Day summary',),
            pages=('stats_dashboard.', 'stat.')),
    Feature('clips', 'Clip Library', 'bi-camera-video-fill', 'Video clips with notes, for review '
            'and coaching feedback.', 'clip.index', 'Clip Library', 'review', flag='clip_enabled',
            steps=_m('Add a clip from a YouTube or video link, with start and end times',
                     'Add time-stamped annotations and comments',
                     'Line clips up in a playlist and watch them back to back'),
            coach_steps=_m("Leave a player a note about a clip from its Feedback tab",),
            pages=('clip.',)),
]

BY_KEY = {f.key: f for f in FEATURES}
BY_FLAG = {f.flag: f for f in FEATURES if f.flag}


# Labels for the Features settings page, grouped as before
FEATURE_GROUPS = [
    ('Core', ['stats_enabled', 'gameday_enabled']),
    ('Coaching', ['playbook_enabled', 'theory_enabled', 'drills_enabled', 'sessions_enabled',
                  'season_plan_enabled', 'leadership_handbook_enabled']),
    ('Analysis', ['clip_enabled', 'scouting_enabled', 'fitness_enabled']),
]
FLAGS = [flag for _, flags in FEATURE_GROUPS for flag in flags]
FLAG_LABELS = {
    'stats_enabled': 'Stats', 'gameday_enabled': 'Game day', 'playbook_enabled': 'Playbook',
    'theory_enabled': 'Theory', 'drills_enabled': 'Drills', 'sessions_enabled': 'Sessions',
    'season_plan_enabled': 'Season plan', 'leadership_handbook_enabled': 'Leadership handbook',
    'clip_enabled': 'Clips', 'scouting_enabled': 'Scouting', 'fitness_enabled': 'Fitness',
}

# Starting points on the Features page; the coach can still change any switch
PRESETS = [
    {'key': 'everything', 'name': 'Everything', 'hint': 'Every feature on',
     'flags': FLAGS},
    {'key': 'competitive', 'name': 'Competitive club',
     'hint': 'Training, playbook, game day, stats, clips and scouting',
     'flags': ['stats_enabled', 'gameday_enabled', 'playbook_enabled', 'theory_enabled',
               'drills_enabled', 'sessions_enabled', 'clip_enabled', 'scouting_enabled',
               'fitness_enabled']},
    {'key': 'training', 'name': 'Training team',
     'hint': 'Sessions, drills, playbook, theory and fitness; no stats',
     'flags': ['playbook_enabled', 'theory_enabled', 'drills_enabled', 'sessions_enabled',
               'fitness_enabled']},
    {'key': 'stats', 'name': 'Stats only', 'hint': 'Record games and see the numbers',
     'flags': ['stats_enabled', 'gameday_enabled']},
]


def feature_on(settings, feature):
    """Is the team's switch for this feature on? No settings means all on,
    except the ones that start off."""
    if not feature.flag:
        return True
    if settings is None:
        return feature.flag not in ('season_plan_enabled', 'leadership_handbook_enabled')
    return bool(getattr(settings, feature.flag, True))


def guide_for(user, settings, nav=None):
    """The guide's sections for this reader: [(section, [(feature, state)])].

    state is 'on', or 'off' for a feature the team has turned off (only
    coaches see those, so they know what they could turn on). Logged-out
    visitors see everything.
    """
    nav = nav or {}
    logged_in = bool(user and user.is_authenticated)
    coach = logged_in and user.is_coach
    out = []
    for section in SECTIONS:
        items = []
        for feature in FEATURES:
            if feature.section != section['key']:
                continue
            if not logged_in:
                items.append((feature, 'on'))
                continue
            if feature.coach_only and not coach:
                continue
            if feature.key == 'feedback' and not (coach or user.player):
                continue
            if not feature_on(settings, feature):
                if coach:
                    items.append((feature, 'off'))
                continue
            check = nav.get(feature.nav_check) if feature.nav_check else None
            if check is not None and not check():
                # On, but nothing there yet (no programmes) or not for this
                # reader; coaches still get told about it
                if coach:
                    items.append((feature, 'on'))
                continue
            items.append((feature, 'on'))
        if items:
            out.append((section, items))
    return out


def feature_for_endpoint(endpoint):
    """The feature that explains a page, from its endpoint (longest prefix wins)."""
    if not endpoint:
        return None
    best, best_len = None, 0
    for feature in FEATURES:
        for prefix in feature.pages:
            if endpoint.startswith(prefix) and len(prefix) > best_len:
                best, best_len = feature, len(prefix)
    return best
