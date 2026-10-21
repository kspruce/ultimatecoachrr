"""Training programmes: any club builds, publishes and runs its own
programmes on the website; nothing about any one club is in the code.

Herd 2028 (a second club) builds a programme from scratch through the
pages; Thundering Herd's off-season plan comes in through the same
spreadsheet import any club can use.
"""
import io
import os
from datetime import date, timedelta

import pytest

from app import db
from app.models.player import Player
from app.models.programme import (
    PerformanceTest, Programme, ProgrammeEnrolment, ProgrammeExercise, ProgrammeSession, ProgrammeTrack,
    ProgrammeWeek, SessionLog, TestResult,
)
from app.utils import programme_import as pimport
from app.utils import programmes as svc
from tests import stats_data
from tests.test_teams import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERD_PLAN = os.path.join(ROOT, 'imports', 'programmes', 'thundering-herd-2025-26')


def make_player(team, name, user=None):
    player = Player(name=name, team_organization_id=team.id, active=True,
                    user_id=user.id if user else None)
    db.session.add(player)
    db.session.commit()
    return player


@pytest.fixture
def clubs(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    ids = {'herd': herd.id, 'other': other.id}
    for team, prefix in ((herd, 'herd'), (other, 'other')):
        ids[f'{prefix}_coach'] = make_user(team, f'{prefix}-coach', role='coach').id
        player_user = make_user(team, f'{prefix}-player', role='player')
        ids[f'{prefix}_player_user'] = player_user.id
        ids[f'{prefix}_player'] = make_player(team, f'{prefix.title()} Runner', player_user).id
        ids[f'{prefix}_player2'] = make_player(team, f'{prefix.title()} Second').id
    return ids


def client(app, clubs, who):
    team = clubs['herd'] if who.startswith('herd') else clubs['other']
    user = clubs[f'{who}_user'] if who.endswith('player') else clubs[who]
    return stats_data.Client(app, user, team)


def ok(response, code=200):
    assert response.status_code == code, response.get_data(as_text=True)[:2000]
    return response.get_data(as_text=True)


def latest(team_id):
    return Programme.query.filter_by(team_organization_id=team_id).order_by(Programme.id.desc()).first()


# --------------------------------------------------------------------------
# Building a programme on the website (a second club, no code changes)
# --------------------------------------------------------------------------

def build_on_site(app, clubs, name='Herd 2028 Speed', start=None):
    """Herd 2028's coach builds a programme with two tracks of different
    lengths, sessions, exercises and a test, all through the pages."""
    c = client(app, clubs, 'other_coach')
    start = start or (date.today() - timedelta(weeks=3))
    r = c.post('/programmes/new', data={'name': name, 'description': 'Our speed block',
                                        'schedule_mode': 'calendar', 'start_date': start.isoformat(),
                                        'track_name': 'Speed', 'weeks': '6'})
    assert r.status_code == 302
    with app.app_context():
        programme = latest(clubs['other'])
        pid = programme.id
    ok(c.post(f'/programmes/{pid}/tracks/add', data={'name': 'Conditioning', 'weeks': '12',
                                                     'first_week_number': '0', 'start_offset_weeks': '0'}), 302)
    with app.app_context():
        draft = db.session.get(Programme, pid).draft
        speed, cond = draft.tracks
        assert (len(speed.weeks), len(cond.weeks)) == (6, 12)
        assert [w.number for w in cond.weeks][:2] == [0, 1]
        week_ids = [w.id for w in speed.weeks]
        cond_week = cond.weeks[0].id
    # A sprint session with exercises, and a throwing session with no distances
    ok(c.post(f'/programmes/{pid}/weeks/{week_ids[0]}', data={'title': 'Acceleration', 'kind': 'training',
                                                              'objective': 'Drive phase'}), 302)
    r = c.post(f'/programmes/{pid}/weeks/{week_ids[0]}/add-session', data={'title': 'Accel', 'session_type': 'sprint'})
    sid = int(r.headers['Location'].rstrip('/').split('/')[-1])
    ok(c.post(f'/programmes/{pid}/sessions/{sid}', data={
        'title': 'Acceleration session', 'session_type': 'sprint', 'requirement': 'required', 'duration_minutes': '45',
        'log_fields': ['duration_minutes', 'rpe'], 'warmup': 'Dynamic warm-up', 'coaching_cues': 'Lean',
        'ex_id': ['new', 'new'], 'ex_name': ['10 m sprints', ''], 'ex_sets': ['15', ''], 'ex_reps': ['', ''],
        'ex_distance_m': ['10', ''], 'ex_duration_seconds': ['', ''], 'ex_rest': ['Walk back', ''],
        'ex_block': ['', ''], 'ex_intensity': ['', ''], 'ex_tempo': ['', ''], 'ex_instructions': ['Stay low', ''],
        'ex_video_url': ['', ''], 'ex_order': ['', '']}), 302)
    r = c.post(f'/programmes/{pid}/weeks/{cond_week}/add-session', data={'title': 'Throws', 'session_type': 'throwing'})
    throw_id = int(r.headers['Location'].rstrip('/').split('/')[-1])
    ok(c.post(f'/programmes/{pid}/sessions/{throw_id}', data={
        'title': 'Throwing', 'session_type': 'throwing', 'requirement': 'optional',
        'custom_fields': 'Throws on target, Max distance (m)',
        'ex_id': ['new'], 'ex_name': ['Clock drill'], 'ex_duration_seconds': ['600'], 'ex_sets': [''],
        'ex_reps': [''], 'ex_distance_m': [''], 'ex_rest': [''], 'ex_block': [''], 'ex_intensity': [''],
        'ex_tempo': [''], 'ex_instructions': ['Two throws at each point'], 'ex_video_url': [''], 'ex_order': ['']}), 302)
    # The other weeks get a session too (or are rest weeks)
    for wid in week_ids[1:]:
        c.post(f'/programmes/{pid}/weeks/{wid}/add-session', data={'title': 'Speed', 'session_type': 'sprint'})
    with app.app_context():
        for w in db.session.get(Programme, pid).draft.tracks[1].weeks[1:]:
            c.post(f'/programmes/{pid}/weeks/{w.id}', data={'kind': 'rest'})
    # A test with a baseline in week 1
    ok(c.post(f'/programmes/{pid}/tests', data={'action': 'save-test', 'name': 'Flying 20', 'unit': 's',
                                                'measurement': 'time', 'better': 'lower', 'attempts': '2',
                                                'aggregation': 'best', 'min_value': '1', 'max_value': '6'}), 302)
    ok(c.post(f'/programmes/{pid}/tests', data={'action': 'save-milestone', 'name': 'Baseline', 'kind': 'baseline',
                                                'week_id': str(week_ids[0])}), 302)
    return c, pid


def test_a_second_club_builds_and_publishes_its_own_programme(app, clubs):
    c, pid = build_on_site(app, clubs)
    page = ok(c.get(f'/programmes/{pid}/build'))
    assert 'Speed' in page and 'Conditioning' in page and 'Week 0' in page
    with app.app_context():
        programme = db.session.get(Programme, pid)
        session = programme.draft.tracks[0].weeks[0].sessions[0]
        assert session.exercises[0].distance_m == 10 and session.exercises[0].sets == '15'
        throw = programme.draft.tracks[1].weeks[0].sessions[0]
        assert throw.exercises[0].distance_m is None and throw.exercises[0].duration_seconds == 600
        assert [f['label'] for f in throw.custom_fields] == ['Throws on target', 'Max distance']
        assert throw.custom_fields[1]['unit'] == 'm'
        assert svc.validate(programme, programme.draft)[0] == []

    preview = ok(c.get(f'/programmes/{pid}/preview'))
    assert 'Acceleration session' in preview and '10 m sprints' in preview and 'Stay low' in preview
    ok(c.post(f'/programmes/{pid}/publish', data={'change_note': 'First go'}), 302)
    with app.app_context():
        programme = db.session.get(Programme, pid)
        assert programme.published.number == 1 and programme.draft is None

    # Players: the one linked to an account logs a session and sees it counted
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])],
                                                  'start_offset_weeks': '0'}), 302)
    p = client(app, clubs, 'other_player')
    page = ok(p.get(f'/programmes/{pid}/me'))
    assert 'Acceleration session' in page and 'Log it' in page
    with app.app_context():
        sid = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0].id
    ok(p.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed', 'duration_minutes': '50', 'rpe': '7',
                                                    'completed_on': date.today().isoformat()}), 302)
    with app.app_context():
        log = SessionLog.query.one()
        assert (log.duration_minutes, log.rpe, log.workload) == (50, 7, 350)
    dash = ok(c.get(f'/programmes/{pid}/dashboard'))
    assert 'Other Runner' in dash and 'Flying 20' in dash


def test_builder_reorders_duplicates_and_removes(app, clubs):
    c, pid = build_on_site(app, clubs)
    with app.app_context():
        speed = db.session.get(Programme, pid).draft.tracks[0]
        w1, w2 = speed.weeks[0].id, speed.weeks[1].id
    ok(c.post(f'/programmes/{pid}/weeks/{w1}/duplicate'), 302)
    ok(c.post(f'/programmes/{pid}/weeks/{w2}/up'), 302)
    with app.app_context():
        speed = db.session.get(Programme, pid).draft.tracks[0]
        assert len(speed.weeks) == 7
        assert speed.weeks[0].id == w1 and speed.weeks[1].id == w2
        assert speed.weeks[2].title == 'Acceleration (copy)'
        assert speed.weeks[2].sessions[0].exercises[0].name == '10 m sprints'
        assert [w.position for w in speed.weeks] == list(range(7))
    ok(c.post(f'/programmes/{pid}/weeks/{w1}/delete'), 302)
    with app.app_context():
        speed = db.session.get(Programme, pid).draft.tracks[0]
        assert len(speed.weeks) == 6 and w1 not in [w.id for w in speed.weeks]
        # The baseline milestone was in the deleted week: it's kept, with no week
        assert db.session.get(Programme, pid).draft.milestones[0].week is None


def test_duplicate_is_independent(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/duplicate', data={'name': 'Speed 2027', 'kind': 'programme'}), 302)
    with app.app_context():
        copy = latest(clubs['other'])
        assert copy.id != pid and copy.name == 'Speed 2027' and copy.source_uid == db.session.get(Programme, pid).uid
        session = copy.draft.tracks[0].weeks[0].sessions[0]
        original_session = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0]
        assert session.key != original_session.key
        sid, cid = session.id, copy.id
    ok(c.post(f'/programmes/{cid}/sessions/{sid}', data={'title': 'Changed in the copy', 'session_type': 'sprint'}), 302)
    with app.app_context():
        original = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0]
        assert original.title == 'Acceleration session'
        assert db.session.get(ProgrammeSession, sid).title == 'Changed in the copy'


# --------------------------------------------------------------------------
# Versions never rewrite history
# --------------------------------------------------------------------------

def test_publishing_a_new_version_keeps_player_logs(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])],
                                                  'start_offset_weeks': '0'}), 302)
    p = client(app, clubs, 'other_player')
    with app.app_context():
        v1 = db.session.get(Programme, pid).published
        accel = v1.tracks[0].weeks[0].sessions[0]
        week2 = v1.tracks[0].weeks[1].sessions[0]
        accel_id, accel_key, week2_id = accel.id, accel.key, week2.id
    ok(p.post(f'/programmes/{pid}/log/{accel_id}', data={'status': 'completed', 'rpe': '6', 'duration_minutes': '40'}), 302)
    ok(p.post(f'/programmes/{pid}/log/{week2_id}', data={'status': 'completed'}), 302)

    # v2: rename the week 1 session and delete the week 2 session
    ok(c.post(f'/programmes/{pid}/draft'), 302)
    with app.app_context():
        draft = db.session.get(Programme, pid).draft
        new_accel = draft.tracks[0].weeks[0].sessions[0]
        assert new_accel.key == accel_key and new_accel.id != accel_id
        new_accel_id, new_week2_id = new_accel.id, draft.tracks[0].weeks[1].sessions[0].id
    # Published rows can't be edited, only the draft's
    assert c.post(f'/programmes/{pid}/sessions/{accel_id}', data={'title': 'Hacked'}).status_code == 404
    ok(c.post(f'/programmes/{pid}/sessions/{new_accel_id}', data={'title': 'Acceleration v2', 'session_type': 'sprint',
                                                                  'requirement': 'required'}), 302)
    ok(c.post(f'/programmes/{pid}/sessions/{new_week2_id}/delete'), 302)
    ok(c.post(f'/programmes/{pid}/publish', data={'change_note': 'v2'}), 302)

    with app.app_context():
        programme = db.session.get(Programme, pid)
        assert programme.published.number == 2
        assert [v.status for v in programme.versions] == ['superseded', 'published']
        enrolment = ProgrammeEnrolment.query.one()
        assert enrolment.version_id == programme.published.id  # moved forward
        logs = {lg.session_id: lg for lg in enrolment.logs}
        # Both logs still point at the v1 rows, which still read as they did
        assert set(logs) == {accel_id, week2_id}
        assert db.session.get(ProgrammeSession, accel_id).title == 'Acceleration session'
        assert logs[accel_id].rpe == 6
        progress = svc.enrolment_progress(enrolment)
        # The renamed session still counts as done (same key); the deleted one is history
        assert progress['units'][f'session:{accel_key}'] == 'done'
        assert [lg.session_id for lg in progress['old_version_logs']] == [week2_id]
    page = ok(p.get(f'/programmes/{pid}/me'))
    assert 'Acceleration v2' in page and 'From earlier versions' in page


def test_players_can_be_kept_on_their_version(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]}), 302)
    ok(c.post(f'/programmes/{pid}/draft'), 302)
    ok(c.post(f'/programmes/{pid}/publish', data={'players': 'stay'}), 302)
    with app.app_context():
        enrolment = ProgrammeEnrolment.query.one()
        assert enrolment.version.number == 1
        eid = enrolment.id
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'update', 'enrolment_id': str(eid), 'status': 'active',
                                                  'start_offset_weeks': '0', 'move_to_current': '1'}), 302)
    with app.app_context():
        assert ProgrammeEnrolment.query.one().version.number == 2


# --------------------------------------------------------------------------
# Sharing templates
# --------------------------------------------------------------------------

def test_shared_template_copies_without_player_data(app, clubs):
    c, pid = build_on_site(app, clubs, name='Herd 2028 Speed')
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]}), 302)
    p = client(app, clubs, 'other_player')
    with app.app_context():
        sid = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0].id
    ok(p.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed', 'notes': 'SECRET-LOG-NOTE'}), 302)
    herd_coach = client(app, clubs, 'herd_coach')
    # Not shared yet: invisible to Thundering Herd
    assert 'Herd 2028 Speed' not in ok(herd_coach.get('/programmes/'))
    assert herd_coach.get(f'/programmes/shared/{pid}').status_code == 404
    ok(c.post(f'/programmes/{pid}/settings', data={'name': 'Herd 2028 Speed', 'schedule_mode': 'calendar',
                                                   'coach_notes': 'SECRET-COACH-NOTE', 'is_shared': 'on'}), 302)

    listing = ok(herd_coach.get('/programmes/'))
    assert 'Herd 2028 Speed' in listing
    page = ok(herd_coach.get(f'/programmes/shared/{pid}'))
    assert 'Acceleration session' in page
    for secret in ('Other Runner', 'SECRET-LOG-NOTE', 'SECRET-COACH-NOTE', 'Log it'):
        assert secret not in page
    # The owner's pages stay closed to the other club
    for url in (f'/programmes/{pid}', f'/programmes/{pid}/build', f'/programmes/{pid}/players',
                f'/programmes/{pid}/dashboard', f'/programmes/{pid}/export/report.csv'):
        assert herd_coach.get(url).status_code == 404, url

    ok(herd_coach.post(f'/programmes/shared/{pid}/copy', data={'name': 'Our speed block'}), 302)
    with app.app_context():
        copy = latest(clubs['herd'])
        assert copy.name == 'Our speed block' and copy.team_organization_id == clubs['herd']
        assert copy.source_team == 'Herd 2028' and copy.source_version == 1 and copy.source_kind == 'template'
        assert copy.coach_notes is None and copy.enrolments == [] and not copy.is_shared
        assert copy.draft.tracks[0].weeks[0].sessions[0].title == 'Acceleration session'
        copy_session = copy.draft.tracks[0].weeks[0].sessions[0]
        cid, copy_sid = copy.id, copy_session.id
        # Every copied row belongs to Thundering Herd
        assert {r.team_organization_id for r in ProgrammeSession.query.filter(
            ProgrammeSession.week_id.in_([w.id for t in copy.draft.tracks for w in t.weeks]))} == {clubs['herd']}
    ok(herd_coach.post(f'/programmes/{cid}/sessions/{copy_sid}', data={'title': 'Herd version', 'session_type': 'sprint'}), 302)
    with app.app_context():
        assert db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0].title == 'Acceleration session'
        assert SessionLog.query.count() == 1


# --------------------------------------------------------------------------
# Isolation between clubs and between players
# --------------------------------------------------------------------------

def test_one_club_cannot_see_or_change_another_clubs_programmes(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]}), 302)
    with app.app_context():
        programme = db.session.get(Programme, pid)
        version = programme.published
        sid = version.tracks[0].weeks[0].sessions[0].id
        wid = version.tracks[0].weeks[0].id
        tid = version.tracks[0].id
        eid = ProgrammeEnrolment.query.one().id
    herd = client(app, clubs, 'herd_coach')
    assert 'Herd 2028 Speed' not in ok(herd.get('/programmes/'))
    gets = ['', '/build', '/tests', '/preview', '/players', '/dashboard', '/settings', '/me',
            f'/players/{eid}', f'/log/{sid}?enrolment={eid}', f'/results?enrolment={eid}',
            '/export/programme.csv', '/export/tests.csv', '/export/report.csv', '/publish']
    for path in gets:
        assert herd.get(f'/programmes/{pid}{path}').status_code == 404, path
    posts = ['/draft', '/duplicate', '/archive', '/delete', '/tracks/add', f'/tracks/{tid}/delete',
             f'/weeks/{wid}/delete', f'/sessions/{sid}/delete', '/publish', '/settings', '/tests',
             f'/log/{sid}?enrolment={eid}']
    for path in posts:
        assert herd.post(f'/programmes/{pid}{path}', data={'name': 'x', 'action': 'save-test', 'unit': 's',
                                                            'status': 'completed'}).status_code == 404, path
    assert herd.post(f'/programmes/{pid}/players', data={'action': 'remove', 'enrolment_id': str(eid)}).status_code == 404
    # A coach can't put another club's player on their own programme
    herd.post('/programmes/new', data={'name': 'Herd own', 'track_name': 'T', 'weeks': '1',
                                       'start_date': date.today().isoformat()})
    with app.app_context():
        own = latest(clubs['herd'])
        week = own.draft.tracks[0].weeks[0]
        week.sessions.append(ProgrammeSession(title='S', session_type='sprint', team_organization_id=clubs['herd']))
        db.session.commit()
        hpid = own.id
    ok(herd.post(f'/programmes/{hpid}/publish', data={}), 302)
    herd.post(f'/programmes/{hpid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]})
    with app.app_context():
        assert ProgrammeEnrolment.query.filter_by(programme_id=hpid).count() == 0
        assert SessionLog.query.count() == 0
        assert db.session.get(Programme, pid).name == 'Herd 2028 Speed'


def test_players_see_only_their_own_programme_and_cannot_coach(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [
        str(clubs['other_player']), str(clubs['other_player2'])]}), 302)
    with app.app_context():
        enrolments = {e.player_id: e.id for e in ProgrammeEnrolment.query}
        sid = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0].id
    p = client(app, clubs, 'other_player')
    # Coach pages bounce players
    for path in ('/build', '/players', '/dashboard', '/settings', '/export/report.csv'):
        assert p.get(f'/programmes/{pid}{path}').status_code == 302, path
    # Naming someone else's enrolment gets nothing
    other_eid = enrolments[clubs['other_player2']]
    assert p.get(f'/programmes/{pid}/log/{sid}?enrolment={other_eid}').status_code == 404
    assert p.post(f'/programmes/{pid}/log/{sid}?enrolment={other_eid}', data={'status': 'completed'}).status_code == 404
    assert p.get(f'/programmes/{pid}/players/{other_eid}').status_code == 302
    ok(p.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed'}), 302)
    with app.app_context():
        assert [lg.enrolment.player_id for lg in SessionLog.query] == [clubs['other_player']]
    # A Thundering Herd player sees none of it
    hp = client(app, clubs, 'herd_player')
    assert hp.get(f'/programmes/{pid}/me').status_code == 404
    assert hp.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed'}).status_code == 404
    # A session from a draft (or another version) can't be logged
    ok(c.post(f'/programmes/{pid}/draft'), 302)
    with app.app_context():
        draft_sid = db.session.get(Programme, pid).draft.tracks[0].weeks[0].sessions[0].id
    assert p.post(f'/programmes/{pid}/log/{draft_sid}', data={'status': 'completed'}).status_code == 404


# --------------------------------------------------------------------------
# Tests: each programme its own
# --------------------------------------------------------------------------

def test_programmes_define_their_own_tests_and_results_are_validated(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    herd = client(app, clubs, 'herd_coach')
    herd.post('/programmes/new', data={'name': 'Throwing block', 'track_name': 'Throwing', 'weeks': '4'})
    with app.app_context():
        hpid = latest(clubs['herd']).id
    ok(herd.post(f'/programmes/{hpid}/tests', data={'action': 'save-test', 'name': 'Effective range', 'unit': 'm',
                                                    'measurement': 'distance', 'better': 'higher', 'attempts': '1'}), 302)
    with app.app_context():
        herd_tests = [t.name for t in db.session.get(Programme, hpid).draft.tests]
        other_tests = [t.name for t in db.session.get(Programme, pid).published.tests]
        assert herd_tests == ['Effective range'] and other_tests == ['Flying 20']
        assert db.session.get(Programme, hpid).draft.tests[0].higher_is_better

    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]}), 302)
    p = client(app, clubs, 'other_player')
    with app.app_context():
        version = db.session.get(Programme, pid).published
        test, ms = version.tests[0], version.milestones[0]
        tid, msid = test.id, ms.id
    # Out of range, not a number, too many attempts: rejected, nothing saved
    for attempts in (['0.5', ''], ['abc', ''], ['2', '3', '4']):
        r = p.post(f'/programmes/{pid}/results', data={'milestone_id': str(msid), f'attempt_{tid}': attempts})
        assert r.status_code == 400
    with app.app_context():
        assert TestResult.query.count() == 0
    ok(p.post(f'/programmes/{pid}/results', data={'milestone_id': str(msid), f'attempt_{tid}': ['2.31', '2.25']}), 302)
    ok(p.post(f'/programmes/{pid}/results', data={'milestone_id': '', f'attempt_{tid}': ['2.20', '']}), 302)
    with app.app_context():
        enrolment = ProgrammeEnrolment.query.one()
        summary = svc.test_summary(enrolment)[test.key if False else db.session.get(PerformanceTest, tid).key]
        assert summary['first'].value == 2.25  # best (lowest) of the baseline attempts
        assert summary['latest'].value == 2.20
        assert summary['change'] == pytest.approx(0.05)  # lower is better: an improvement
    # Re-entering the baseline replaces it rather than adding a second one
    ok(p.post(f'/programmes/{pid}/results', data={'milestone_id': str(msid), f'attempt_{tid}': ['2.40', '']}), 302)
    with app.app_context():
        assert TestResult.query.filter(TestResult.milestone_id.isnot(None)).count() == 1


def test_aggregation_and_direction():
    class T:
        pass
    t = T()
    t.aggregation, t.higher_is_better = 'best', True
    assert svc.aggregate(t, [3.0, 5.0, 4.0]) == 5.0
    t.higher_is_better = False
    assert svc.aggregate(t, [3.0, 5.0, 4.0]) == 3.0
    t.aggregation = 'mean'
    assert svc.aggregate(t, [3.0, 5.0, 4.0]) == 4.0
    t.aggregation = 'last'
    assert svc.aggregate(t, [3.0, 5.0, 4.0]) == 4.0
    assert svc.improvement(True, 10, 12) == 2 and svc.improvement(False, 10, 12) == -2
    assert svc.improvement(False, None, 12) is None


# --------------------------------------------------------------------------
# Scheduling, completion and the dashboard
# --------------------------------------------------------------------------

def make_programme(team_id, start, tracks, mode='calendar'):
    """tracks: [(name, [kinds or session lists], first_week_number, offset)]"""
    programme = Programme(team_organization_id=team_id, name='P', schedule_mode=mode, start_date=start)
    db.session.add(programme)
    draft = svc.start_draft(programme)
    for name, weeks, first, offset in tracks:
        track = ProgrammeTrack(name=name, first_week_number=first, start_offset_weeks=offset, team_organization_id=team_id)
        draft.tracks.append(track)
        for i, sessions in enumerate(weeks):
            week = ProgrammeWeek(position=i, kind='rest' if sessions == 'rest' else 'training', team_organization_id=team_id)
            track.weeks.append(week)
            if sessions == 'rest':
                continue
            for j, (title, req, group) in enumerate(sessions):
                week.sessions.append(ProgrammeSession(title=title, position=j, requirement=req, alternative_group=group,
                                                      session_type='custom', team_organization_id=team_id))
    db.session.flush()
    svc.publish(programme, None)
    db.session.commit()
    return programme


def test_schedule_tracks_offsets_pauses_and_late_joiners(app, clubs):
    start = date(2026, 1, 5)
    req = [('Run', 'required', None)]
    programme = make_programme(clubs['herd'], start, [
        ('Speed', [req] * 6, 1, 0),
        ('Conditioning', [req] * 12, 0, 2),
    ])
    version = programme.published
    speed, cond = version.tracks
    assert svc.week_start(programme, cond, cond.weeks[0]) == date(2026, 1, 19)  # starts two weeks in
    assert cond.weeks[0].number == 0 and cond.weeks[-1].number == 11
    assert svc.total_weeks(version) == 14
    assert svc.end_date(programme, version) == date(2026, 4, 12)
    # A two-week pause from 2 Feb pushes everything from then on back
    programme.pauses = [{'from': '2026-02-02', 'weeks': 2}]
    assert svc.week_start(programme, speed, speed.weeks[3]) == date(2026, 1, 26)
    assert svc.week_start(programme, speed, speed.weeks[4]) == date(2026, 2, 16)
    assert svc.end_date(programme, version) == date(2026, 4, 26)
    assert svc.current_week(programme, speed, today=date(2026, 2, 5)) is None  # paused
    programme.pauses = None

    player = db.session.get(Player, clubs['herd_player'])
    enrolment, created = svc.enrol(programme, player, today=date(2026, 1, 22))
    assert created and enrolment.start_offset_weeks == 2  # joined in week 3: starts there
    db.session.commit()
    p = svc.enrolment_progress(enrolment, today=date(2026, 2, 2))
    # Speed weeks 1-2 were before they joined; weeks 3 and 4 have ended unlogged,
    # and so have conditioning weeks 0 and 1 (programme weeks 3 and 4)
    assert p['units'][f'session:{speed.weeks[0].sessions[0].key}'] == 'not_expected'
    assert p['due'] == 4 and p['done'] == 0 and len(p['missing']) == 4
    assert p['completion'] == 0
    assert [t['week'].number for t in p['tracks']] == [5, 2]


def test_missing_is_not_skipped_and_alternatives_count_once(app, clubs):
    start = date(2026, 1, 5)
    programme = make_programme(clubs['herd'], start, [
        ('Mixed', [
            [('Hills', 'alternative', 'hills'), ('Treadmill', 'alternative', 'hills'), ('Stretch', 'optional', None)],
            [('Gym', 'required', None)],
            'rest',
            [('Gym', 'required', None)],
        ], 1, 0),
    ])
    track = programme.published.tracks[0]
    player = db.session.get(Player, clubs['herd_player'])
    enrolment, _ = svc.enrol(programme, player, start_offset_weeks=0)
    db.session.commit()
    # Nothing logged and nothing due yet: no zeros, just "not yet"
    p = svc.enrolment_progress(enrolment, today=date(2026, 1, 6))
    assert p['due'] == 0 and p['completion'] is None and p['workload_7'] is None and p['last_logged'] is None
    # Treadmill done (an alternative), week 2 gym skipped, nothing for week 4
    treadmill = track.weeks[0].sessions[1]
    gym2 = track.weeks[1].sessions[0]
    db.session.add_all([
        SessionLog(enrolment=enrolment, session=treadmill, session_key=treadmill.key, status='completed',
                   completed_on=date(2026, 1, 7), rpe=8, duration_minutes=20, team_organization_id=clubs['herd']),
        SessionLog(enrolment=enrolment, session=gym2, session_key=gym2.key, status='skipped',
                   completed_on=date(2026, 1, 14), team_organization_id=clubs['herd']),
    ])
    db.session.commit()
    p = svc.enrolment_progress(enrolment, today=date(2026, 2, 9))
    # Units due: hills group (done), week-2 gym (skipped), week-4 gym (missing). Rest week: nothing.
    assert (p['due'], p['done'], p['skipped'], len(p['missing'])) == (3, 1, 1, 1)
    assert p['missing'][0][1].position == 3
    assert p['optional_done'] == 0 and p['completion'] == 33
    assert p['workload_28'] is None  # the treadmill log is more than 28 days back
    p = svc.enrolment_progress(enrolment, today=date(2026, 1, 20))
    assert p['workload_28'] == 160
    d = svc.dashboard(programme, today=date(2026, 2, 9))
    assert (d['due'], d['done'], d['missing'], d['skipped']) == (3, 1, 1, 1)
    assert d['follow_up'] and 'completion 33%' in d['follow_up'][0]['follow_up']


def test_validation_blocks_broken_programmes(app, clubs):
    programme = Programme(team_organization_id=clubs['herd'], name='Broken', schedule_mode='calendar')
    db.session.add(programme)
    draft = svc.start_draft(programme)
    track = ProgrammeTrack(name='T', team_organization_id=clubs['herd'])
    draft.tracks.append(track)
    week = ProgrammeWeek(position=0, team_organization_id=clubs['herd'])
    track.weeks.append(week)
    week.sessions.append(ProgrammeSession(title='Alt', requirement='alternative', session_type='custom',
                                          video_url='javascript:alert(1)', team_organization_id=clubs['herd']))
    draft.tests.append(PerformanceTest(name='Bad', unit='', attempts=1, min_value=5, max_value=1,
                                       team_organization_id=clubs['herd']))
    db.session.flush()
    errors, _ = svc.validate(programme, draft)
    text = ' '.join(errors)
    for expected in ('start date', 'no group', 'web link', 'needs a unit', 'lowest allowed'):
        assert expected in text, expected
    with pytest.raises(ValueError):
        svc.publish(Programme(team_organization_id=clubs['herd'], name='x'), None)


# --------------------------------------------------------------------------
# Import and export
# --------------------------------------------------------------------------

GOOD_CSV = (
    'track,track_first_week,week,week_title,week_type,session,session_type,requirement,alternative_group,'
    'exercise,sets,reps,distance_m,duration_s,rest,log_fields\n'
    'Speed,1,1,Accel,,Sprint day,sprint,required,,10 m sprints,15,,10,,Walk back,"duration_minutes, rpe"\n'
    ',,,,,,,,,20 m sprints,10,,20,,Walk back,\n'
    ',,2,Rest,rest,,,,,,,,,,,\n'
    ',,3,Top speed,,Sprint day,sprint,required,,Flying 20s,6,,20,,2 min,\n'
    'Conditioning,0,0,Intervals,,Intervals,conditioning,required,,ON,4,,,120,2 min,\n'
    ',,1,Hills,,Hill sprints,conditioning,alternative,hills,Hill,7,,,20,,\n'
    ',,1,,,Deadmill,conditioning,alternative,hills,Push,7,,,25,,\n'
    ',,2,Throwing,,Throws,Throwing,optional,,Clock drill,,,,600,,\n'
)
GOOD_TESTS = ('test,unit,measurement,attempts,aggregation,better,min,max,milestone_track,baseline_week,retest_weeks\n'
              '10 m sprint,s,time,3,best,lower,1,4,Speed,1,3\n')


def test_parse_reports_problems_with_row_numbers():
    bad = GOOD_CSV.replace(',,3,Top speed', ',,4,Top speed').replace('Hill sprints,conditioning,alternative,hills',
                                                                     'Hill sprints,conditioning,alternative,')
    bad += ',,x,,,Oops,sprint,sometimes,,,,,,,,\n' + ',,2,,,,,,,,3,,,,,\n' + ',,2,,,Throws,,,,Bad,,,-5,,,\n'
    parsed = pimport.parse(pimport.rows_from_csv(bad), pimport.rows_from_csv(GOOD_TESTS.replace(',3\n', ',9\n')))
    messages = {msg for _, msg in parsed['errors']}
    rows = {row for row, _ in parsed['errors']}
    assert any('no rows for week(s) 3' in m for m in messages)
    assert any('no alternative_group' in m for m in messages)
    assert any('"x" must be a whole number' in m for m in messages)
    assert any('without an exercise name' in m for m in messages)
    assert any("can't be below 0" in m for m in messages)
    assert any('has no week 9' in m for m in messages)
    assert 10 in rows  # the "x" row
    missing = pimport.parse(pimport.rows_from_csv('track,week\nA,1\n'))
    assert 'missing the column(s): session' in missing['errors'][0][1]


def test_parse_maps_tracks_weeks_sessions_and_tests():
    parsed = pimport.parse(pimport.rows_from_csv(GOOD_CSV), pimport.rows_from_csv(GOOD_TESTS))
    assert parsed['errors'] == []
    speed, cond = parsed['tracks']
    assert [w['number'] for w in speed['weeks']] == [1, 2, 3] and speed['weeks'][1]['kind'] == 'rest'
    assert [w['number'] for w in cond['weeks']] == [0, 1, 2] and cond['first_week'] == 0
    accel = speed['weeks'][0]['sessions'][0]
    assert [e['name'] for e in accel['exercises']] == ['10 m sprints', '20 m sprints']
    assert accel['log_fields'] == ['duration_minutes', 'rpe']
    hills = cond['weeks'][1]['sessions']
    assert [(s['title'], s['alternative_group']) for s in hills] == [('Hill sprints', 'hills'), ('Deadmill', 'hills')]
    throws = cond['weeks'][2]['sessions'][0]
    assert (throws['session_type'], throws['requirement']) == ('throwing', 'optional')
    assert parsed['tests'][0]['higher_is_better'] is False
    assert [(m['kind'], m['week']) for m in parsed['milestones']] == [('baseline', 1), ('retest', 3)]


def test_import_on_site_fix_errors_then_import_once(app, clubs):
    c = client(app, clubs, 'other_coach')
    bad = GOOD_CSV.replace(',,3,Top speed', ',,4,Top speed')
    page = ok(c.post('/programmes/import', data={'file': (io.BytesIO(bad.encode()), 'speed.csv'),
                                                 'tests_file': (io.BytesIO(GOOD_TESTS.encode()), 'tests.csv')},
                     content_type='multipart/form-data'))
    assert 'no rows for week(s) 3' in page and 'Check again' in page and 'Import as a draft' not in page
    # Confirming a sheet with errors creates nothing
    c.post('/programmes/import', data={'programme_csv': bad, 'tests_csv': GOOD_TESTS, 'confirm': '1', 'name': 'X'})
    with app.app_context():
        assert Programme.query.count() == 0
    # Corrected in the page and checked again
    page = ok(c.post('/programmes/import', data={'programme_csv': GOOD_CSV, 'tests_csv': GOOD_TESTS,
                                                 'filename': 'speed.csv', 'recheck': '1'}))
    assert 'No errors' in page and 'Import as a draft' in page and 'Speed' in page
    r = c.post('/programmes/import', data={'programme_csv': GOOD_CSV, 'tests_csv': GOOD_TESTS, 'filename': 'speed.csv',
                                           'confirm': '1', 'name': 'Imported speed', 'schedule_mode': 'calendar',
                                           'start_date': '2026-11-02'})
    assert r.status_code == 302
    with app.app_context():
        programme = Programme.query.one()
        assert programme.team_organization_id == clubs['other'] and programme.import_filename == 'speed.csv'
        assert programme.draft and programme.published is None
        assert [t.name for t in programme.draft.tracks] == ['Speed', 'Conditioning']
        assert programme.draft.milestones[1].week.number == 3
        assert svc.validate(programme, programme.draft)[0] == []
    # The same content again is refused
    page = ok(c.post('/programmes/import', data={'programme_csv': GOOD_CSV, 'tests_csv': GOOD_TESTS,
                                                 'confirm': '1', 'name': 'Again'}))
    assert 'already imported' in page
    with app.app_context():
        assert Programme.query.count() == 1
    # Another club importing the same file gets its own programme
    herd = client(app, clubs, 'herd_coach')
    herd.post('/programmes/import', data={'programme_csv': GOOD_CSV, 'tests_csv': GOOD_TESTS, 'confirm': '1',
                                          'name': 'Imported speed'})
    with app.app_context():
        assert Programme.query.filter_by(team_organization_id=clubs['herd']).count() == 1


def test_xlsx_import(app, clubs):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'programme'
    for row in pimport.rows_from_csv(GOOD_CSV):
        ws.append([int(v) if v.isdigit() else v for v in row])
    tests = wb.create_sheet('tests')
    for row in pimport.rows_from_csv(GOOD_TESTS):
        tests.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    c = client(app, clubs, 'other_coach')
    page = ok(c.post('/programmes/import', data={'file': (io.BytesIO(buf.getvalue()), 'plan.xlsx')},
                     content_type='multipart/form-data'))
    assert 'No errors' in page and '10 m sprint' in page


def test_export_round_trips(app, clubs):
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    programme_csv = ok(c.get(f'/programmes/{pid}/export/programme.csv'))
    tests_csv = ok(c.get(f'/programmes/{pid}/export/tests.csv'))
    parsed = pimport.parse(pimport.rows_from_csv(programme_csv), pimport.rows_from_csv(tests_csv))
    assert parsed['errors'] == []
    with app.app_context():
        original = db.session.get(Programme, pid).published
        assert parsed['counts']['weeks'] == sum(len(t.weeks) for t in original.tracks)
        assert parsed['counts']['exercises'] == ProgrammeExercise.query.filter(
            ProgrammeExercise.session_id.in_([s.id for t in original.tracks for w in t.weeks for s in w.sessions])).count()
        assert [t['first_week'] for t in parsed['tracks']] == [1, 0]
    report = ok(c.get(f'/programmes/{pid}/export/report.csv'))
    assert report.startswith('player,status,sessions_due')


def test_export_cells_cannot_become_formulas(app, clubs):
    from app.routes.programmes import _safe_cell
    assert _safe_cell('=HYPERLINK("x")') == '\'=HYPERLINK("x")'
    assert _safe_cell('-5') == '-5' and _safe_cell('-x') == "'-x" and _safe_cell(None) == ''


# --------------------------------------------------------------------------
# Thundering Herd: the same framework, from a data file
# --------------------------------------------------------------------------

def test_herd_plan_imports_through_the_general_framework(app, clubs):
    from commands import import_programme_command
    runner = app.test_cli_runner()
    result = runner.invoke(import_programme_command, [HERD_PLAN, '--team', 'herd', '--name',
                                                      'Off-Season Training Plan 2025/26', '--start', '2025-10-20'])
    assert result.exit_code == 0, result.output
    programme = Programme.query.filter_by(team_organization_id=clubs['herd']).one()
    draft = programme.draft
    tracks = {t.name: t for t in draft.tracks}
    assert {name: len(t.weeks) for name, t in tracks.items()} == {
        'Sprint & Agility': 10, 'Conditioning': 16, 'Throwing': 16, 'Gym': 16}
    assert [w.number for w in tracks['Conditioning'].weeks][:2] == [0, 1]
    hills = tracks['Conditioning'].weeks[8].sessions
    assert [(s.title, s.requirement) for s in hills] == [('Hill sprints', 'alternative'), ('Deadmill sprints', 'alternative')]
    assert [t.name for t in draft.tests] == ['10 m sprint', '30 m sprint', '5-10-5 pro-agility']
    assert [(m.kind, m.week.number) for m in draft.milestones] == [('baseline', 1), ('retest', 10)]
    assert svc.validate(programme, draft)[0] == []
    # Running it again doesn't make a second copy
    again = runner.invoke(import_programme_command, [HERD_PLAN, '--team', 'herd', '--name', 'Again'])
    assert again.exit_code != 0 and 'Already imported' in again.output
    assert Programme.query.count() == 1


def test_no_club_specific_logic_in_the_framework():
    files = ['app/models/programme.py', 'app/utils/programmes.py', 'app/utils/programme_import.py',
             'app/routes/programmes.py'] + [os.path.join('app/templates/programmes', f)
                                            for f in os.listdir(os.path.join(ROOT, 'app/templates/programmes'))]
    for path in files:
        with open(os.path.join(ROOT, path)) as f:
            text = f.read().lower()
        for word in ('herd', 'thundering'):
            assert word not in text, f'{word!r} in {path}'


# --------------------------------------------------------------------------
# A club's download and delete cover programmes
# --------------------------------------------------------------------------

def test_deleting_a_club_removes_its_programmes_and_leaves_copies(app, clubs):
    from app.utils.team_data import delete_team_data
    c, pid = build_on_site(app, clubs)
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [str(clubs['other_player'])]}), 302)
    p = client(app, clubs, 'other_player')
    with app.app_context():
        sid = db.session.get(Programme, pid).published.tracks[0].weeks[0].sessions[0].id
    ok(p.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed'}), 302)
    ok(c.post(f'/programmes/{pid}/settings', data={'name': 'Shared', 'schedule_mode': 'calendar', 'is_shared': 'on'}), 302)
    herd = client(app, clubs, 'herd_coach')
    ok(herd.post(f'/programmes/shared/{pid}/copy', data={'name': 'Copy'}), 302)
    with app.app_context():
        delete_team_data(clubs['other'])
        db.session.commit()
        assert Programme.query.filter_by(team_organization_id=clubs['other']).count() == 0
        assert SessionLog.query.count() == 0 and ProgrammeEnrolment.query.count() == 0
        copy = Programme.query.one()
        assert copy.name == 'Copy' and copy.draft.tracks[0].weeks[0].sessions[0].title == 'Acceleration session'


def test_every_page_renders_for_a_full_programme(app, clubs):
    """The Herd plan, published with a player on it: every coach and player
    page renders."""
    from commands import import_programme_command
    start = (date.today() - timedelta(weeks=11)).isoformat()
    result = app.test_cli_runner().invoke(import_programme_command, [HERD_PLAN, '--team', 'herd', '--name', 'Plan',
                                                                     '--start', start])
    assert result.exit_code == 0, result.output
    c = client(app, clubs, 'herd_coach')
    with app.app_context():
        pid = Programme.query.one().id
    ok(c.post(f'/programmes/{pid}/publish', data={}), 302)
    ok(c.post(f'/programmes/{pid}/players', data={'action': 'enrol', 'player_ids': [
        str(clubs['herd_player']), str(clubs['herd_player2'])], 'start_offset_weeks': '0'}), 302)
    with app.app_context():
        version = db.session.get(Programme, pid).published
        track = version.tracks[0]
        sid = track.weeks[0].sessions[0].id
        ms = version.milestones[0].id
        test_ids = [t.id for t in version.tests]
        eid = ProgrammeEnrolment.query.filter_by(player_id=clubs['herd_player']).one().id
    p = client(app, clubs, 'herd_player')
    ok(p.post(f'/programmes/{pid}/log/{sid}', data={'status': 'completed', 'rpe': '7', 'duration_minutes': '60'}), 302)
    ok(p.post(f'/programmes/{pid}/results', data={'milestone_id': str(ms), f'attempt_{test_ids[0]}': ['1.9', '1.85', '']}), 302)
    ok(c.post(f'/programmes/{pid}/results?enrolment={eid}', data={'milestone_id': '', f'attempt_{test_ids[0]}': ['1.8']}), 302)
    ok(c.post(f'/programmes/{pid}/draft'), 302)
    with app.app_context():
        draft = db.session.get(Programme, pid).draft
        d_track, d_week = draft.tracks[0], draft.tracks[0].weeks[0]
        d_session = d_week.sessions[0]
        ids = (d_track.id, d_week.id, d_session.id)
    for url in ['/programmes/', '/programmes/new', f'/programmes/{pid}', f'/programmes/{pid}/settings',
                f'/programmes/{pid}/build', f'/programmes/{pid}/tracks/{ids[0]}', f'/programmes/{pid}/weeks/{ids[1]}',
                f'/programmes/{pid}/sessions/{ids[2]}', f'/programmes/{pid}/tests', f'/programmes/{pid}/preview',
                f'/programmes/{pid}/publish', f'/programmes/{pid}/players', f'/programmes/{pid}/dashboard',
                f'/programmes/{pid}/players/{eid}', f'/programmes/{pid}/log/{sid}?enrolment={eid}',
                f'/programmes/{pid}/results?enrolment={eid}', '/programmes/import',
                '/programmes/import/template/programme.csv', '/programmes/import/template/tests.csv']:
        ok(c.get(url))
    dash = ok(c.get(f'/programmes/{pid}/dashboard'))
    assert 'Herd Runner' in dash and '10 m sprint' in dash and 'Load 7d' in dash
    me = ok(p.get(f'/programmes/{pid}/me'))
    assert 'Hill sprints' in me and 'Deadmill sprints' in me and 'this week' in me and 'Record results' in me
    assert '1.85 s' in me and '1.8 s' in me
    ok(p.get(f'/programmes/{pid}/log/{sid}'))
    ok(p.get(f'/programmes/{pid}/results'))
    # A player on exactly one programme goes straight to it; the nav shows it
    r = p.get('/programmes/')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/programmes/{pid}/me')
    assert '/programmes/' in ok(p.get('/team/'))
    # The template download is a valid import
    rows = pimport.rows_from_csv(ok(c.get('/programmes/import/template/programme.csv')))
    tests = pimport.rows_from_csv(ok(c.get('/programmes/import/template/tests.csv')))
    assert pimport.parse(rows, tests)['errors'] == []
