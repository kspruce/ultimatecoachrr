"""Importing a markdown file of theory cards: parsing, drafts in the named
section, re-imports leaving edits alone, the upload page and the command."""
import io
import os

import pytest

from app import db
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from app.utils.theory_import import TheoryImportError, import_cards, parse_cards
from tests import stats_data
from tests.test_teams import make_user

HERD_CARDS = os.path.join(os.path.dirname(__file__), '..', 'imports', 'theory-cards', 'herd-theory-cards-1-40.md')

SAMPLE = """# Herd Theory Cards

Oct 29, 2026 · @Kieran

## How to use these cards

Each card is one idea a player can read in three minutes.

| Card | Release week |
| --- | --- |
| 1 Catching | 3 |

## Card 1 · Catching: feet first

**Release:** week 3

**Why it matters.** Drops are free turnovers.

```
## not a heading inside a code block
```

## Card 2 · Throw to space

**Why it matters.** Lead the receiver.
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


def topics(team_id):
    db.session.expire_all()
    return (TheoryTopic.query.filter_by(team_organization_id=team_id)
            .order_by(TheoryTopic.order).all())


def test_parse_cards():
    parsed = parse_cards(SAMPLE)
    assert parsed['section'] == 'Herd Theory Cards'
    assert parsed['description'] == 'Each card is one idea a player can read in three minutes.'
    assert [(t['number'], t['name']) for t in parsed['topics']] == [
        (None, 'How to use these cards'), (1, 'Catching: feet first'), (2, 'Throw to space')]
    first = parsed['topics'][1]['content']
    assert first.startswith('**Release:** week 3') and '## not a heading' in first
    assert 'Oct 29' not in ''.join(t['content'] for t in parsed['topics'])


@pytest.mark.parametrize('text, problem', [
    ('# Cards\n\nJust words.', 'No cards found'),
    ('## Card 1 · A\n\nx', 'needs a "# Title"'),
    ('# Cards\n## Card 1 · A\nx\n## Card 1 · B\nx', 'Card numbers used twice: 1'),
    ('# Cards\n## Card 1 · A\nx\n## Card 2 · a\nx', 'Two cards are called "a"'),
    ('# Cards\n## Card 1 · A\n\n## Card 2 · B\nx', 'Card 1 has nothing under its heading'),
    ('# Cards\n## Card 1 · ' + 'x' * 101 + '\nbody', 'the most is 100'),
    ('# Cards\n## Card 1 · A\nx\n## Appendix\nx', 'comes after the cards'),
])
def test_parse_errors(text, problem):
    with pytest.raises(TheoryImportError) as e:
        parse_cards(text)
    assert any(problem in m for m in e.value.errors), e.value.errors


def test_import_makes_drafts_and_reimport_keeps_edits(app, teams):
    report = import_cards(SAMPLE, teams['team'], teams['coach'])
    db.session.commit()
    assert report.section_created and len(report.created) == 3
    rows = topics(teams['team'])
    assert [t.name for t in rows] == ['How to use these cards', 'Catching: feet first', 'Throw to space']
    assert not any(t.published for t in rows) and rows[0].created_by == teams['coach']
    section = TheorySection.query.filter_by(team_organization_id=teams['team']).one()
    assert section.slug == 'herd-theory-cards' and section.description.startswith('Each card')
    assert topics(teams['other']) == []

    rows[1].content = 'Edited on the site'
    rows[1].published = True
    db.session.commit()
    more = SAMPLE + '\n## Card 3 · Resets\n\nDump by five.\n'
    report = import_cards(more, teams['team'])
    db.session.commit()
    assert report.created == ['Resets'] and len(report.kept) == 3 and not report.section_created
    rows = topics(teams['team'])
    assert rows[1].content == 'Edited on the site' and rows[-1].name == 'Resets' and rows[-1].order == 4

    report = import_cards(more, teams['team'], replace=True)
    db.session.commit()
    assert len(report.updated) == 4
    rows = topics(teams['team'])
    assert rows[1].content.startswith('**Release:**') and rows[1].published  # still published
    assert TheorySection.query.filter_by(team_organization_id=teams['team']).count() == 1


def test_dry_run_writes_nothing(app, teams):
    report = import_cards(SAMPLE, teams['team'], dry_run=True)
    db.session.commit()
    assert len(report.created) == 3 and topics(teams['team']) == []
    assert TheorySection.query.count() == 0


def test_herd_cards_file_imports_all_forty(app, teams):
    with open(HERD_CARDS, encoding='utf-8') as f:
        parsed = parse_cards(f.read())
    cards = [t for t in parsed['topics'] if t['number'] is not None]
    assert [t['number'] for t in cards] == list(range(1, 41))
    assert cards[0]['name'] == 'The Herd Way: five habits, three jobs, one language'
    assert all('**Why it matters.**' in t['content'] and '**Source:**' in t['content'] for t in cards)


def test_upload_page(app, teams):
    coach = stats_data.Client(app, teams['coach'], teams['team'])
    assert 'Import cards' in coach.get('/theory/').get_data(as_text=True)
    r = coach.post('/theory/import', data={'file': (io.BytesIO(SAMPLE.encode()), 'cards.md')},
                   content_type='multipart/form-data')
    assert r.status_code == 302 and r.headers['Location'].endswith('/theory/section/herd-theory-cards')
    assert len(topics(teams['team'])) == 3
    page = coach.get('/theory/section/herd-theory-cards').get_data(as_text=True)
    assert 'Throw to space' in page and '3 new cards added as drafts' in page

    r = coach.post('/theory/import', data={'file': (io.BytesIO(b'# Nothing\n'), 'cards.md')},
                   content_type='multipart/form-data')
    assert r.status_code == 400 and 'No cards found' in r.get_data(as_text=True)

    player = stats_data.Client(app, teams['player'], teams['team'])
    assert player.get('/theory/import').status_code == 403
    assert 'Throw to space' not in player.get('/theory/section/herd-theory-cards').get_data(as_text=True)


def test_command(app, teams):
    runner = app.test_cli_runner()
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert 'new cards (drafts): 41' in result.output and topics(teams['team']) == []
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028'])
    assert result.exit_code == 0, result.output
    assert len(topics(teams['team'])) == 41 and topics(teams['other']) == []
    result = runner.invoke(args=['import-theory', HERD_CARDS, '--team', 'herd-2028'])
    assert 'new cards (drafts): 0' in result.output and 'left as edited: 41' in result.output
