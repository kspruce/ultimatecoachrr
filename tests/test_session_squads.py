"""Saying which squad a session is for, and filtering the sessions list by it."""

from app import db
from app.models.session import SessionPlan
from app.models.season import Squad
from app.routes.session import plan_squad_for
from tests import stats_data
from tests.test_training import TODAY, club, login, make_user  # noqa: F401


def add(c, title, **data):
    r = c.post('/sessions/add', data={'title': title, 'date': TODAY.isoformat(),
                                      'session_type': 'invited_training', 'is_published': 'y', **data})
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    return SessionPlan.query.filter_by(title=title).one()


def listed(c, squad):
    """Titles of the sessions the list shows for a squad filter (the page also
    has an unfiltered "upcoming" panel, so read the route's own list)."""
    from flask import template_rendered
    seen = []

    def record(sender, template, context, **extra):
        if template.name == 'session/index.html':
            seen.append([s.title for s in context['sessions']])
    template_rendered.connect(record)
    try:
        assert c.get(f'/sessions/?squad={squad}').status_code == 200
    finally:
        template_rendered.disconnect(record)
    return seen[-1]


def test_plan_squad_for():
    a, b = Squad(name='1s'), Squad(name=' 2S ')
    assert plan_squad_for([], [a, b]) == 'joint'
    assert plan_squad_for([a, b], [a, b]) == 'joint'
    assert plan_squad_for([a], [a, b]) == '1s'
    assert plan_squad_for([b], [a, b]) == '2s'
    assert plan_squad_for([Squad(name='Masters')], [a, b, Squad(name='Masters')]) is None


def test_ticked_squads_set_the_filter(app, club):
    c = login(app, club, 'coach')
    seconds = add(c, 'Seconds night', squads=[str(club['seconds'].id)])
    everyone = add(c, 'Club night')
    assert seconds.squad == '2s' and [s.name for s in seconds.squads] == ['2s']
    assert everyone.squad == 'joint' and everyone.squads == []

    # Editing moves it to the other squad
    r = c.post(f'/sessions/edit/{seconds.id}', data={
        'title': 'Seconds night', 'date': TODAY.isoformat(), 'session_type': 'invited_training',
        'is_published': 'y', 'squads': [str(club['firsts'].id)]})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(SessionPlan, seconds.id).squad == '1s'

    page = listed(c, '1s')
    assert 'Seconds night' in page and 'Club night' not in page
    page = listed(c, 'joint')
    assert 'Club night' in page and 'Seconds night' not in page
    # All three choices are offered even before a 2s session exists
    assert 'value="2s"' in c.get('/sessions/').get_data(as_text=True)


def test_sessions_saved_before_the_label_still_filter(app, club):
    c = login(app, club, 'coach')
    old_firsts = add(c, 'Old firsts', squads=[str(club['firsts'].id)])
    old_club = add(c, 'Old club night')
    old_firsts.squad = old_club.squad = None  # as saved before this change
    db.session.commit()
    assert 'Old firsts' in listed(c, '1s') and 'Old firsts' not in listed(c, '2s')
    assert 'Old club night' in listed(c, 'joint') and 'Old club night' not in listed(c, '1s')


def test_a_club_without_squads_picks_joint_1s_or_2s(app):
    team = stats_data.build_team(name='Solo', slug='solo')
    coach = make_user(team, 'solo-coach', 'coach')
    db.session.commit()
    c = stats_data.Client(app, coach.id, team.id)

    form = c.get('/sessions/add').get_data(as_text=True)
    assert 'name="plan_squad"' in form and 'Joint (whole club)' in form
    session = add(c, 'Firsts only', plan_squad='1s')
    assert session.squad == '1s' and session.squads == []

    edit = c.get(f'/sessions/edit/{session.id}').get_data(as_text=True)
    assert '<option selected value="1s">' in edit
    assert 'Firsts only' in listed(c, '1s') and 'Firsts only' not in listed(c, 'joint')
