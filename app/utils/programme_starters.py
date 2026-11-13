"""Starter programmes any club can add with one click (Training >
Programmes > Starter templates). Each is written in the import format and
built through the same import (programme_import.parse and build), as a
template the club then copies into a programme with a start date.
"""
from app.utils import programme_import as pimport


def _rows(columns, rows):
    return [columns] + [[str(r.get(c, '')) for c in columns] for r in rows]


def _week_rows(track, number, title, objective, sessions, kind=None, first=None):
    """Rows for one week: sessions are (title, type, minutes, focus,
    [exercises], requirement). Every row names its track, week and session;
    the week's and each session's details go on their first row."""
    week = {'week_title': title, 'week_objective': objective}
    if kind:
        week['week_type'] = kind
    if first is not None:
        week.update(track_first_week=first, track_start_offset=0)
    out = []
    for s_title, s_type, minutes, focus, exercises, requirement in sessions:
        details = {'session_type': s_type, 'session_minutes': minutes, 'session_focus': focus,
                   'requirement': requirement, 'log_fields': 'duration_minutes, rpe',
                   'warmup': '10 min: jog, leg swings, skips, lunges, build-up runs'}
        for i, ex in enumerate(exercises or [{}]):
            row = {'track': track, 'week': number, 'session': s_title}
            if not out:
                row.update(week)
            if i == 0:
                row.update(details)
            row.update(ex)
            out.append(row)
    return out


def _ex(name, sets='', reps='', distance='', seconds='', rest='', intensity='', instructions=''):
    return {'exercise': name, 'sets': sets, 'reps': reps, 'distance_m': distance, 'duration_s': seconds,
            'rest': rest, 'intensity': intensity, 'instructions': instructions}


def _off_season_10():
    """10 weeks, no equipment: speed and agility, bodyweight strength and
    conditioning. Week 5 is lighter; tests in weeks 1 and 10."""
    rows = []
    speed = [
        ('Acceleration', 'Drive from a standing start', [
            _ex('Falling starts', 6, distance=10, rest='Walk back', intensity='Max',
                instructions='Lean until you have to run; stay low, drive the arms'),
            _ex('Sprints', 6, distance=20, rest='Walk back', intensity='Max')]),
        ('Change of direction', 'Plant, drop the hips and push away', [
            _ex('5-10-5 shuttle', 6, rest='90 s', intensity='Max', instructions='Touch the line with your hand'),
            _ex('Cut-and-go', 8, distance=15, rest='Walk back', intensity='Fast',
                instructions='Sharp cut at 10 m, like an in-cut from the stack')]),
        ('Top speed', 'Relax at full speed', [
            _ex('Flying 20s', 5, distance=20, rest='2 min', intensity='Max',
                instructions='20 m build-up, then 20 m at full speed'),
            _ex('Deceleration drills', 6, distance=15, rest='Walk back',
                instructions='Sprint and stop within three steps')]),
        ('Reactive agility', 'React to a partner or a call', [
            _ex('Mirror drill', 6, seconds=10, rest='50 s', instructions='Follow a partner\'s cuts'),
            _ex('Reaction sprints', 8, distance=10, rest='Walk back', instructions='Go on a clap or a dropped disc')]),
    ]
    strength = [
        _ex('Squats', 3, '15', rest='60 s'), _ex('Reverse lunges', 3, '10 each leg', rest='60 s'),
        _ex('Single-leg glute bridge', 3, '12 each leg', rest='45 s'), _ex('Press-ups', 3, '10-15', rest='60 s'),
        _ex('Plank', 3, seconds=40, rest='30 s'), _ex('Side plank', 2, seconds=30, rest='30 s',
                                                        instructions='Each side'),
    ]
    jumps = [
        _ex('Squat jumps', 3, '8', rest='90 s', intensity='Explosive', instructions='Land quietly'),
        _ex('Lateral bounds', 3, '6 each side', rest='90 s', instructions='Stick each landing for a second'),
        _ex('Single-leg Romanian deadlift', 3, '10 each leg', rest='60 s', instructions='Slow on the way down'),
        _ex('Copenhagen plank', 2, seconds=20, rest='45 s', instructions='Each side; knee on a bench to start'),
    ]
    conditioning = {
        'build': ('Intervals', [_ex('Run 30 s hard, 30 s easy', 2, '8', rest='3 min between sets', intensity='RPE 8')]),
        'longer': ('Tempo runs', [_ex('Tempo run', 8, distance=100, rest='Walk 50 m', intensity='70-75%')]),
        'game': ('Game-speed repeats', [
            _ex('Point simulation', 6, seconds=45, rest='90 s', intensity='Game pace',
                instructions='Cut, sprint deep, jog back, cut again, as in a long point')]),
    }
    for week in range(1, 11):
        light = week == 5
        title = {1: 'Baseline week', 5: 'Lighter week', 10: 'Retest week'}.get(week)
        drill_title, focus, drills = speed[(week - 1) % len(speed)]
        sets = 'Half the usual sets' if light else ''
        rows += _week_rows('Speed & agility', week, title or drill_title,
                           'Run the tests before the session' if week in (1, 10) else focus,
                           [(drill_title, 'sprint', 40, (sets + '. ' if sets else '') + focus, drills, 'required')],
                           kind='deload' if light else None, first=1 if week == 1 else None)
        rows += _week_rows('Strength', week, 'Lighter week' if light else ('Strength A and B'),
                           'Two sessions: A for strength, B for jumping and single-leg control', [
                               ('Strength A', 'strength', 35, 'Slow and controlled' + ('; two sets each' if light else ''),
                                strength, 'required'),
                               ('Strength B', 'strength', 30, 'Quality landings', jumps,
                                'optional' if light else 'required'),
                           ], kind='deload' if light else None, first=1 if week == 1 else None)
        key = 'build' if week <= 4 else ('longer' if week <= 7 else 'game')
        c_title, c_ex = conditioning[key]
        rows += _week_rows('Conditioning', week, c_title, 'Build the engine for long points', [
            (c_title, 'conditioning', 30, 'Steady effort you could repeat', c_ex, 'optional' if light else 'required'),
            ('Pick-up or hat game', 'conditioning', 60, 'Any ultimate counts', [], 'optional'),
        ], kind='deload' if light else None, first=1 if week == 1 else None)
    tests = [
        {'test': '10 m sprint', 'unit': 's', 'measurement': 'time', 'attempts': 3, 'aggregation': 'best',
         'better': 'lower', 'min': 1, 'max': 4, 'description': 'Acceleration from a standing start',
         'milestone_track': 'Speed & agility', 'baseline_week': 1, 'retest_weeks': 10},
        {'test': '5-10-5 shuttle', 'unit': 's', 'measurement': 'time', 'attempts': 2, 'aggregation': 'best',
         'better': 'lower', 'min': 3, 'max': 9, 'description': 'Change of direction',
         'milestone_track': 'Speed & agility', 'baseline_week': 1, 'retest_weeks': 10},
        {'test': 'Standing broad jump', 'unit': 'cm', 'measurement': 'distance', 'attempts': 3,
         'aggregation': 'best', 'better': 'higher', 'min': 50, 'max': 350, 'description': 'Leg power',
         'milestone_track': 'Speed & agility', 'baseline_week': 1, 'retest_weeks': 10},
    ]
    return _rows(pimport.PROGRAMME_COLUMNS, rows), _rows(pimport.TEST_COLUMNS, tests)


def _in_season_6():
    """Six weeks to keep fitness up during the season: one short session a
    week next to training."""
    rows = []
    for week in range(1, 7):
        rows += _week_rows('Maintenance', week, 'Tournament week' if week in (3, 6) else 'Training week',
                           'Keep speed and strength without tiring legs before games', [
                               ('Speed and strength', 'strength', 30,
                                'Short and sharp; at least two days before a tournament', [
                                    _ex('Sprints', 4, distance=20, rest='Walk back', intensity='Max'),
                                    _ex('Squat jumps', 3, '5', rest='90 s'),
                                    _ex('Single-leg Romanian deadlift', 2, '8 each leg'),
                                    _ex('Copenhagen plank', 2, seconds=20, instructions='Each side'),
                                ], 'optional' if week in (3, 6) else 'required'),
                               ('Recovery', 'recovery', 20, 'After a tournament or a hard session', [
                                   _ex('Easy jog or bike', seconds=600),
                                   _ex('Stretch: hips, hamstrings, calves', seconds=600)], 'optional'),
                           ], first=1 if week == 1 else None)
    return _rows(pimport.PROGRAMME_COLUMNS, rows), []


STARTERS = [
    {'key': 'off-season-10', 'name': '10-week off-season fitness (no equipment)',
     'description': 'Speed and agility, bodyweight strength and conditioning, with a lighter week 5 and '
                    'tests in weeks 1 and 10. Everything can be done on a field.',
     'rows': _off_season_10},
    {'key': 'in-season-6', 'name': '6-week in-season maintenance',
     'description': 'One short speed and strength session a week alongside training, lighter on tournament '
                    'weeks, plus optional recovery.',
     'rows': _in_season_6},
]
BY_KEY = {s['key']: s for s in STARTERS}


def parsed(starter):
    programme_rows, test_rows = starter['rows']()
    return pimport.parse(programme_rows, test_rows), pimport.content_hash(programme_rows, test_rows)
