"""A week's session notes as structure: the timed session tables and the
learning points, with everything else kept exactly as written.

The season plan stores each week's session notes as markdown (see
app/utils/season_sessions.py for what Build sessions reads from them). An
editor, or a session saved in the planner, needs to change the tables
without disturbing the coach's prose around them, so:

    outline = parse(markdown, squads)   # text, tables and learning points
    outline.joint.rows[2]['activity'] = 'Gate drill'
    markdown = render(outline)          # the same notes, that table rewritten

Only the tables Build sessions uses become structure: the first joint table
(Time | Activity | How it runs | Source) and the first split table (Time | a
column per squad | Source), each with the bold line above it as its label.
Any other table stays as text, and `outline.unsupported` says so, so an
editor can fall back to editing the markdown.

render(parse(md)) is md exactly; a changed table or learning points line is
written afresh, and gives the same sessions as before for anything not
changed (tests/test_session_outline.py checks every week of a real season).
"""
import copy
from dataclasses import dataclass, field

from app.utils.season_plan_import import clean_cell, parse_tables
from app.utils.season_sessions import LABEL_RE, LEARNING_RE, NUMBERED_RE, _squad_columns, length_from_label

JOINT_KEYS = {'activity': 'activity', 'how': 'how', 'source': 'source'}


@dataclass
class Table:
    """A session table. `columns` is [(key, header)]: key 'time',
    'activity', 'how', 'source', or a squad's name in a split table.
    `rows` are {key: cell text or None}, cells unescaped (clean_cell)."""
    kind: str  # 'joint' or 'split'
    columns: list
    rows: list = field(default_factory=list)
    label: str = None  # the bold line above, e.g. '**Joint session**'
    gap: list = field(default_factory=list)  # blank lines between label and table, as written
    raw: str = field(default=None, repr=False, compare=False)  # the text as written
    _was: tuple = field(default=None, repr=False, compare=False)

    def _state(self):
        return (self.kind, copy.deepcopy(self.columns), copy.deepcopy(self.rows), self.label)

    @property
    def changed(self):
        return self.raw is None or self._was != self._state()

    @property
    def squads(self):
        reserved = {'time', 'activity', 'how', 'source'}
        return [k for k, _ in self.columns if k not in reserved]

    @property
    def length(self):
        """Minutes, from a label such as '(about 2 hours)', or None."""
        m = LABEL_RE.match(self.label or '')
        return length_from_label(m.group(1) + ' ' + m.group(2)) if m else None


@dataclass
class LearningPoints:
    points: list
    raw: str = field(default=None, repr=False, compare=False)
    _was: list = field(default=None, repr=False, compare=False)

    @property
    def changed(self):
        return self.raw is None or self._was != self.points


@dataclass
class Outline:
    parts: list  # str (verbatim text, possibly several lines) | Table | LearningPoints
    unsupported: bool = False  # timed tables kept as text: edit as markdown

    def _first(self, kind):
        return next((p for p in self.parts if isinstance(p, Table) and p.kind == kind), None)

    @property
    def joint(self):
        return self._first('joint')

    @property
    def split(self):
        return self._first('split')

    @property
    def tables(self):
        return [p for p in self.parts if isinstance(p, Table)]

    @property
    def learning_points(self):
        found = next((p for p in self.parts if isinstance(p, LearningPoints)), None)
        return found.points if found else []


def _column_key(header, squad_cols, i):
    if i == 0:
        return 'time'
    for prefix, key in JOINT_KEYS.items():
        if header.startswith(prefix):
            return key
    return squad_cols.get(i)


def _table(t, squads):
    """A Table for a timed table Build sessions would read, else None."""
    header = t['header']
    if not header or header[0] != 'time':
        return None
    raw = t.get('raw_header') or header
    is_joint = any(h.startswith('activity') for h in header)
    squad_cols = {} if is_joint else _squad_columns(t, squads)
    if not is_joint and not squad_cols:
        return None
    columns = []
    for i, h in enumerate(header):
        key = _column_key(h, squad_cols, i)
        if key is None or (is_joint and key not in ('time', 'activity', 'how', 'source')) \
                or (not is_joint and key in ('activity', 'how')) or key in [k for k, _ in columns]:
            return False  # a timed table with a column we don't understand
        columns.append((key, raw[i]))
    rows = []
    for r in t['rows']:
        cells = r + [''] * (len(columns) - len(r))
        rows.append({key: clean_cell(cells[i]) for i, (key, _) in enumerate(columns)})
    return Table(kind='joint' if is_joint else 'split', columns=columns, rows=rows)


def parse(markdown, squads=('1s', '2s')):
    """The notes as an Outline. `squads` are the plan's squads, which a
    split table's columns are matched to."""
    lines = (markdown or '').splitlines()
    structured = {}  # first line index -> (end index, part)
    unsupported = False
    seen = set()
    for t in parse_tables(markdown or ''):
        table = _table(t, squads)
        if table is False:
            unsupported = True
            continue
        if table is None:
            continue
        if table.kind in seen:
            unsupported = True  # a second joint (or split) table: Build sessions ignores it
            continue
        seen.add(table.kind)
        start = t['start']
        # The bold line just above (blank lines between) labels it
        j = start - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and LABEL_RE.match(lines[j]) and not LEARNING_RE.match(lines[j]) \
                and j not in structured and all(not (s <= j < e) for s, (e, _) in structured.items()):
            table.label = lines[j]
            table.gap = lines[j + 1:start]
            start = j
        table.raw = '\n'.join(lines[start:t['end']])
        table._was = table._state()
        structured[start] = (t['end'], table)

    for i, line in enumerate(lines):
        if LEARNING_RE.match(line) and not any(s <= i < e for s, (e, _) in structured.items()):
            m = LEARNING_RE.match(line)
            points = [clean_cell(p) for p in NUMBERED_RE.split(m.group(1)) if p.strip()]
            structured[i] = (i + 1, LearningPoints(points or [], raw=line, _was=list(points or [])))
            break

    parts, text, i = [], [], 0
    while i < len(lines):
        if i in structured:
            if text:
                parts.append('\n'.join(text))
                text = []
            end, part = structured[i]
            parts.append(part)
            i = end
        else:
            text.append(lines[i])
            i += 1
    if text:
        parts.append('\n'.join(text))
    return Outline(parts=parts, unsupported=unsupported)


def _cell(text):
    """A cell for a markdown table row: one line, pipes escaped."""
    text = ' '.join((text or '').split())
    return text.replace('\\|', '|').replace('|', '\\|')


def render_table(table):
    """The table as markdown: as written if it hasn't been changed."""
    if not table.changed:
        return table.raw
    lines = []
    if table.label:
        lines.append(table.label)
        lines.extend(table.gap or [''])
    lines.append('| ' + ' | '.join(_cell(h) for _, h in table.columns) + ' |')
    lines.append('| ' + ' | '.join('---' for _ in table.columns) + ' |')
    for row in table.rows:
        lines.append('| ' + ' | '.join(_cell(row.get(key)) for key, _ in table.columns) + ' |')
    return '\n'.join(lines)


def render_learning_points(points):
    return '**Learning points:** ' + ' '.join(f'({i}) {p}' for i, p in enumerate(points, start=1))


def render(outline):
    out = []
    for part in outline.parts:
        if isinstance(part, Table):
            out.append(render_table(part))
        elif isinstance(part, LearningPoints):
            if not part.changed:
                out.append(part.raw)
            elif part.points:
                out.append(render_learning_points(part.points))
        else:
            out.append(part)
    return '\n'.join(out)


# ── Times ───────────────────────────────────────────────────────────────────

def clock(minutes):
    """90 -> '1:30': the session-relative times the plan's tables use."""
    return f'{minutes // 60}:{minutes % 60:02d}'


def retime(table, durations, start=0):
    """Set the rows' times from how long each runs (minutes, one per row;
    None counts as 0), counting from `start` minutes."""
    t = start
    for row, mins in zip(table.rows, durations):
        row['time'] = clock(t)
        t += mins or 0
