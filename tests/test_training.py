"""Training: schedules make dates ahead (squads included), players answer
before the plan is written, coaches see everyone at once, plans are built
on one page, the register starts from the answers, and reminders go to the
maybes."""
from datetime import date, time, timedelta

import pytest

from app import db
from app.models.drill import SavedDrill
from app.models.onboarding import UserOnboarding
from app.models.player import Player
from app.models.schedule import ScheduleAvailability, SessionReminder, SessionTemplate, TrainingSchedule
from app.models.season import Season, SeasonRoster, Squad
from app.models.session import Attendance, SessionComponent, SessionPlan, SessionRSVP
from app.models.team_settings import TeamSettings
from app.models.user import User
from app.utils import reminders, rsvp, schedules
from tests import stats_data

TODAY = date.today()


def next_weekday(weekday, after=TODAY):
    return after + timedelta(days=(weekday - after.weekday()) % 7 or 7)


def make_user(team, username, role, player=None):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=(role == 'admin'), team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    if player is not None:
        player.user_id = user.id
    return user


@pytest.fixture
def club(app):
    """A club with 1s and 2s: four players a squad, a coach, an admin, and
    players Ann (1s) and Bea (2s) with logins."""
    team = stats_data.build_team()
    season = Season(team_organization_id=team.id, year=TODAY.year, start_date=date(TODAY.year, 1, 1),
                    end_date=date(TODAY.year + 1, 12, 31), is_current=True)
    firsts, seconds = Squad(team_organization_id=team.id, name='1s'), \
        Squad(team_organization_id=team.id, name='2s', sort_order=1)
    db.session.add_all([season, firsts, seconds])
    db.session.flush()
    players = stats_data.build_players(team, 8)  # new players join the current season's roster
    for i, p in enumerate(players):
        entry = SeasonRoster.query.filter_by(season_id=season.id, player_id=p.id).one()
        entry.squad_id = (firsts if i < 4 else seconds).id
    ann, bea = players[0], players[4]
    admin = make_user(team, 'admin', 'admin')
    coach = make_user(team, 'coach', 'coach')
    ann_user = make_user(team, 'ann', 'player', ann)
    bea_user = make_user(team, 'bea', 'player', bea)
    db.session.commit()
    return {'team': team, 'season': season, 'firsts': firsts, 'seconds': seconds, 'players': players,
            'ann': ann, 'bea': bea, 'ann_user': ann_user, 'bea_user': bea_user, 'admin': admin, 'coach': coach}


def login(app, club, who):
    user = club[who] if isinstance(club[who], User) else club[f'{who}_user']
    return stats_data.Client(app, user.id, club['team'].id)


def add_schedule(club, name, weekday, squads=(), weeks=8, **kw):
    schedule = TrainingSchedule(team_organization_id=club['team'].id, name=name, weekday=weekday,
                                start_time=time(19), end_time=time(21), location='Park',
                                start_date=TODAY, end_date=TODAY + timedelta(weeks=weeks), **kw)
    schedule.squads = list(squads)
    db.session.add(schedule)
    db.session.flush()
    schedules.sync_schedule(schedule)
    db.session.commit()
    return schedule


def dates(schedule):
    return [s.date for s in schedule.sessions.order_by(SessionPlan.date)]


@pytest.fixture
def week(club):
    """Saturdays for everyone, Tuesdays for the 2s, Wednesdays for the 1s."""
    return {
        'sat': add_schedule(club, 'Saturday', 5),
        'tue': add_schedule(club, '2s midweek', 1, [club['seconds']], weeks=4),
        'wed': add_schedule(club, '1s midweek', 2, [club['firsts']], weeks=4),
    }


# ── Schedules ──────────────────────────────────────────────────────────────

def test_a_schedule_makes_its_dates_ahead(club):
    sat = add_schedule(club, 'Saturday', 5, weeks=6)
    made = dates(sat)
    assert made and all(d.weekday() == 5 for d in made)
    assert made[0] == next_weekday(5, TODAY - timedelta(days=1)) and made[-1] <= TODAY + timedelta(weeks=6)
    session = sat.sessions.first()
    assert (session.title, session.start_time, session.location, session.is_published) == \
        ('Saturday', time(19), 'Park', False)
    # Running it again changes nothing
    assert schedules.sync_schedule(sat).summary() == 'no changes'


def test_an_open_ended_schedule_runs_to_the_end_of_the_season(club):
    schedule = TrainingSchedule(team_organization_id=club['team'].id, name='Sat', weekday=5, start_date=TODAY)
    db.session.add(schedule)
    db.session.flush()
    schedules.sync_schedule(schedule)
    assert dates(schedule)[-1] > TODAY + timedelta(weeks=26)


def test_editing_a_schedule_moves_unplanned_dates_and_keeps_answers(club, week):
    wed = week['wed']
    first, second, *rest = wed.sessions.order_by(SessionPlan.date).all()
    db.session.add(SessionComponent(session_id=first.id, title='Planned', order=1, component_type='drill',
                                    team_organization_id=club['team'].id))
    rsvp.set_rsvp(rest[-1], club['ann'], 'yes')
    db.session.commit()

    wed.start_time, wed.location = time(18), 'Hall'
    wed.end_date = TODAY + timedelta(weeks=2)
    report = schedules.sync_schedule(wed)
    db.session.commit()
    assert (second.start_time, second.location) == (time(18), 'Hall')
    # A planned date keeps its own time and place
    assert (first.start_time, first.location) == (time(19), 'Park')
    # Dates off the end go, unless someone answered for them
    assert rest[-1].is_cancelled and rest[-1] in report.cancelled
    assert SessionRSVP.query.filter_by(session_id=rest[-1].id).count() == 1


def test_schedule_page_adds_with_squads_and_weeks_off(app, club):
    c = login(app, club, 'coach')
    skip = next_weekday(1, TODAY + timedelta(days=7))
    r = c.post('/sessions/schedules', data={
        'name': '2s midweek', 'weekday': '1', 'start_time': '19:00', 'end_time': '21:00',
        'start_date': TODAY.isoformat(), 'end_date': (TODAY + timedelta(weeks=12)).isoformat(),
        'squads': [str(club['seconds'].id)], 'skip_dates': skip.isoformat()})
    assert r.status_code == 302
    schedule = TrainingSchedule.query.one()
    assert [s.name for s in schedule.squads] == ['2s']
    session = schedule.sessions.filter_by(date=skip).one()
    assert session.is_cancelled and [s.name for s in session.squads] == ['2s']
    page = c.get('/sessions/schedules').get_data(as_text=True)
    assert '2s midweek' in page and 'Tuesdays' in page
    # Bad input is refused
    r = c.post('/sessions/schedules', data={'name': 'x', 'weekday': '9', 'start_date': TODAY.isoformat()})
    assert r.status_code == 400 and TrainingSchedule.query.count() == 1
    # Players can't manage schedules
    assert login(app, club, 'ann').get('/sessions/schedules').status_code == 302


def test_removing_a_schedule_keeps_answered_and_past_dates(app, club, week):
    sat = week['sat']
    answered = sat.sessions.order_by(SessionPlan.date).first()
    rsvp.set_rsvp(answered, club['ann'], 'maybe')
    db.session.commit()
    total, sat_id = sat.sessions.count(), sat.id
    assert login(app, club, 'coach').post(f'/sessions/schedules/{sat_id}/delete').status_code == 302
    db.session.expire_all()
    assert db.session.get(TrainingSchedule, sat_id) is None
    left = SessionPlan.query.filter_by(title='Saturday').all()
    assert [s.id for s in left] == [answered.id] and left[0].is_cancelled and total > 1


def test_tournament_clashes_are_flagged(club, week):
    from app.models.tournament import Tournament
    sat = week['sat'].sessions.order_by(SessionPlan.date).first()
    db.session.add(Tournament(name='Tour', start_date=sat.date, end_date=sat.date + timedelta(days=1),
                              team_organization_id=club['team'].id))
    db.session.commit()
    assert [(s.id, t.name) for s, t in schedules.clashes(club['team'].id)] == [(sat.id, 'Tour')]


# ── Who a session is for, and answers ─────────────────────────────────────

def test_squads_decide_who_each_session_is_for(club, week):
    sat = week['sat'].sessions.first()
    tue = week['tue'].sessions.first()
    wed = week['wed'].sessions.first()
    names = lambda s: {p.name for p in rsvp.expected_players(s)}  # noqa: E731
    everyone = {p.name for p in club['players']}
    assert names(sat) == everyone
    assert names(tue) == {p.name for p in club['players'][4:]}
    assert names(wed) == {p.name for p in club['players'][:4]}
    # Someone from the other squad who says they're coming counts too
    rsvp.set_rsvp(tue, club['ann'], 'attending')
    assert club['ann'].name in names(tue)


def test_answers_are_saved_one_way(club, week):
    session = week['sat'].sessions.first()
    for raw, saved in (('yes', 'attending'), ('Y', 'attending'), ('?', 'maybe'), ('No', 'not_attending')):
        rsvp.set_rsvp(session, club['ann'], raw)
        assert SessionRSVP.query.filter_by(player_id=club['ann'].id).one().status == saved
    with pytest.raises(ValueError):
        rsvp.set_rsvp(session, club['ann'], 'perhaps')
    other_team = stats_data.build_team('Other', 'other')
    outsider = Player(name='Outsider', team_organization_id=other_team.id)
    db.session.add(outsider)
    with pytest.raises(ValueError):
        rsvp.set_rsvp(session, outsider, 'yes')


def test_usual_answers_fill_in_until_the_player_answers(club, week):
    sat = week['sat']
    first, second = sat.sessions.order_by(SessionPlan.date).limit(2).all()
    rsvp.set_usual(sat, club['ann'], 'yes')
    rsvp.set_rsvp(second, club['ann'], 'no')
    db.session.commit()
    answers = rsvp.answers([first, second])
    assert (answers[(first.id, club['ann'].id)].status, answers[(first.id, club['ann'].id)].usual) == ('attending', True)
    assert (answers[(second.id, club['ann'].id)].status, answers[(second.id, club['ann'].id)].usual) == \
        ('not_attending', False)
    assert rsvp.counts(first)['attending'] == 1


# ── The player's page ──────────────────────────────────────────────────────

def test_players_see_their_squads_dates_and_answer_in_one_tap(app, club, week):
    c = login(app, club, 'ann')  # 1s
    page = c.get('/sessions/availability').get_data(as_text=True)
    assert 'Saturday' in page and '1s midweek' in page and '2s midweek' not in page

    session = week['wed'].sessions.order_by(SessionPlan.date).first()
    r = c.post(f'/sessions/{session.id}/answer', data={'status': 'maybe'}, headers={'Accept': 'application/json'})
    assert r.get_json()['ok'] and r.get_json()['status'] == 'maybe'
    assert SessionRSVP.query.one().status == 'maybe'
    # Without JavaScript the form still works
    r = c.post(f'/sessions/{session.id}/answer', data={'status': 'attending', 'next': '/sessions/availability'})
    assert r.status_code == 302 and r.location.endswith('/sessions/availability')
    assert SessionRSVP.query.one().status == 'attending'
    # ...and never sends you off the site
    r = c.post(f'/sessions/{session.id}/answer', data={'status': 'attending', 'next': '//evil.example'})
    assert 'evil' not in r.location
    # Players answer only for themselves
    other = club['bea']
    assert c.post(f'/sessions/{session.id}/answer/{other.id}', data={'status': 'no'}).status_code == 403


def test_usual_answers_page(app, club, week):
    c = login(app, club, 'bea')
    page = c.get('/sessions/availability').get_data(as_text=True)
    assert 'Your usual answers' in page and '2s midweek' in page and '1s midweek' not in page
    c.post('/sessions/availability/usual', data={f"usual_{week['tue'].id}": 'not_attending',
                                                  f"usual_{week['sat'].id}": 'attending'})
    assert {r.schedule_id: r.status for r in ScheduleAvailability.query} == {
        week['tue'].id: 'not_attending', week['sat'].id: 'attending'}
    c.post('/sessions/availability/usual', data={f"usual_{week['tue'].id}": ''})
    assert {r.schedule_id for r in ScheduleAvailability.query} == {week['sat'].id}


def test_other_squads_sessions_when_welcome(app, club):
    add_schedule(club, '2s extra', 3, [club['seconds']], others_welcome=True)
    page = login(app, club, 'ann').get('/sessions/availability').get_data(as_text=True)
    assert "Other squads' sessions you can come to" in page and '2s extra' in page


def test_cancelled_sessions_cant_be_answered(app, club, week):
    session = week['sat'].sessions.first()
    schedules.cancel(session, 'Pitch closed')
    db.session.commit()
    r = login(app, club, 'ann').post(f'/sessions/{session.id}/answer', data={'status': 'yes'},
                                     headers={'Accept': 'application/json'})
    assert r.status_code == 400 and SessionRSVP.query.count() == 0


def test_session_page_shows_answer_buttons_and_counts(app, club, week):
    session = week['sat'].sessions.first()
    rsvp.set_rsvp(session, club['bea'], 'yes')
    db.session.commit()
    page = login(app, club, 'ann').get(f'/sessions/{session.id}/detail').get_data(as_text=True)
    assert 'Are you coming?' in page and '1 yes' in page


# ── The coach's grid ───────────────────────────────────────────────────────

def test_grid_shows_everyone_and_coaches_can_set_cells(app, club, week):
    c = login(app, club, 'coach')
    rsvp.set_rsvp(week['sat'].sessions.first(), club['ann'], 'maybe')
    db.session.commit()
    page = c.get('/sessions/availability/grid').get_data(as_text=True)
    assert club['ann'].name in page and club['players'][7].name in page and 's-maybe' in page
    squad_page = c.get(f"/sessions/availability/grid?squad={club['seconds'].id}").get_data(as_text=True)
    assert club['ann'].name not in squad_page and '1s midweek' not in squad_page

    session = week['tue'].sessions.first()
    bea = club['bea']
    r = c.post(f'/sessions/{session.id}/answer/{bea.id}', json={'status': 'attending'})
    assert r.get_json()['ok'] and SessionRSVP.query.filter_by(player_id=bea.id).one().status == 'attending'
    r = c.post(f'/sessions/{session.id}/answer/{bea.id}', json={'status': 'none'})
    assert SessionRSVP.query.filter_by(player_id=bea.id).count() == 0
    # Players don't get the grid
    assert login(app, club, 'ann').get('/sessions/availability/grid').status_code == 302


def test_grid_csv_round_trip(app, club, week):
    c = login(app, club, 'coach')
    sat = week['sat'].sessions.order_by(SessionPlan.date).first()
    rsvp.set_rsvp(sat, club['ann'], 'yes')
    rsvp.set_usual(week['sat'], club['bea'], 'maybe')
    db.session.commit()
    csv_text = c.get('/sessions/availability/grid.csv').get_data(as_text=True)
    header, *rows = csv_text.strip().splitlines()
    assert header.startswith('Player,Squad,' + sat.date.isoformat() + ' Saturday')
    assert any(r.startswith(club['ann'].name + ',1s,Yes') for r in rows)
    assert 'Maybe (usual)' in csv_text

    # Importing it back changes nothing (usual answers stay usual)
    c.post('/sessions/availability/import', data={'text': csv_text})
    assert SessionRSVP.query.count() == 1

    # A hand-made sheet
    wed = week['wed'].sessions.order_by(SessionPlan.date).first()
    sheet = (f"Player,{wed.date.strftime('%d/%m/%Y')},Not a date\n"
             f"{club['players'][1].name},Y,x\nNobody,N,\n{club['players'][2].name},perhaps,\n")
    page = c.post('/sessions/availability/import', data={'text': sheet}).get_data(as_text=True)
    assert '1 answers saved' in page and 'Nobody' in page and 'Not a date' in page
    assert SessionRSVP.query.filter_by(player_id=club['players'][1].id, session_id=wed.id).one().status == 'attending'


# ── What players see ───────────────────────────────────────────────────────

def test_coaches_choose_what_players_see(app, club, week):
    session = week['sat'].sessions.first()
    rsvp.set_rsvp(session, club['bea'], 'yes')
    db.session.commit()
    ann = login(app, club, 'ann')
    assert club['bea'].name in ann.get(f'/sessions/{session.id}/rsvps').get_data(as_text=True)

    coach = login(app, club, 'coach')
    coach.post('/sessions/settings', data={'attendee_visibility': 'counts', 'plan_when': 'now',
                                           'reminders_enabled': 'on', 'reminder_days': '5'})
    page = ann.get(f'/sessions/{session.id}/rsvps').get_data(as_text=True)
    assert club['bea'].name not in page and 'pill-attending' in page

    coach.post('/sessions/settings', data={'attendee_visibility': 'hidden', 'plan_when': 'now', 'reminder_days': '5'})
    assert ann.get(f'/sessions/{session.id}/rsvps').status_code == 302
    # Coaches still see names
    assert club['bea'].name in coach.get(f'/sessions/{session.id}/rsvps').get_data(as_text=True)
    settings = TeamSettings.query.filter_by(team_id=club['team'].id).one()
    assert (settings.reminders_enabled, settings.reminder_days) == (False, 5)


def test_plans_are_hidden_until_published(app, club):
    team_id = club['team'].id
    session = SessionPlan(title='Hidden', date=TODAY + timedelta(days=5), team_organization_id=team_id,
                          is_published=False)
    db.session.add(session)
    db.session.flush()
    db.session.add(SessionComponent(session_id=session.id, title='Secret drill', order=1,
                                    component_type='drill', team_organization_id=team_id))
    db.session.commit()
    ann, coach = login(app, club, 'ann'), login(app, club, 'coach')
    assert 'Secret drill' not in ann.get(f'/sessions/{session.id}/detail').get_data(as_text=True)
    assert ann.get(f'/sessions/{session.id}/printable').status_code == 302
    assert 'Secret drill' in coach.get(f'/sessions/{session.id}/detail').get_data(as_text=True)

    session.is_published = True
    settings = TeamSettings.query.filter_by(team_id=team_id).first() or TeamSettings(team_id=team_id)
    settings.plan_visible_days = 2
    db.session.add(settings)
    db.session.commit()
    assert 'Secret drill' not in ann.get(f'/sessions/{session.id}/detail').get_data(as_text=True)
    settings.plan_visible_days = 7
    db.session.commit()
    assert 'Secret drill' in ann.get(f'/sessions/{session.id}/detail').get_data(as_text=True)


# ── The session builder ────────────────────────────────────────────────────

def test_builder_saves_blocks_in_place(app, club, week):
    team_id = club['team'].id
    drill = SavedDrill(title='Huck drill', recommended_duration=15, team_organization_id=team_id)
    other_team = stats_data.build_team('Other', 'other')
    foreign = SavedDrill(title='Their drill', team_organization_id=other_team.id)
    db.session.add_all([drill, foreign])
    db.session.commit()
    session = week['sat'].sessions.first()
    c = login(app, club, 'coach')
    assert 'Who&#39;s coming' in c.get(f'/sessions/{session.id}/plan').get_data(as_text=True) or \
        "Who's coming" in c.get(f'/sessions/{session.id}/plan').get_data(as_text=True)

    r = c.post(f'/sessions/{session.id}/plan', json={'blocks': [
        {'title': 'Warm-up', 'component_type': 'warmup', 'duration_minutes': 15},
        {'title': 'Hucks', 'component_type': 'drill', 'duration_minutes': '20', 'drill_id': drill.id},
        {'title': 'Sneaky', 'component_type': 'nonsense', 'drill_id': foreign.id},
    ], 'focus_area': 'Deep game', 'publish': True})
    body = r.get_json()
    assert body['ok'] and body['published']
    warm, hucks, sneaky = body['blocks']
    assert (hucks['drill_id'], sneaky['drill_id'], sneaky['component_type']) == (drill.id, None, 'drill')

    # Reorder and drop one: kept blocks keep their ids
    r = c.post(f'/sessions/{session.id}/plan', json={'blocks': [
        {**hucks, 'title': 'Hucks!'}, warm]})
    ids = [b['id'] for b in r.get_json()['blocks']]
    assert ids == [hucks['id'], warm['id']]
    assert [c.title for c in session.components.order_by(SessionComponent.order)] == ['Hucks!', 'Warm-up']
    assert c.post(f'/sessions/{session.id}/plan', json={'blocks': [{'title': ''}]}).status_code == 400
    db.session.expire_all()
    assert db.session.get(SessionPlan, session.id).is_published

    # Templates and copying
    r = c.post('/sessions/templates', json={'name': 'Standard', 'blocks': r.get_json()['blocks']})
    assert r.get_json()['ok'] and SessionTemplate.query.one().blocks[0]['title'] == 'Hucks!'
    copy = c.get(f'/sessions/{session.id}/blocks.json').get_json()
    assert [b['title'] for b in copy['blocks']] == ['Hucks!', 'Warm-up'] and copy['blocks'][0]['id'] is None
    # Players can't use it
    assert login(app, club, 'ann').post(f'/sessions/{session.id}/plan', json={'blocks': []}).status_code == 302


def test_builder_offers_last_weeks_plan(app, club, week):
    first, second = week['sat'].sessions.order_by(SessionPlan.date).limit(2).all()
    db.session.add(SessionComponent(session_id=first.id, title='Last week', order=1, component_type='drill',
                                    team_organization_id=club['team'].id))
    first.date = TODAY - timedelta(days=7)
    db.session.commit()
    page = login(app, club, 'coach').get(f'/sessions/{second.id}/plan').get_data(as_text=True)
    assert f'data-copy="{first.id}"' in page


# ── The register ───────────────────────────────────────────────────────────

def test_register_starts_from_the_yes_answers(app, club, week):
    session = week['wed'].sessions.first()
    ann, other = club['ann'], club['players'][1]
    rsvp.set_rsvp(session, ann, 'yes')
    rsvp.set_rsvp(session, other, 'no')
    db.session.commit()
    c = login(app, club, 'coach')
    page = c.get(f'/sessions/{session.id}/attendance').get_data(as_text=True)
    assert 'starts as present' in page
    assert f'name="p{ann.id}" value="present" data-player="{ann.id}" checked' in page
    assert f'name="p{other.id}" value="present" data-player="{other.id}" checked' not in page

    c.post(f'/sessions/{session.id}/attendance', data={f'p{ann.id}': 'late', f'p{other.id}': '',
                                                         f"p{club['bea'].id}": 'present'})
    assert {(a.player_id, a.status) for a in Attendance.query} == {(ann.id, 'late'), (club['bea'].id, 'present')}


# ── Reminders ──────────────────────────────────────────────────────────────

@pytest.fixture
def email(app):
    app.config.update(MAIL_DEFAULT_SENDER='coach@example.com', MAIL_SERVER='smtp.example.com')
    app.extensions['sent_emails'] = []
    return app.extensions['sent_emails']


def test_maybes_and_no_answers_get_one_reminder(app, club, week, email):
    team_id = club['team'].id
    session = week['wed'].sessions.order_by(SessionPlan.date).first()  # within a week
    ann, yes, no = club['ann'], club['players'][1], club['players'][2]
    rsvp.set_rsvp(session, ann, 'maybe')
    rsvp.set_rsvp(session, yes, 'yes')
    rsvp.set_rsvp(session, no, 'no')
    db.session.commit()

    owed = reminders.due(team_id)
    wed_people = {p.name for p, sessions in owed.items() if session in sessions}
    assert ann.name in wed_people and club['players'][3].name in wed_people
    assert yes.name not in wed_people and no.name not in wed_people

    reached, missed = reminders.send_for_team(team_id)
    assert reached == 2 and missed == len(owed) - 2  # only Ann and Bea have logins with email
    assert any('Can you let your coaches know' in m.get_content() for m in email)
    assert SessionReminder.query.filter_by(session_id=session.id, player_id=ann.id).count() == 1
    # Once only
    sent = len(email)
    assert reminders.send_for_team(team_id) == (0, 0) and len(email) == sent

    # Teams can turn it off
    settings = TeamSettings.query.filter_by(team_id=team_id).first() or TeamSettings(team_id=team_id)
    settings.reminders_enabled = False
    db.session.add(settings)
    db.session.commit()
    SessionReminder.query.delete()
    db.session.commit()
    assert reminders.send_all() == 0


def test_coach_can_nudge_one_session(app, club, week, email):
    session = week['wed'].sessions.order_by(SessionPlan.date).first()
    r = login(app, club, 'coach').post(f'/sessions/{session.id}/nudge')
    assert r.status_code == 302
    assert [m['To'] for m in email] == ['ann@example.com']


def test_cancelling_tells_the_players_who_were_coming(app, club, week, email):
    session = week['sat'].sessions.order_by(SessionPlan.date).first()
    rsvp.set_rsvp(session, club['ann'], 'yes')
    rsvp.set_rsvp(session, club['bea'], 'no')
    db.session.commit()
    login(app, club, 'coach').post(f'/sessions/{session.id}/cancel', data={'reason': 'Waterlogged'})
    db.session.expire_all()
    assert db.session.get(SessionPlan, session.id).cancel_reason == 'Waterlogged'
    assert [m['To'] for m in email] == ['ann@example.com']
    login(app, club, 'coach').post(f'/sessions/{session.id}/restore')
    db.session.expire_all()
    assert not db.session.get(SessionPlan, session.id).is_cancelled


# ── The season plan fills in schedule dates ────────────────────────────────

def test_season_plan_fills_in_schedule_dates(app, club, week):
    from app.models.season_plan import SeasonPlan, SeasonWeek
    from app.utils.season_sessions import build_sessions
    from tests.test_season_sessions import WEEK_MD

    team_id = club['team'].id
    monday = next_weekday(0)
    plan = SeasonPlan(team_organization_id=team_id, season='2026/27', title='Plan')
    db.session.add(plan)
    db.session.flush()
    db.session.add(SeasonWeek(plan_id=plan.id, team_organization_id=team_id, week_number=1,
                              week_commencing=monday, session_detail_md=WEEK_MD))
    sat = week['sat'].sessions.filter_by(date=monday + timedelta(days=5)).one()
    wed = week['wed'].sessions.filter_by(date=monday + timedelta(days=2)).one()
    tue = week['tue'].sessions.filter_by(date=monday + timedelta(days=1)).one()
    rsvp.set_rsvp(sat, club['ann'], 'yes')
    db.session.commit()
    before = SessionPlan.query.count()

    build_sessions(plan)
    assert SessionPlan.query.count() == before  # nothing new: the schedule's dates were used
    assert (sat.squad, wed.squad, tue.squad) == ('joint', '1s', '2s')
    assert sat.components.count() == 5 and sat.title.startswith('Week 1 Joint')
    assert (sat.start_time, sat.location) == (time(19), 'Park')  # the schedule's, not the plan's
    assert SessionRSVP.query.filter_by(session_id=sat.id).count() == 1

    # Taking the week out of the plan puts the dates back as they were
    plan.weeks[0].session_detail_md = None
    build_sessions(plan)
    assert sat.components.count() == 0 and sat.title == 'Saturday' and sat.external_id is None
    assert db.session.get(SessionPlan, sat.id) is not None
