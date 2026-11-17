"""A week's session notes as structure and back (app/utils/session_outline.py).
The gate: every week of a real season comes back exactly as written, and
rewriting every table from its rows gives Build sessions the same result."""
import os

import pytest

from app.utils import session_outline as so
from app.utils.season_plan_import import load_export, parse_export
from app.utils.season_sessions import parse_week_notes

EXPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'imports', 'season-plan-export')


def real_weeks():
    manifest, tabs = load_export(EXPORT)
    return [w for w in parse_export(manifest, tabs)['weeks'] if w.get('session_detail_md')]


WEEKS = real_weeks()

NOTES = """Intro paragraph.

**Learning points:** (1) Clear hard. (2) Make space.

**Joint session (about 2 hours)**

| Time | Activity | How it runs | Source |
| --- | --- | --- | --- |
| 0:00 | Warm-up | Three-part warm-up | HB |
| 0:20 | Gate drill | Cutters run through a gate | DK 9.22 |
| 1:30 | Water |  |  |

Some notes between.

**Split sessions**

| Time | 1s group | 2s group (suggested) | Source |
| --- | --- | --- | --- |
| 0:00 | H cut drill | Same, stall 7 | DK |
| 0:30 | Ho game | Vert game | IF |

Closing words."""


def test_every_real_week_comes_back_exactly():
    assert len(WEEKS) > 40
    for week in WEEKS:
        md = week['session_detail_md']
        outline = so.parse(md)
        assert so.render(outline) == md, f'week {week["week_number"]}'
        assert not outline.unsupported, f'week {week["week_number"]}'


def test_rewriting_every_table_gives_the_same_sessions():
    tables = 0
    for week in WEEKS:
        md = week['session_detail_md']
        outline = so.parse(md)
        for part in outline.parts:
            if isinstance(part, (so.Table, so.LearningPoints)):
                part.raw = None  # force a fresh render
        tables += len(outline.tables)
        out = so.render(outline)
        assert parse_week_notes(out) == parse_week_notes(md), f'week {week["week_number"]}'
        # And it settles: parsing what was written and writing it again changes nothing
        assert so.render(so.parse(out)) == out
    assert tables > 50


def test_structure():
    outline = so.parse(NOTES)
    assert outline.learning_points == ['Clear hard.', 'Make space.']
    joint, split = outline.joint, outline.split
    assert joint.label == '**Joint session (about 2 hours)**' and joint.length == 120
    assert [k for k, _ in joint.columns] == ['time', 'activity', 'how', 'source']
    assert joint.rows[1] == {'time': '0:20', 'activity': 'Gate drill', 'how': 'Cutters run through a gate',
                             'source': 'DK 9.22'}
    assert joint.rows[2]['how'] is None
    assert split.squads == ['1s', '2s']
    assert split.columns[2] == ('2s', '2s group (suggested)')
    assert split.rows[0] == {'time': '0:00', '1s': 'H cut drill', '2s': 'Same, stall 7', 'source': 'DK'}
    assert so.render(outline) == NOTES


def test_changing_one_table_leaves_the_rest_as_written():
    outline = so.parse(NOTES)
    outline.joint.rows[1]['activity'] = 'Clear-cut drill'
    outline.joint.rows.insert(2, {'time': '1:00', 'activity': 'Honeypass | 5v5', 'how': None, 'source': 'IF'})
    out = so.render(outline)
    assert 'Intro paragraph.' in out and 'Some notes between.' in out and out.endswith('Closing words.')
    assert '| 0:00 | H cut drill | Same, stall 7 | DK |' in out  # the split table untouched
    assert 'Honeypass \\| 5v5' in out  # pipes escaped

    week = parse_week_notes(out)
    joint = next(s for s in week['sessions'] if s['squad'] == 'joint')
    assert [a['title'] for a in joint['activities']] == ['Warm-up', 'Clear-cut drill', 'Honeypass | 5v5', 'Water']
    assert [a['duration_minutes'] for a in joint['activities']] == [20, 40, 30, 30]
    assert week['learning_points'] == ['Clear hard.', 'Make space.']
    seconds = next(s for s in week['sessions'] if s['squad'] == '2s')
    assert seconds['activities'][0]['title'] == 'H cut drill'  # "Same" still reads as the 1s activity


def test_learning_points_edit():
    outline = so.parse(NOTES)
    outline.parts[outline.parts.index(next(p for p in outline.parts if isinstance(p, so.LearningPoints)))] \
        .points.append('Cut with purpose.')
    out = so.render(outline)
    assert '**Learning points:** (1) Clear hard. (2) Make space. (3) Cut with purpose.' in out
    assert parse_week_notes(out)['learning_points'] == ['Clear hard.', 'Make space.', 'Cut with purpose.']


def test_retime_from_durations():
    outline = so.parse(NOTES)
    so.retime(outline.joint, [15, 60, 10])
    assert [r['time'] for r in outline.joint.rows] == ['0:00', '0:15', '1:15']
    assert so.clock(135) == '2:15'


@pytest.mark.parametrize('notes', [
    # A second joint table: Build sessions only reads the first
    NOTES + '\n\n| Time | Activity |\n| --- | --- |\n| 0:00 | Extra |',
    # A timed table with a column the editor doesn't know
    '| Time | Activity | Coach |\n| --- | --- | --- |\n| 0:00 | Warm-up | Sam |',
])
def test_tables_the_editor_cant_show_stay_as_text(notes):
    outline = so.parse(notes)
    assert outline.unsupported
    assert so.render(outline) == notes


def test_plain_notes_and_empty():
    assert so.parse('').parts == [] and so.render(so.parse('')) == ''
    outline = so.parse('Just words.\n\n| Drill | Why |\n| --- | --- |\n| A | B |')
    assert outline.tables == [] and not outline.unsupported
    assert so.render(outline) == 'Just words.\n\n| Drill | Why |\n| --- | --- |\n| A | B |'


def test_custom_squads():
    md = '| Time | Women | Open | Source |\n| --- | --- | --- | --- |\n| 0:00 | Zone | Stack | X |'
    outline = so.parse(md, squads=('Women', 'Open'))
    assert outline.split.squads == ['Women', 'Open']
    assert so.parse(md, squads=('1s', '2s')).tables == []
