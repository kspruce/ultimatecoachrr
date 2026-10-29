"""The player profile: tabs, and what teammates can and can't see."""
from datetime import date

from app import db
from app.models.player import Player
from tests.test_feedback import club, login, text  # noqa: F401


def test_tabs_and_privacy(app, club):
    ann = db.session.get(Player, club['ann'])
    ann.birth_date = date(2000, 5, 17)
    ann.notes = 'Recovering from a hamstring'
    ann.short_term_goals = 'Throw more break-side'
    db.session.commit()

    own = text(login(app, club, 'ann_user').get(f"/team/player/{club['ann']}"))
    for bit in ('data-pp-tab="overview"', 'data-pp-tab="roles-tab"', 'data-pp-tab="development"',
                'Recovering from a hamstring', 'Throw more break-side', '17 May 2000'):
        assert bit in own, bit

    # A teammate sees the profile, but not the private parts
    mate = text(login(app, club, 'ben_user').get(f"/team/player/{club['ann']}"))
    assert ann.name in mate and 'data-pp-tab="games"' in mate
    for bit in ('data-pp-tab="development"', 'Recovering from a hamstring', 'Throw more break-side', '17 May 2000'):
        assert bit not in mate, bit

    coach = text(login(app, club, 'coach').get(f"/team/player/{club['ann']}"))
    assert 'Recovering from a hamstring' in coach and 'Edit Goals' in coach and 'View Feedback' in coach

    # Saving goals comes back to the Development tab
    r = login(app, club, 'ann_user').post(f"/team/player/{club['ann']}/update_goals", data={'short_term_goals': 'x'})
    assert r.headers['Location'].endswith('#development')
