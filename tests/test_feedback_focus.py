"""Coach feedback: keep doing / work on, player replies, and what a player
should keep in mind at the next training or tournament."""
from datetime import date, timedelta

from app import db
from app.models.feedback import FeedbackReply, PlayerFeedback, PlayerFocus
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from tests.test_feedback import add_note, club, login, text  # noqa: F401


def welcomed(user_id):
    from app.models.onboarding import UserOnboarding
    db.session.add(UserOnboarding(user_id=user_id, welcomed_role='player', completed_steps=[]))
    db.session.commit()


def test_keep_doing_and_work_on(app, club):
    coach = login(app, club, 'coach')
    add_note(coach, club, 'Great hucks', shared='1', kind='keep')
    add_note(coach, club, 'Mark the break side', shared='1', kind='work_on')
    add_note(coach, club, 'Odd one', kind='nonsense')
    assert [n.kind for n in PlayerFeedback.query.order_by(PlayerFeedback.id)] == ['keep', 'work_on', 'note']
    mine = text(login(app, club, 'ann_user').get('/feedback/mine'))
    assert 'Keep doing' in mine and 'Work on' in mine


def test_player_replies_and_coaches_see_them(app, club):
    coach = login(app, club, 'coach')
    add_note(coach, club, 'Great hucks', shared='1')
    add_note(coach, club, 'Coaches only')
    shared, private = PlayerFeedback.query.order_by(PlayerFeedback.id).all()
    ann = login(app, club, 'ann_user')
    r = ann.post(f'/feedback/{shared.id}/reply', data={'content': 'Thanks! Working on the flick too'})
    assert r.status_code == 302 and r.headers['Location'].endswith(f'#note-{shared.id}')
    assert ann.post(f'/feedback/{private.id}/reply', data={'content': 'x'}).status_code == 403
    assert login(app, club, 'ben_user').post(f'/feedback/{shared.id}/reply', data={'content': 'x'}).status_code == 403
    assert FeedbackReply.query.one().from_player

    hub = text(coach.get('/feedback/'))
    assert '1 new reply from players' in hub
    page = text(coach.get(f"/players/{club['ann']}/feedback"))
    assert 'Working on the flick too' in page
    assert FeedbackReply.query.one().seen_at is not None  # read now
    coach.post(f'/feedback/{shared.id}/reply', data={'content': 'Yes, keep at it'})
    assert 'Yes, keep at it' in text(ann.get('/feedback/mine'))


def test_keep_in_mind(app, club):
    nationals = Tournament(name='Nationals', start_date=date.today() + timedelta(days=9), team_organization_id=club['team'])
    db.session.add(nationals)
    db.session.commit()
    coach = login(app, club, 'coach')
    assert 'Nationals' in text(coach.get(f"/players/{club['ann']}/feedback"))
    coach.post(f"/players/{club['ann']}/focus", data={'content': 'Call for the swing early.\nStay low on the mark.',
                                                      'event': f't{nationals.id}'})
    focus = PlayerFocus.query.one()
    assert focus.tournament_id == nationals.id and focus.active and focus.for_label.startswith('For Nationals')

    ann = login(app, club, 'ann_user')
    for url in ('/', f"/team/player/{club['ann']}", '/feedback/mine', f'/tournaments/{nationals.id}'):
        assert 'Stay low on the mark.' in text(ann.get(url)), url
    db.session.expire_all()
    assert PlayerFocus.query.one().seen_at is not None  # seen on My Feedback
    # Not on someone else's pages
    assert 'Stay low on the mark.' not in text(login(app, club, 'ben_user').get(f'/tournaments/{nationals.id}'))

    # A new one replaces it; the old one is history
    coach.post(f"/players/{club['ann']}/focus", data={'content': 'Breathe.', 'event': ''})
    db.session.expire_all()
    assert [f.active for f in PlayerFocus.query.order_by(PlayerFocus.id)] == [False, True]
    mine = text(ann.get('/feedback/mine'))
    assert 'Breathe.' in mine and 'Earlier' in mine
    coach.post(f"/players/{club['ann']}/focus/clear")
    db.session.expire_all()
    assert PlayerFocus.query.filter_by(active=True).count() == 0
    # Players can't set their own
    assert ann.post(f"/players/{club['ann']}/focus", data={'content': 'x'}).status_code == 403


def test_focus_board_and_follow_ups(app, club):
    past = SessionPlan(title='Last Tuesday', date=date.today() - timedelta(days=3), team_organization_id=club['team'])
    db.session.add(past)
    db.session.flush()
    db.session.add(PlayerFocus(team_organization_id=club['team'], player_id=club['ann'], content='Old focus',
                               session_id=past.id))
    db.session.commit()
    coach = login(app, club, 'coach')
    board = text(coach.get('/feedback/focus'))
    assert 'Old focus' in board and 'time for a new one' in board and 'No &#34;keep in mind&#34; yet' in board
    follow = text(coach.get('/feedback/focus?show=follow'))
    assert 'Herd Player 01' in follow
    assert login(app, club, 'ann_user').get('/feedback/focus').status_code == 403
    assert login(app, club, 'other_coach', team='other').post(f"/players/{club['ann']}/focus",
                                                              data={'content': 'x'}).status_code == 404
