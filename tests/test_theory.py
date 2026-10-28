"""Theory reads like the handbook: sections and topics in order, search,
previous/next through the whole guide, and each topic links the drills
that practise it and the clips that show it."""
import pytest

from app import db
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.models.theory import TheorySection, TheoryTopic
from tests import stats_data
from tests.test_teams import make_user


@pytest.fixture
def guide(app, team):
    coach = make_user(team, 'coach1', role='coach')
    player = make_user(team, 'player1', role='player')
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    offence = TheorySection(name='Offence', slug='offence', order=1, team_organization_id=team.id)
    defence = TheorySection(name='Defence', slug='defence', order=2, team_organization_id=team.id)
    db.session.add_all([offence, defence])
    db.session.flush()
    topics = [
        TheoryTopic(name='Stack basics', section_id=offence.id, order=1, team_organization_id=team.id,
                    content='## Why a stack\n\nSpace for **cutters**.'),
        TheoryTopic(name='Break-side cuts', section_id=offence.id, order=2, team_organization_id=team.id,
                    content='Cut to the break side when the mark is beaten.'),
        TheoryTopic(name='Force flick', section_id=defence.id, order=1, team_organization_id=team.id,
                    content='Mark the backhand. A *zone* comes later.'),
    ]
    drill = SavedDrill(title='Break-mark ladder', team_organization_id=team.id)
    other_drill = SavedDrill(title='Their drill', team_organization_id=other.id)
    clip = Clip(title='Huck off the break', team_organization_id=team.id)
    hidden = Clip(title='Hidden film', is_hidden=True, team_organization_id=team.id)
    other_clip = Clip(title='Their clip', team_organization_id=other.id)
    db.session.add_all(topics + [drill, other_drill, clip, hidden, other_clip])
    db.session.commit()
    return {'team': team.id, 'topics': [t.id for t in topics], 'drill': drill.id, 'other_drill': other_drill.id,
            'clip': clip.id, 'hidden': hidden.id, 'other_clip': other_clip.id,
            'coach': stats_data.Client(app, coach.id, team.id),
            'player': stats_data.Client(app, player.id, team.id)}


def text(r):
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def test_reading_through_the_guide(app, guide):
    stack, cuts, force = guide['topics']
    home = text(guide['player'].get('/theory/'))
    assert home.index('Offence') < home.index('Defence') and 'Start with Stack basics' in home
    assert 'Add a topic' not in home

    page = text(guide['player'].get(f'/theory/topic/{cuts}'))
    assert 'Cut to the break side' in page and 'aria-current="page"' in page
    assert f'/theory/topic/{stack}' in page and f'/theory/topic/{force}' in page  # previous, and next across sections
    last = text(guide['player'].get(f'/theory/topic/{force}'))
    assert '← Previous' in last and 'Next →' not in last
    assert '<strong>cutters</strong>' in text(guide['player'].get(f'/theory/topic/{stack}'))

    section = text(guide['player'].get('/theory/section/defence'))
    assert 'Force flick' in section and 'Stack basics' in section  # in the contents
    assert 'Edit section' not in section


def test_search(app, guide):
    found = text(guide['player'].get('/theory/?q=zone'))
    assert '1 topic matching' in found and 'Force flick' in found
    assert 'Stack basics' in text(guide['player'].get('/theory/?q=cutters'))
    assert '0 topics matching' in text(guide['player'].get('/theory/?q=nothinglikethis'))


def test_topics_link_drills_and_clips(app, guide):
    stack = guide['topics'][0]
    form = text(guide['coach'].get(f'/theory/edit_topic/{stack}'))
    assert 'Break-mark ladder' in form and 'Huck off the break' in form
    assert 'Their drill' not in form and 'Their clip' not in form

    r = guide['coach'].post(f'/theory/edit_topic/{stack}', data={
        'name': 'Stack basics', 'section_id': TheoryTopic.query.get(stack).section_id, 'content': 'Space.',
        'related_drills': [guide['drill'], guide['other_drill']],
        'clips': [guide['clip'], guide['hidden'], guide['other_clip']]})
    assert r.status_code == 302
    topic = db.session.get(TheoryTopic, stack)
    assert [d.id for d in topic.related_drills] == [guide['drill']]
    assert sorted(c.id for c in topic.clips) == sorted([guide['clip'], guide['hidden']])

    player_view = text(guide['player'].get(f'/theory/topic/{stack}'))
    assert 'Practise it' in player_view and 'Break-mark ladder' in player_view
    assert 'Huck off the break' in player_view and 'Hidden film' not in player_view
    assert 'Hidden film' in text(guide['coach'].get(f'/theory/topic/{stack}'))


def test_coaches_add_topics_to_a_section(app, guide):
    defence = TheorySection.query.filter_by(slug='defence').one()
    form = text(guide['coach'].get(f'/theory/add_topic?section={defence.id}'))
    assert f'<option selected value="{defence.id}">' in form or f'value="{defence.id}" selected' in form
    r = guide['coach'].post('/theory/add_topic', data={'name': 'Poaching', 'section_id': defence.id,
                                                      'content': 'Sag into the lane.', 'clips': [guide['clip']]})
    assert r.status_code == 302
    topic = TheoryTopic.query.filter_by(name='Poaching').one()
    assert [c.id for c in topic.clips] == [guide['clip']]
    assert guide['player'].post('/theory/add_topic', data={'name': 'Nope', 'section_id': defence.id,
                                                          'content': 'x'}).status_code == 302
    assert TheoryTopic.query.filter_by(name='Nope').count() == 0
