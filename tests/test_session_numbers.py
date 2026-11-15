"""Sessions are numbered per team in URLs (/sessions/s2/plan), not by the
database id that every team's sessions share. Old id links still work."""
from datetime import date

import pytest

from app import db
from app.models.session import SessionPlan
from tests import stats_data
from tests.test_teams import make_user


@pytest.fixture
def clubs(app):
    alpha = stats_data.build_team('Alpha', 'alpha')
    bravo = stats_data.build_team('Bravo', 'bravo')
    # Alpha makes three sessions before Bravo makes its first
    mine = []
    for i in range(3):
        s = SessionPlan(title=f'Alpha {i + 1}', team_organization_id=alpha.id)
        db.session.add(s)
        db.session.commit()
        mine.append(s.id)
    theirs = SessionPlan(title='Bravo first', team_organization_id=bravo.id)
    db.session.add(theirs)
    db.session.commit()
    return {'alpha': alpha.id, 'bravo': bravo.id, 'alpha_sessions': mine, 'bravo_session': theirs.id,
            'alpha_coach': make_user(alpha, 'alphacoach').id, 'bravo_coach': make_user(bravo, 'bravocoach').id}


def test_each_team_counts_its_own_sessions(clubs):
    numbers = lambda team: [s.number for s in SessionPlan.query.filter_by(team_organization_id=team).order_by(SessionPlan.id)]
    assert numbers(clubs['alpha']) == [1, 2, 3]
    assert numbers(clubs['bravo']) == [1]
    # ...even though the ids carry on across teams
    assert clubs['bravo_session'] == 4


def test_a_batch_made_together_is_numbered_in_date_order(app, clubs):
    db.session.add_all([
        SessionPlan(title='Late', date=date(2026, 12, 20), team_organization_id=clubs['alpha']),
        SessionPlan(title='Early', date=date(2026, 12, 1), team_organization_id=clubs['alpha']),
        SessionPlan(title='Middle', date=date(2026, 12, 10), team_organization_id=clubs['alpha']),
        SessionPlan(title='Bravo two', team_organization_id=clubs['bravo']),
    ])
    db.session.commit()
    got = {s.title: s.number for s in SessionPlan.query.all()}
    assert (got['Early'], got['Middle'], got['Late']) == (4, 5, 6)
    assert got['Bravo two'] == 2


def test_urls_use_the_team_number_and_stay_inside_the_team(app, clubs):
    alpha = stats_data.Client(app, clubs['alpha_coach'], clubs['alpha'])
    bravo = stats_data.Client(app, clubs['bravo_coach'], clubs['bravo'])
    # /s1 is each team's own first session
    assert 'Alpha 1' in alpha.get('/sessions/s1/detail').get_data(as_text=True)
    page = bravo.get('/sessions/s1/detail').get_data(as_text=True)
    assert 'Bravo first' in page and 'Alpha 1' not in page
    assert '/sessions/s1/' in page and f'/sessions/{clubs["bravo_session"]}/' not in page
    # Bravo has no second session, whatever Alpha has
    assert bravo.get('/sessions/s2/detail').status_code == 404
    assert alpha.get('/sessions/s3/detail').status_code == 200
    assert alpha.get('/sessions/s9/detail').status_code == 404


def test_signed_out_visitors_are_sent_to_sign_in(app, clubs):
    with app.app_context():
        r = app.test_client().get('/sessions/s1/detail')
    assert r.status_code == 302 and '/auth/login' in r.headers['Location']


def test_old_id_links_redirect_to_the_numbered_page(app, clubs):
    alpha = stats_data.Client(app, clubs['alpha_coach'], clubs['alpha'])
    second = clubs['alpha_sessions'][1]
    r = alpha.get(f'/sessions/{second}/detail?back=1')
    assert r.status_code == 308 and r.headers['Location'].endswith('/sessions/s2/detail?back=1')
    # POSTs are told to repeat as POSTs; the edit/delete forms have the id last
    assert alpha.post(f'/sessions/{second}/cancel').status_code == 308
    r = alpha.get(f'/sessions/edit/{second}')
    assert r.status_code == 308 and r.headers['Location'].endswith('/sessions/edit/s2')
    assert alpha.get(r.headers['Location']).status_code == 200


def test_old_id_links_never_reach_another_teams_session(app, clubs):
    bravo = stats_data.Client(app, clubs['bravo_coach'], clubs['bravo'])
    assert bravo.get(f'/sessions/{clubs["alpha_sessions"][0]}/detail').status_code == 404
    assert bravo.get(f'/sessions/edit/{clubs["alpha_sessions"][0]}').status_code == 404
