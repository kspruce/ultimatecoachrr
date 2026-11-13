"""Starting points for a new season plan (Season plan > Create a plan).

A template has phases (name and length), weekly themes, milestones and a
page or two. Dates come from the start date the coach picks. Squad themes
are given per squad position ("first squad", "second squad") and go to the
plan's squads in the order the coach lists them; with no squads they're
left out. Everything can be changed once the plan exists.
"""

HOW_WE_TRAIN = """# How we train

Every session has the same shape, so players know what to expect and coaches can plan quickly.

| Part | Time | What happens |
| --- | --- | --- |
| Warm-up | 15 min | Dynamic warm-up, then throwing in pairs |
| Skill | 25 min | This week's theme as a drill or a small game |
| Game | 30 min | A small-sided game whose rules reward the skill |
| Scrimmage | 30 min | Full game; one thing to look for from the theme |
| Close | 5 min | What went well, one thing to work on |

**How to use this plan**

- The week's theme is what every activity builds towards. If the session runs short, keep the game and cut the drill.
- Coaches: open each week to add session notes. A timed table under the notes can be turned into a session (Season plan > Sessions).
- Players: the overview shows this week and what is coming up.
"""

TESTS_PAGE = """# Measuring improvement

Run the same four quick tests at the start, in the middle and at the end, so everyone can see their progress.

| Test | How |
| --- | --- |
| Throwing accuracy | 10 throws each side to a target 15 m away; count catches |
| Breaking the mark | 10 throws past a marker; count completions |
| Change of direction | 5-10-5 shuttle, timed |
| Catching | 20 catches under light pressure; count clean catches |

Record results in Training > Programmes (add the tests to a programme) or a shared sheet.
"""


def _weeks(rows):
    """{week number: row} from (weeks, row) blocks run one after another."""
    out, n = {}, 1
    for count, row in rows:
        for _ in range(count):
            out[n] = row
            n += 1
    return out


SEASON_16 = {
    'key': 'season-16',
    'name': '16-week season, one squad',
    'hint': 'Four phases from the basics to a peak tournament, with a theme for every week.',
    'summary': 'A 16-week season: build the basics, add team play, compete and review.',
    'phases': [
        {'name': 'Foundations', 'weeks': 4, 'aim': 'Every player throws, catches and moves better',
         'focus': 'Throwing, catching, cutting and marking'},
        {'name': 'Building', 'weeks': 4, 'aim': 'Skills hold up against a defence',
         'focus': 'Breaking the mark, person defence, a first offence'},
        {'name': 'Competing', 'weeks': 6, 'aim': 'Play well as a team at tournaments',
         'focus': 'Zones, endzone offence, learning from each event', 'events': 'Tournament in week 12'},
        {'name': 'Peak and review', 'weeks': 2, 'aim': 'Play our best at the last event; learn for next season',
         'focus': 'Game plans, sharp short sessions', 'events': 'Final tournament in week 16'},
    ],
    'weeks': {
        1: {'block': 'Throwing base', 'theme': 'Grip, pivot, backhand and forehand', 'off_pitch': 'Baseline tests'},
        2: {'block': 'Throwing base', 'theme': 'Catching and the dump-swing'},
        3: {'block': 'Getting open', 'theme': 'Cutting: timing, under and away'},
        4: {'block': 'Getting open', 'theme': 'Marking and the force'},
        5: {'block': 'Team offence', 'theme': 'Vertical stack: spacing and clearing'},
        6: {'block': 'Team offence', 'theme': 'Breaking the mark: inside and around'},
        7: {'block': 'Defence', 'theme': 'Person defence: position and reading the thrower'},
        8: {'block': 'Defence', 'theme': 'Hucks and deep defence'},
        9: {'block': 'Second offence', 'theme': 'Horizontal stack, or a second set play'},
        10: {'block': 'Zones', 'theme': 'Zone defence basics', 'off_pitch': 'Retest'},
        11: {'block': 'Zones', 'theme': 'Zone offence: handlers and poppers'},
        12: {'block': 'Tournament', 'theme': 'Light session: set plays and pulls', 'event': True},
        13: {'block': 'Review', 'theme': 'Fix the two biggest problems from the tournament'},
        14: {'block': 'Endzone', 'theme': 'Endzone offence and pulling'},
        15: {'block': 'Peak', 'theme': 'Game plans and calls; short, sharp session'},
        16: {'block': 'Final tournament', 'theme': 'Warm-up and set plays only', 'event': True,
             'off_pitch': 'Final tests and player survey'},
    },
    'milestones': [
        (1, None, 'Baseline tests'),
        (10, None, 'Retest: check progress against the baseline'),
        (12, None, 'First tournament; review what went well and what to fix'),
        (16, None, 'Final tests, player survey and end-of-season review'),
    ],
    'pages': [('How we train', HOW_WE_TRAIN), ('Measuring improvement', TESTS_PAGE)],
}

FULL_YEAR = {
    'key': 'full-year',
    'name': 'Full year, two squads',
    'hint': 'Off-season to peak in 40 weeks: one shared skill a week, with a theme for each squad.',
    'summary': ('A full year for a club with two squads: one shared skill each week in the joint session, '
                'which each squad then uses in its own tactics.'),
    'phases': [
        {'name': 'Foundations', 'weeks': 11, 'aim': 'Every player\'s technique improves; new players join',
         'focus': 'Throwing, footwork, marking and cutting; a shared vocabulary'},
        {'name': 'Pressure and trials', 'weeks': 9, 'aim': 'Skills hold up against a defence; squads picked fairly',
         'focus': 'Constraint games; first team structures', 'events': 'Trials'},
        {'name': 'Early season', 'weeks': 10, 'aim': 'Build the playbook through the first events',
         'focus': 'Zones, endzone calls, reviewing every event', 'events': 'First tournaments'},
        {'name': 'Peak', 'weeks': 8, 'aim': 'Play our best at the main event',
         'focus': 'Scouting and game plans; shorter, sharper sessions', 'events': 'Main event'},
        {'name': 'Review', 'weeks': 2, 'aim': 'Learn and keep players',
         'focus': 'Final tests, player survey, captains\' review'},
    ],
    'weeks': _weeks([
        (2, {'block': 'Throwing', 'theme': 'Grip, pivot and the backhand',
             'squads': ['Throwing under a mark', 'Throwing in pairs to targets']}),
        (2, {'block': 'Catching and resets', 'theme': 'Catching and the dump-swing',
             'squads': ['Resets under pressure', 'Dump and swing']}),
        (3, {'block': 'Getting open', 'theme': 'Cutting: timing and space',
             'squads': ['Horizontal stack cutting', 'Vertical stack, cutting from the back']}),
        (2, {'block': 'Marking', 'theme': 'Marking and the force',
             'squads': ['Team defence: force and poach', 'Person defence basics']}),
        (2, {'block': 'Breaking the mark', 'theme': 'Inside and around breaks',
             'squads': ['Breaks in the stack', 'Breaks in pairs and threes']}),
        (3, {'block': 'Pressure', 'theme': 'Skills against a defence: small-sided games',
             'squads': ['Main offence against person defence', 'Vertical stack against person defence']}),
        (3, {'block': 'Trials', 'theme': 'Trials: the same games and tests as the off-season', 'event': True}),
        (3, {'block': 'Team defence', 'theme': 'Reading the thrower',
             'squads': ['Switches and help defence', 'Poach and clog near the disc']}),
        (3, {'block': 'Zones', 'theme': 'Throwing in wind',
             'squads': ['Zone offence: around, through and over', 'Zone offence: bucket and swing']}),
        (1, {'block': 'Tournament', 'theme': 'Light session: set plays', 'event': True}),
        (2, {'block': 'Review', 'theme': 'Fix what the tournament showed',
             'squads': ['Endzone calls', 'Endzone offence']}),
        (1, {'block': 'Tournament', 'theme': 'Light session: set plays', 'event': True}),
        (3, {'block': 'Playbook', 'theme': 'Pulls and the first throws of a point',
             'squads': ['Zone defence and switching', 'Basic zone defence']}),
        (3, {'block': 'Scouting', 'theme': 'One fundamental refresher a week',
             'squads': ['Plans A, B and C', 'Game plans and calls']}),
        (2, {'block': 'Peak', 'theme': 'Short, sharp sessions; no new material',
             'squads': ['Game plan run-throughs', 'Game plan run-throughs']}),
        (2, {'block': 'Taper', 'theme': 'Light: throwing and set pieces'}),
        (1, {'block': 'Main event', 'theme': 'Warm-up and set plays only', 'event': True}),
        (2, {'block': 'Review', 'theme': 'Final tests and a fun session', 'off_pitch': 'Player survey'}),
    ]),
    'milestones': [
        (1, 2, 'Baseline tests'),
        (15, 17, 'Trials and squad selection'),
        (21, None, 'Retest: check progress against the baseline'),
        (38, None, 'Main event'),
        (39, 40, 'Final tests, player survey and captains\' review'),
    ],
    'pages': [('How we train', HOW_WE_TRAIN), ('Measuring improvement', TESTS_PAGE)],
}

TEMPLATES = [SEASON_16, FULL_YEAR]
BY_KEY = {t['key']: t for t in TEMPLATES}


def template_weeks(template):
    return sum(p['weeks'] for p in template['phases'])
