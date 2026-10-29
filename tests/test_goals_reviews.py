"""Player development: goals (the player's own or set with coaches), notes
about a goal, and written reviews."""
from app import db
from app.models.feedback import PlayerFeedback, PlayerGoal, PlayerReview
from tests.test_feedback import add_note, club, login, text  # noqa: F401


def test_goals(app, club):
    ann = login(app, club, 'ann_user')
    r = ann.post(f"/players/{club['ann']}/goals", data={'title': '  Reliable   flick huck ', 'horizon': 'mid',
                                                        'detail': 'Ten a session'})
    assert r.status_code == 302
    goal = PlayerGoal.query.one()
    assert (goal.title, goal.horizon, goal.status, goal.created_by) == ('Reliable flick huck', 'mid', 'active', club['ann_user'])
    # Teammates can't see or touch them
    ben = login(app, club, 'ben_user')
    assert 'Reliable flick huck' not in text(ben.get(f"/team/player/{club['ann']}"))
    assert ben.post(f'/goals/{goal.id}/status', data={'status': 'achieved'}).status_code == 403
    assert ben.post(f"/players/{club['ann']}/goals", data={'title': 'x'}).status_code == 403

    # A coach links a note to it; it shows on the goal
    coach = login(app, club, 'coach')
    add_note(coach, club, 'Two good hucks today', shared='1', goal_id=goal.id, kind='keep')
    assert PlayerFeedback.query.one().goal_id == goal.id
    page = text(ann.get(f"/team/player/{club['ann']}"))
    assert 'Notes about it' in page and 'Two good hucks today' in page

    ann.post(f'/goals/{goal.id}/edit', data={'title': 'Flick huck', 'detail': '', 'horizon': 'short'})
    ann.post(f'/goals/{goal.id}/status', data={'status': 'achieved'})
    db.session.expire_all()
    goal = db.session.get(PlayerGoal, goal.id)
    assert goal.title == 'Flick huck' and goal.status == 'achieved' and goal.done_at
    assert 'Achieved and dropped (1)' in text(ann.get(f"/team/player/{club['ann']}"))
    assert login(app, club, 'other_coach', team='other').post(f'/goals/{goal.id}/delete').status_code == 404
    coach.post(f'/goals/{goal.id}/delete')
    assert PlayerGoal.query.count() == 0 and PlayerFeedback.query.one().goal_id is None


def test_reviews(app, club):
    coach = login(app, club, 'coach')
    assert 'What has gone well' in text(coach.get(f"/players/{club['ann']}/reviews/new"))
    r = coach.post(f"/players/{club['ann']}/reviews/new", data={'title': 'Mid-season review',
                                                                'went_well': 'Your hucks', 'work_on': 'The mark'})
    review = PlayerReview.query.one()
    assert r.headers['Location'].endswith(f'/reviews/{review.id}') and not review.shared

    ann = login(app, club, 'ann_user')
    assert ann.get(f'/reviews/{review.id}').status_code == 404  # not shared yet
    assert 'Mid-season review' not in text(ann.get('/feedback/mine'))
    coach.post(f'/reviews/{review.id}/edit', data={'title': 'Mid-season review', 'went_well': 'Your hucks',
                                                   'work_on': 'The mark', 'next_steps': 'Cup drills', 'shared': '1'})
    assert 'Mid-season review' in text(ann.get('/feedback/mine'))
    page = text(ann.get(f'/reviews/{review.id}'))
    assert 'Cup drills' in page and 'Your comment' in page
    ann.post(f'/reviews/{review.id}/comment', data={'player_comment': 'Agreed, the mark is my focus'})
    assert 'Agreed, the mark is my focus' in text(coach.get(f'/reviews/{review.id}'))
    db.session.expire_all()
    assert db.session.get(PlayerReview, review.id).seen_at is not None

    # Nobody else
    assert login(app, club, 'ben_user').get(f'/reviews/{review.id}').status_code == 404
    assert ann.post(f"/players/{club['ann']}/reviews/new", data={'went_well': 'x'}).status_code == 403
    assert login(app, club, 'other_coach', team='other').get(f'/reviews/{review.id}').status_code == 404
    # A review a while ago counts towards the follow-ups
    assert 'No review in' not in text(coach.get('/feedback/focus?show=follow')).split('Herd Player 02')[0]
