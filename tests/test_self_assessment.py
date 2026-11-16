"""Player check-ins: a self-assessment rubric players tap through, their own
notes, coaches' nudges and the team's editable statements. Coaches always
see check-ins; teammates never do."""
from app import db
from app.models.self_assessment import (
    DEFAULT_ITEMS, CheckInRequest, RubricItem, SelfAssessment,
)
from tests.test_feedback import club, login, text  # noqa: F401


def items(club_ids, section=None):
    q = RubricItem.query.filter_by(team_organization_id=club_ids['team'], active=True)
    if section:
        q = q.filter_by(section=section)
    return q.order_by(RubricItem.position, RubricItem.id).all()


def test_player_fills_in_a_check_in(app, club):
    ann = login(app, club, 'ann_user')
    page = text(ann.get('/check-in/new'))
    # The base statements, in five sections
    for heading in ('Offence', 'Cutting', 'Handling', 'Defence', 'Mental &amp; spirit'):
        assert heading in page
    assert DEFAULT_ITEMS['cutting'][3].replace("'", '&#39;') in page
    assert len(items(club)) == sum(len(v) for v in DEFAULT_ITEMS.values())

    cut = items(club, 'cutting')
    mental = items(club, 'mental')
    # Nothing tapped and no notes: not saved
    ann.post('/check-in/new', data={'notes': '  '})
    assert SelfAssessment.query.count() == 0

    r = ann.post('/check-in/new', data={
        f'score-{cut[0].id}': '2', f'score-{cut[1].id}': '4', f'score-{mental[0].id}': '1',
        f'score-{cut[2].id}': '9',  # not a real answer: ignored
        'focus_item': str(cut[0].id), 'notes': 'Late on my cuts all day', 'about': 'none'})
    assert r.status_code == 302
    a = SelfAssessment.query.one()
    assert a.score_map() == {cut[0].id: 2, cut[1].id: 4, mental[0].id: 1}
    assert a.focus_item_id == cut[0].id and a.player_id == club['ann']
    assert a.section_averages() == {'cutting': 3.0, 'mental': 1.0}

    view = text(ann.get(f'/check-in/{a.id}'))
    assert 'Late on my cuts all day' in view and 'Focus next time' in view
    assert 'Sometimes' in view and 'Always' in view and 'Rarely' in view
    assert 'Late on my cuts all day' not in text(ann.get('/check-in/new'))

    # Edit: clear one answer, change another
    ann.post(f'/check-in/{a.id}/edit', data={f'score-{cut[0].id}': '3', 'notes': 'Better by the end'})
    db.session.expire_all()
    a = db.session.get(SelfAssessment, a.id)
    assert a.score_map() == {cut[0].id: 3} and a.notes == 'Better by the end' and a.focus_item_id is None

    # Listed on My Feedback and their profile
    assert 'My Check-ins' in text(ann.get('/feedback/mine')) and 'Late on my cuts' not in text(ann.get('/feedback/mine'))
    assert 'Better by the end' not in text(ann.get('/check-ins/mine')) and 'Check-in' in text(ann.get('/check-ins/mine'))
    assert 'Check-ins' in text(ann.get(f"/team/player/{club['ann']}"))


def test_coaches_always_see_teammates_never(app, club):
    ann = login(app, club, 'ann_user')
    ann.get('/check-in/new')
    cut = items(club, 'cutting')
    ann.post('/check-in/new', data={f'score-{cut[0].id}': '1', 'notes': 'Private-ish thoughts'})
    a = SelfAssessment.query.one()
    assert a.seen_by_coach_at is None

    coach = login(app, club, 'coach')
    assert 'Private-ish thoughts' in text(coach.get(f'/check-in/{a.id}'))
    db.session.expire_all()
    assert db.session.get(SelfAssessment, a.id).seen_by_coach_at is not None
    assert 'Check-ins' in text(coach.get(f"/team/player/{club['ann']}"))
    # Coaches can't fill one in for the player
    assert coach.post(f'/check-in/{a.id}/edit', data={'notes': 'x'}).status_code == 403

    ben = login(app, club, 'ben_user')
    assert ben.get(f'/check-in/{a.id}').status_code == 404
    assert ben.post(f'/check-in/{a.id}/delete').status_code == 404
    assert ben.get('/check-ins').status_code == 403
    assert login(app, club, 'other_coach', team='other').get(f'/check-in/{a.id}').status_code == 404


def test_nudge_and_team_overview(app, club):
    coach = login(app, club, 'coach')
    assert 'Nudge the team' in text(coach.get('/check-ins'))
    r = coach.post('/check-ins/nudge', data={'title': 'After Nationals', 'message': 'Be honest'})
    assert r.status_code == 302
    req = CheckInRequest.query.one()
    assert req.team_organization_id == club['team'] and req.is_open()

    # Players see it on the home page, in the menu (with a badge) and on
    # My Check-ins; it isn't counted as a new feedback note
    ann = login(app, club, 'ann_user')
    home = text(ann.get('/'))
    assert 'Check-in: After Nationals' in home and 'Be honest' in home
    assert f'/check-in/new?request={req.id}' in home
    assert 'My Check-ins' in home and 'uc-user-dot' in home
    mine = text(ann.get('/check-ins/mine'))
    assert 'Your coaches asked for a check-in: After Nationals' in mine and 'Be honest' in mine
    assert 'your coaches asked for one' in text(ann.get('/feedback/mine'))
    from app.models.user import User
    from app.routes.feedback import unseen_count
    assert unseen_count(db.session.get(User, club['ann_user'])) == 0
    # Coaches (on their home page) don't get the player's card
    assert 'Check-in: After Nationals' not in text(coach.get('/'))
    # Another team's players don't
    assert CheckInRequest.query.filter_by(team_organization_id=club['other']).count() == 0

    form = text(ann.get(f'/check-in/new?request={req.id}'))
    assert 'After Nationals' in form
    d = items(club, 'defence')
    ann.post('/check-in/new', data={'request': req.id, f'score-{d[0].id}': '1', f'score-{d[1].id}': '2'})
    a = SelfAssessment.query.one()
    assert a.request_id == req.id
    assert 'Check-in: After Nationals' not in text(ann.get('/'))
    assert 'Your coaches asked' not in text(ann.get('/check-ins/mine'))
    assert 'uc-user-dot' not in text(ann.get('/check-ins/mine'))
    # Going back to the nudge opens the one they filled in
    assert ann.get(f'/check-in/new?request={req.id}').headers['Location'].endswith(f'/check-in/{a.id}/edit')

    from app.models.player import Player
    ann_name, ben_name = db.session.get(Player, club['ann']).name, db.session.get(Player, club['ben']).name
    page = text(coach.get(f'/check-ins?request={req.id}'))
    assert '1/2 answered' in page
    waiting = page.split('Not answered')[1].split('</div>')[0]
    assert ben_name in waiting and ann_name not in waiting
    assert d[0].text in page  # lowest-rated list
    assert ann_name in text(coach.get('/check-ins'))
    assert '1 new' in text(coach.get('/feedback/'))

    coach.post(f'/check-ins/nudge/{req.id}/close')
    db.session.expire_all()
    assert not db.session.get(CheckInRequest, req.id).is_open()
    assert login(app, club, 'ben_user').get('/feedback/mine').get_data(as_text=True).count('After Nationals') == 0
    assert coach.post('/check-ins/nudge', data={'title': ''}).status_code == 302
    assert CheckInRequest.query.count() == 1


def test_coaches_edit_the_rubric(app, club):
    coach = login(app, club, 'coach')
    assert 'Check-in rubric' in text(coach.get('/check-ins/rubric'))
    all_items = items(club)
    cut = items(club, 'cutting')
    form = {f'text-{i.id}': i.text for i in all_items}
    form.update({f'active-{i.id}': '1' for i in all_items})
    form[f'text-{cut[0].id}'] = 'I cut on the thrower\'s eyes'
    del form[f'active-{cut[1].id}']
    form['new-mental'] = 'I called my own fouls honestly'
    coach.post('/check-ins/rubric', data=form)
    db.session.expire_all()
    cut_now = items(club, 'cutting')
    assert cut_now[0].text == "I cut on the thrower's eyes"
    assert cut[1].id not in {i.id for i in cut_now}
    assert items(club, 'mental')[-1].text == 'I called my own fouls honestly'

    # Players see the team's wording, not hidden ones
    page = text(login(app, club, 'ann_user').get('/check-in/new'))
    assert 'thrower&#39;s eyes' in page and 'I called my own fouls honestly' in page
    assert DEFAULT_ITEMS['cutting'][1] not in page

    # Reorder
    first, second = cut_now[0], cut_now[1]
    form = {f'text-{i.id}': i.text for i in items(club)}
    form.update({f'active-{i.id}': '1' for i in items(club)})
    form['move'] = f'{second.id}:up'
    coach.post('/check-ins/rubric', data=form)
    db.session.expire_all()
    assert [i.id for i in items(club, 'cutting')][:2] == [second.id, first.id]

    # Bring back the base statements
    coach.post('/check-ins/rubric/restore')
    db.session.expire_all()
    texts = {i.text for i in items(club, 'cutting')}
    assert set(DEFAULT_ITEMS['cutting']) <= texts

    # Players can't edit it; another team has its own
    assert login(app, club, 'ann_user').get('/check-ins/rubric').status_code == 403
    login(app, club, 'other_coach', team='other').get('/check-ins/rubric')
    assert RubricItem.query.filter_by(team_organization_id=club['other']).count() == \
        sum(len(v) for v in DEFAULT_ITEMS.values())


def test_home_asks_after_a_tournament(app, club):
    """For a few days after a tournament they went to, the home page asks
    how it went, until they check in."""
    from datetime import date, timedelta
    from app.models.tournament import Tournament
    from app.models.tournament_rsvp import TournamentRSVP
    today = date.today()
    went = Tournament(name='Windmill', team_organization_id=club['team'],
                      start_date=today - timedelta(days=2), end_date=today - timedelta(days=1))
    skipped = Tournament(name='Skipped Cup', team_organization_id=club['team'],
                         start_date=today - timedelta(days=1), end_date=today - timedelta(days=1))
    old = Tournament(name='Long Ago Open', team_organization_id=club['team'],
                     start_date=today - timedelta(days=20), end_date=today - timedelta(days=19))
    db.session.add_all([went, skipped, old])
    db.session.flush()
    db.session.add_all([
        TournamentRSVP(tournament_id=went.id, player_id=club['ann'], status='attending', team_organization_id=club['team']),
        TournamentRSVP(tournament_id=skipped.id, player_id=club['ann'], status='not_attending', team_organization_id=club['team']),
        TournamentRSVP(tournament_id=old.id, player_id=club['ann'], status='attending', team_organization_id=club['team']),
    ])
    db.session.commit()
    went_id = went.id

    ann = login(app, club, 'ann_user')
    home = text(ann.get('/'))
    assert 'How did Windmill go?' in home and 'Skipped Cup' not in home and 'Long Ago Open' not in home
    assert f'about=t:{went_id}' in home
    # The form opens about that tournament
    form = text(ann.get(f'/check-in/new?about=t:{went_id}'))
    assert f'value="t:{went_id}" selected' in form
    # Ben didn't go: nothing for him
    assert 'How did Windmill go?' not in text(login(app, club, 'ben_user').get('/'))

    cut = items(club, 'cutting')
    ann.post('/check-in/new', data={'about': f't:{went_id}', f'score-{cut[0].id}': '3'})
    assert SelfAssessment.query.one().tournament_id == went_id
    assert 'How did Windmill go?' not in text(ann.get('/'))
