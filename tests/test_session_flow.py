"""Repeating a session, run mode and the after-session wrap-up
(app/routes/training.py)."""
from datetime import date, time, timedelta

import pytest

from app import db
from app.models.feedback import PlayerFeedback
from app.models.onboarding import UserOnboarding
from app.models.session import Attendance, SessionComponent, SessionPlan, SessionRSVP
from app.models.user import User
from tests import stats_data

TODAY = date.today()


def _user(team, username, role, player=None):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=role == 'admin', team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    if player is not None:
        player.user_id = user.id
    db.session.commit()
    return user


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    players = stats_data.build_players(team, 3)
    coach = _user(team, 'coach', 'coach')
    player_user = _user(team, 'sam', 'player', players[0])
    session = SessionPlan(title='Zone offence', date=TODAY - timedelta(days=1), start_time=time(19, 30),
                          location='Sportpark', focus_area='Zone', team_organization_id=team.id)
    db.session.add(session)
    db.session.flush()
    db.session.add_all([
        SessionComponent(session_id=session.id, title='Warm-up', order=1, component_type='warm_up',
                         duration_minutes=10, team_organization_id=team.id),
        SessionComponent(session_id=session.id, title='Cup drill', order=2, component_type='drill',
                         duration_minutes=20, coach_cue='Watch the wings', team_organization_id=team.id),
        SessionRSVP(session_id=session.id, player_id=players[0].id, status='attending',
                    team_organization_id=team.id),
    ])
    db.session.commit()
    return {'team': team.id, 'session': session.id, 'players': [p.id for p in players],
            'coach': stats_data.Client(app, coach.id, team.id),
            'player': stats_data.Client(app, player_user.id, team.id)}


def test_repeat_copies_the_session_a_week_on(club):
    r = club['coach'].post(f'/sessions/{club["session"]}/repeat')
    assert r.status_code == 302
    copy = SessionPlan.query.filter(SessionPlan.id != club['session']).one()
    assert f'/sessions/{copy.id}/plan' in r.headers['Location']
    assert copy.title == 'Zone offence' and copy.date == TODAY + timedelta(days=6)
    assert copy.location == 'Sportpark' and copy.start_time == time(19, 30)
    assert not copy.is_published
    blocks = copy.components.order_by(SessionComponent.order).all()
    assert [(b.title, b.duration_minutes) for b in blocks] == [('Warm-up', 10), ('Cup drill', 20)]
    assert blocks[1].coach_cue == 'Watch the wings'
    # Answers and the register stay with the original
    assert copy.rsvps.count() == 0 and copy.attendances.count() == 0


def test_run_mode_shows_the_blocks(club):
    r = club['coach'].get(f'/sessions/{club["session"]}/run')
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert 'Cup drill' in page and 'Watch the wings' in page and 'session_run.js' in page


def test_wrap_up_saves_register_notes_and_review(club):
    first, second, third = club['players']
    page = club['coach'].get(f'/sessions/{club["session"]}/wrap-up').get_data(as_text=True)
    assert 'Who came?' in page and 'How did it go?' in page
    r = club['coach'].post(f'/sessions/{club["session"]}/wrap-up', data={
        f'p{first}': 'present', f'p{second}': 'absent', f'p{third}': '',
        f'note{first}': 'Great reset throws', f'share{first}': '1', f'note{second}': '  ',
        'review_notes': 'Cup was too flat. Repeat next week.'})
    assert r.status_code == 302
    assert {a.player_id: a.status for a in Attendance.query.all()} == {first: 'present', second: 'absent'}
    note = PlayerFeedback.query.one()
    assert (note.player_id, note.content, note.shared, note.session_id) == \
        (first, 'Great reset throws', True, club['session'])
    assert db.session.get(SessionPlan, club['session']).review_notes == 'Cup was too flat. Repeat next week.'
    # The coaches see how it went; players don't
    assert 'Cup was too flat' in club['coach'].get(f'/sessions/{club["session"]}/detail').get_data(as_text=True)
    assert 'Cup was too flat' not in club['player'].get(f'/sessions/{club["session"]}/detail').get_data(as_text=True)


def test_players_cannot_repeat_run_or_wrap_up(club):
    for path in ('run', 'wrap-up'):
        assert club['player'].get(f'/sessions/{club["session"]}/{path}').status_code == 302
    assert club['player'].post(f'/sessions/{club["session"]}/repeat').status_code == 302
    assert SessionPlan.query.count() == 1


def test_another_teams_session_is_not_found(club, app):
    other = stats_data.build_team(name='Others', slug='others')
    theirs = SessionPlan(title='Theirs', date=TODAY, team_organization_id=other.id)
    db.session.add(theirs)
    db.session.commit()
    for path in ('run', 'wrap-up'):
        assert club['coach'].get(f'/sessions/{theirs.id}/{path}').status_code == 404
    assert club['coach'].post(f'/sessions/{theirs.id}/repeat').status_code == 404
