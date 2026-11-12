"""The opt-in email telling coaches what's waiting on them
(app/utils/coach_summary.py)."""
from datetime import date, datetime, timedelta

import pytest

from app import db
from app.models.game import Game
from app.models.team_membership import TeamMembership
from app.models.user import User
from app.utils import coach_summary
from tests import stats_data
from tests.test_onboarding import login, make_user

TODAY = date.today()
NOW = datetime.utcnow()


@pytest.fixture
def herd(app):
    app.config.update(MAIL_SERVER='smtp.example.com', MAIL_DEFAULT_SENDER='site@example.com',
                      BASE_URL='https://coach.example.com')
    team = stats_data.build_team('Thundering Herd', 'herd')
    coach = make_user(team, 'carla', role='coach', email='carla@example.com', welcomed=True)
    player = make_user(team, 'pat', role='player', email='pat@example.com', welcomed=True)
    for user_id in (coach, player):
        db.session.get(User, user_id).email_coach_summary = True
    db.session.add(Game(opponent='Chevron', date=TODAY - timedelta(days=1), our_score=0, their_score=0,
                        team_organization_id=team.id))
    db.session.commit()
    return {'team': team.id, 'coach': coach, 'player': player}


def sent(app):
    return app.extensions.get('sent_emails', [])


def test_only_opted_in_coaches_hear_and_only_once(app, herd):
    assert coach_summary.send_due(TODAY, NOW) == 1
    (mail,) = sent(app)
    body = mail.get_content()
    assert mail['To'] == 'carla@example.com' and 'No score yet for vs Chevron' in mail['Subject']
    assert 'https://coach.example.com/games/' in body and 'account page' in body

    # Nothing new the next day or three days on: no more email
    assert coach_summary.send_due(TODAY, NOW + timedelta(days=1)) == 0
    assert coach_summary.send_due(TODAY, NOW + timedelta(days=3)) == 0
    # Still open a week later: one reminder
    assert coach_summary.send_due(TODAY, NOW + timedelta(days=7, minutes=1)) == 1
    assert len(sent(app)) == 2
    # ...and then quiet until something new comes up
    assert coach_summary.send_due(TODAY, NOW + timedelta(days=15)) == 0


def test_something_new_is_sent_and_marked(app, herd):
    coach_summary.send_due(TODAY, NOW)
    db.session.add(Game(opponent='Clapham', date=TODAY - timedelta(days=2), our_score=0, their_score=0,
                        team_organization_id=herd['team']))
    db.session.commit()
    assert coach_summary.send_due(TODAY, NOW + timedelta(hours=2)) == 0  # one a day at most
    assert coach_summary.send_due(TODAY, NOW + timedelta(days=1)) == 1
    assert '2 played games have no score' in sent(app)[-1].get_content()


def test_nothing_outstanding_sends_nothing(app, herd):
    game = Game.query.one()
    game.our_score = 15
    db.session.commit()
    assert coach_summary.send_due(TODAY, NOW) == 0 and not sent(app)


def test_off_by_default_and_set_from_the_account_page(app, herd):
    user = db.session.get(User, herd['coach'])
    user.email_coach_summary = False
    db.session.commit()
    assert coach_summary.send_due(TODAY, NOW) == 0

    coach = login(app, herd['coach'])
    assert 'Coach summary' in coach.get('/auth/account').get_data(as_text=True)
    coach.post('/auth/account', data={'action': 'notifications', 'email_event_updates': '1',
                                      'email_coach_summary': '1'})
    db.session.expire_all()
    assert db.session.get(User, herd['coach']).email_coach_summary
    # Players aren't offered it and can't switch it on
    db.session.get(User, herd['player']).email_coach_summary = False
    db.session.commit()
    player = login(app, herd['player'])
    assert 'Coach summary' not in player.get('/auth/account').get_data(as_text=True)
    player.post('/auth/account', data={'action': 'notifications', 'email_coach_summary': '1'})
    db.session.expire_all()
    assert not db.session.get(User, herd['player']).email_coach_summary
    assert TeamMembership.query.filter_by(user_id=herd['player']).one().summary_sent_at is None
