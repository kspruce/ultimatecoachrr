"""Importing a markdown file of theory cards: parsing, drafts in the named
sections, re-imports moving cards but leaving edits alone, the upload page,
the command, and the page for moving topics between sections."""
import io
import os

import pytest

from app import db
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from app.utils.theory_import import TheoryImportError, import_cards, parse_cards
from tests import stats_data
from tests.test_teams import make_user

HERD_CARDS = os.path.join(os.path.dirname(__file__), '..', 'imports', 'theory-cards', 'herd-theory-cards.md')

SAMPLE = """# Start here

Oct 29, 2026 · @Kieran

Read these first.

## How to use these cards

Each card is one idea a player can read in three minutes.

## Card 1 · The Herd Way

**Release:** week 1

# Throw and catch

## Card 2 · Catching: feet first

**Release:** week 3

```
# not a section inside a code block
## not a card either
```

## Card 3 · Throw to space

**Why it matters.** Lead the receiver.
"""

# What the first upload looked like: every card in one section
ONE_SECTION = """# Herd Theory Cards

## How to use these cards

Each card is one idea.

## Card 1 · The Herd Way

Habits.

## Card 2 · Catching: feet first

Feet.

## Card 3 · Throw to space

Space.
"""


@pytest.fixture
def teams(app):
    team = stats_data.build_team('Herd 2028', 'herd-2028')
    other = stats_data.build_team('Other', 'other')
    db.session.add_all([TeamSettings(team_id=team.id), TeamSettings(team_id=other.id)])
    db.session.commit()
    return {'team': team.id, 'other': other.id,
            'coach': make_user(team, 'coach', role='coach').id,
            'player': make_user(team, 'player', role='player').id}


def layout(team_id):
    """{section name: [topic names in order]}"""
    db.session.expire_all()
    sections = TheorySection.query.filter_by(team_organization_id=team_id).order_by(TheorySection.order).all()
    return {s.name: [t.name for t in s.topics.order_by(TheoryTopic.order)] for s in sections}


def topic(team_id, name):
    db.session.expire_all()
    return TheoryTopic.query.filter_by(team_organization_id=team_id, name=name).one()


def test_parse_cards():
    sections = parse_cards(SAMPLE)['sections']
    assert [s['name'] for s in sections] == ['Start here', 'Throw and catch']
    assert sections[0]['description'] == 'Read these first.'  # the byline is skipped
    assert sections[1]['description'] == ''
    assert [(t['number'], t['name']) for t in sections[0]['topics']] == [
        (None, 'How to use these cards'), (1, 'The Herd Way')]
    catching = sections[1]['topics'][0]['content']
    assert catching.startswith('**Release:** week 3') and '# not a section' in catching


@pytest.mark.parametrize('text, problem', [
    ('# Cards\n\nJust words.', 'No cards found'),
    ('## Card 1 · A\n\nx', 'Start the file with a "# Section name"'),
    ('# Cards\n## Card 1 · A\nx\n## Card 1 · B\nx', 'Card numbers used twice: 1'),
    ('# Cards\n## Card 1 · A\nx\n# More\n## Card 2 · a\nx', 'Two cards are called "a"'),
    ('# Cards\n## Card 1 · A\n\n## Card 2 · B\nx', 'Card 1 has nothing under its heading'),
    ('# Cards\n## Card 1 · ' + 'x' * 101 + '\nbody', 'the most is 100'),
    ('# Cards\n## Card 1 · A\nx\n## Appendix\nx', 'comes after cards in Cards'),
    ('# Cards\n## Card 1 · A\nx\n# Other\n## Card 2 · B\nx\n# cards\n## Card 3 · C\nx', 'appears twice'),
])
def test_parse_errors(text, problem):
    with pytest.raises(TheoryImportError) as e:
        parse_cards(text)
    assert any(problem in m for m in e.value.errors), e.value.errors


def test_import_makes_drafts_in_each_section(app, teams):
    report = import_cards(SAMPLE, teams['team'], teams['coach'])
    db.session.commit()
    assert report.sections_created == ['Start here', 'Throw and catch'] and len(report.created) == 4
    assert layout(teams['team']) == {'Start here': ['How to use these cards', 'The Herd Way'],
                                     'Throw and catch': ['Catching: feet first', 'Throw to space']}
    assert not topic(teams['team'], 'The Herd Way').published
    assert topic(teams['team'], 'The Herd Way').created_by == teams['coach']
    assert layout(teams['other']) == {}


def test_reupload_with_sections_moves_cards_and_keeps_edits(app, teams):
    import_cards(ONE_SECTION, teams['team'])
    db.session.commit()
    catching = topic(teams['team'], 'Catching: feet first')
    catching.content, catching.published = 'Edited on the site', True
    db.session.commit()

    report = import_cards(SAMPLE, teams['team'])
    db.session.commit()
    assert sorted(report.moved) == ['Catching: feet first', 'How to use these cards', 'The Herd Way',
                                    'Throw to space']
    assert report.created == [] and report.sections_removed == ['Herd Theory Cards']
    assert layout(teams['team']) == {'Start here': ['How to use these cards', 'The Herd Way'],
                                     'Throw and catch': ['Catching: feet first', 'Throw to space']}
    catching = topic(teams['team'], 'Catching: feet first')
    assert catching.content == 'Edited on the site' and catching.published

    report = import_cards(SAMPLE, teams['team'], replace=True)
    db.session.commit()
    assert len(report.updated) == 4 and report.moved == []
    assert topic(teams['team'], 'Catching: feet first').content.startswith('**Release:**')


def test_a_section_with_other_topics_is_kept(app, teams):
    import_cards(ONE_SECTION, teams['team'])
    db.session.commit()
    section = TheorySection.query.filter_by(name='Herd Theory Cards').one()
    db.session.add(TheoryTopic(section_id=section.id, name='My own topic', content='x', order=9,
                               team_organization_id=teams['team']))
    db.session.commit()
    report = import_cards(SAMPLE, teams['team'])
    db.session.commit()
    assert report.sections_removed == [] and layout(teams['team'])['Herd Theory Cards'] == ['My own topic']


def test_dry_run_writes_nothing(app, teams):
    import_cards(ONE_SECTION, teams['team'])
    db.session.commit()
    before = layout(teams['team'])
    report = import_cards(SAMPLE, teams['team'], dry_run=True)
    db.session.commit()
    assert len(report.moved) == 4 and report.sections_removed == ['Herd Theory Cards']
    assert layout(teams['team']) == before


def test_herd_cards_file(app, teams):
    with open(HERD_CARDS, encoding='utf-8') as f:
        sections = parse_cards(f.read())['sections']
    numbers = {s['name']: [t['number'] for t in s['topics'] if t['number']] for s in sections}
    assert numbers == {'Start here': [1, 2, 3], 'Throw and catch': list(range(4, 10)),
                       'Get open': list(range(10, 15)), 'Handle and reset': list(range(15, 20)),
                       'Defend': list(range(20, 27)), 'Herd systems': list(range(27, 35)),
                       'Compete': list(range(35, 41))}
    cards = [t for s in sections for t in s['topics'] if t['number']]
    assert cards[0]['name'] == 'The Herd Way: five habits, three jobs, one language'
    assert all('**Why it matters.**' in t['content'] and '**Source:**' in t['content'] for t in cards)


def test_upload_page(app, teams):
    coach = stats_data.Client(app, teams['coach'], teams['team'])
    assert 'Import cards' in coach.get('/theory/').get_data(as_text=True)
    r = coach.post('/theory/import', data={'file': (io.BytesIO(ONE_SECTION.encode()), 'cards.md')},
                   content_type='multipart/form-data')
    assert r.status_code == 302 and r.headers['Location'].endswith('/theory/section/herd-theory-cards')
    page = coach.get('/theory/section/herd-theory-cards').get_data(as_text=True)
    assert 'Throw to space' in page and '4 new cards added as drafts' in page

    r = coach.post('/theory/import', data={'file': (io.BytesIO(SAMPLE.encode()), 'cards.md')},
                   content_type='multipart/form-data')
    assert r.status_code == 302 and r.headers['Location'].endswith('/theory/')
    page = coach.get('/theory/').get_data(as_text=True)
    assert '4 cards moved to their sections' in page and 'Throw and catch' in page

    r = coach.post('/theory/import', data={'file': (io.BytesIO(b'# Nothing\n'), 'cards.md')},
                   content_type='multipart/form-data')
    assert r.status_code == 400 and 'No cards found' in r.get_data(as_text=True)

    player = stats_data.Client(app, teams['player'], teams['team'])
    assert player.get('/theory/import').status_code == 403
    assert 'Throw to space' not in player.get('/theory/section/throw-and-catch').get_data(as_text=True)


def test_organise_page_moves_topics_and_adds_sections(app, teams):
    import_cards(ONE_SECTION, teams['team'])
    db.session.commit()
    coach = stats_data.Client(app, teams['coach'], teams['team'])
    assert 'Move to another section' in coach.get('/theory/section/herd-theory-cards').get_data(as_text=True)

    r = coach.post('/theory/organise', data={'action': 'add_section', 'name': '  Throw   and catch '})
    assert r.status_code == 302
    new = TheorySection.query.filter_by(team_organization_id=teams['team'], name='Throw and catch').one()
    old = TheorySection.query.filter_by(team_organization_id=teams['team'], name='Herd Theory Cards').one()
    r = coach.post('/theory/organise', data={'action': 'add_section', 'name': 'throw and catch'})
    assert 'already a section' in coach.get('/theory/organise').get_data(as_text=True)

    page = coach.get('/theory/organise').get_data(as_text=True)
    assert 'Throw to space' in page and 'Draft' in page
    ids = {name: topic(teams['team'], name).id for name in ('Catching: feet first', 'Throw to space', 'The Herd Way')}
    form = {f'section_{i}': old.id for i in ids.values()}
    form[f'section_{ids["Throw to space"]}'] = new.id
    form[f'section_{ids["Catching: feet first"]}'] = new.id
    r = coach.post('/theory/organise', data=form)
    assert r.status_code == 302
    assert layout(teams['team']) == {'Herd Theory Cards': ['How to use these cards', 'The Herd Way'],
                                     'Throw and catch': ['Catching: feet first', 'Throw to space']}

    # Another team's section id is ignored, and players can't use it
    other = TheorySection(name='Theirs', slug='theirs', team_organization_id=teams['other'])
    db.session.add(other)
    db.session.commit()
    coach.post('/theory/organise', data={f'section_{ids["The Herd Way"]}': other.id})
    assert topic(teams['team'], 'The Herd Way').section_id == old.id
    player = stats_data.Client(app, teams['player'], teams['team'])
    assert player.get('/theory/organise').status_code == 403
    assert player.post('/theory/organise', data={'action': 'add_section', 'name': 'X'}).status_code == 403


def test_command(app, teams):
    runner = app.test_cli_runner()
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert 'new cards (drafts): 41' in result.output and layout(teams['team']) == {}
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028'])
    assert result.exit_code == 0, result.output
    sections = layout(teams['team'])
    assert len(sections) == 7 and sum(map(len, sections.values())) == 41 and layout(teams['other']) == {}
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028'])
    assert 'new cards (drafts): 0' in result.output and 'left as edited: 41' in result.output


def test_herd_first_upload_then_sectioned_file(app, teams):
    """Herd 2028 uploaded the cards as one section; the sectioned file
    spreads them over seven and removes the old one."""
    import re
    with open(HERD_CARDS, encoding='utf-8') as f:
        sectioned = f.read()
    first = '# Herd Theory Cards\n\nOct 29, 2026 · @Kieran\n\n' + re.sub(r'^# .*\n\n', '', sectioned, flags=re.M)
    import_cards(first, teams['team'])
    db.session.commit()
    assert list(layout(teams['team'])) == ['Herd Theory Cards']
    report = import_cards(sectioned, teams['team'])
    db.session.commit()
    sections = layout(teams['team'])
    assert list(sections) == ['Start here', 'Throw and catch', 'Get open', 'Handle and reset', 'Defend',
                              'Herd systems', 'Compete']
    assert len(report.moved) == 41 and report.created == [] and report.sections_removed == ['Herd Theory Cards']
    assert sections['Start here'][0] == 'How to use these cards'
    assert sections['Compete'][-1] == 'Scouting and game plans'
