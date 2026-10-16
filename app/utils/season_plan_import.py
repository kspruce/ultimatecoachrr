"""Import a season plan from a markdown export folder. Used by
`flask import-season-plan`.

The folder holds manifest.json (the plan title and its tabs in order) and one
markdown file per tab. The structured data comes from pipe tables found by
their header row, wherever they are:

  Phase | Dates | Weeks | Aim | ...           -> SeasonPhase
  Wk | w/c | Ph | Block ... | Joint ... | ...  -> SeasonWeek
  When | What                                 -> SeasonMilestone
  Area | Phase 1 | Phase 2 | ...               -> SeasonPhase.progression

Every "## Week N" section of any tab becomes that week's session notes, and
every tab is stored as a SeasonPage. Classroom sessions come from the
"# | Week | Format | Who | Title" table and the "### C1 · Week 3 · ..." sections.

The import is an upsert on (team, season): phases match on number, weeks on
week number and pages on slug, and anything no longer in the export is
removed. Coaches' notes, SessionPlan links and who-can-see-what settings are
kept. Classroom sessions are refined by hand, so an import only fills their
empty fields (except the facilitator plan) and never touches summaries,
links, dates or resources. Once sessions have been built from the plan
(Season plan > Sessions), the import updates them too. The whole import is
one transaction, rolled back for dry runs.
"""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import db
from app.models.season_plan import (
    SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, SeasonMilestone, ClassroomSession,
)

MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], start=1)}
EMPTY_CELLS = {'', '-', '—', '–'}
PHASE_COLOURS = ['#2E7D5B', '#2F6DB5', '#C77D1A', '#B23A48', '#6A4C93', '#3A8F9E']

# A block cell that names a training block ("A", "B. Getting open", "I (Easter)")
# is not an event even when it mentions one ("I. Offence after Tour 1").
TRAINING_BLOCK_RE = re.compile(r'^[A-Z](?:\.|\s|$)')
EVENT_RE = re.compile(r'\b(tours?|tournament|trials?|regionals|nationals|euros|herdlodge|warm-up)\b', re.I)
WEEK_HEADING_RE = re.compile(r'^##\s+Week\s+(\d+)\b(.*)$')
DAY_MONTH_RE = re.compile(r'(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?(?:\s+(\d{4}))?')
WEEK_RANGE_RE = re.compile(r'weeks?\s+(\d+)(?:\s*[-–]\s*(\d+))?', re.I)

# Header signatures: first column, then prefixes other columns must start with
PHASE_COLUMNS = ('phase', 'dates', 'weeks')
WEEK_COLUMNS = ('wk', 'w/c', 'ph', 'joint')
MILESTONE_COLUMNS = ('when', 'what')
PROGRESSION_COLUMNS = ('area', 'phase 1')
CLASSROOM_COLUMNS = ('#', 'week', 'format', 'title')
CLASSROOM_HEADING_RE = re.compile(r'^###\s+(C(\d+))\b\s*(.*)$')

LIMITS = {
    'plan.title': 200, 'plan.season': 20, 'plan.source': 200,
    'phase.name': 100, 'phase.classroom_refs': 200,
    'week.block': 200, 'week.classroom': 200, 'week.session_title': 200,
    'page.slug': 100, 'page.title': 200, 'milestone.when_label': 100,
    'classroom.code': 10, 'classroom.title': 200, 'classroom.format': 100,
    'classroom.audience': 200, 'classroom.main_source': 200,
}


class SeasonPlanImportError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('\n'.join(errors))


@dataclass
class ImportReport:
    dry_run: bool = False
    replaced: bool = False
    plan_created: bool = False
    counts: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)  # rows that couldn't be parsed
    removed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    sessions: object = None  # season_sessions.BuildReport when sessions were built

    def text(self):
        out = ['DRY RUN: nothing was written' if self.dry_run else 'Import complete']
        if self.replaced:
            out.append('Replaced: the existing plan was wiped first')
        elif not self.dry_run:
            out.append('Created a new plan' if self.plan_created else 'Updated the existing plan')
        for kind in ('phases', 'weeks', 'session notes', 'pages', 'milestones', 'classroom sessions'):
            out.append(f'{kind}: {self.counts.get(kind, 0)}')
        if self.sessions is not None:
            out.append(self.sessions.text())
        for line in self.removed:
            out.append(f'removed: {line}')
        for line in self.warnings:
            out.append(f'warning: {line}')
        if self.skipped:
            out.append(f'{len(self.skipped)} rows could not be parsed:')
            out.extend(f'  - {line}' for line in self.skipped)
        return '\n'.join(out)


# --------------------------------------------------------------------------
# Markdown parsing
# --------------------------------------------------------------------------

def clean_cell(text):
    """Unescape markdown in a table cell; blank and dash-only cells -> None."""
    if text is None:
        return None
    text = re.sub(r'\\([\\`*_{}\[\]()#+\-.!~|>])', r'\1', text.strip())
    return None if text in EMPTY_CELLS else text


def _split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'):
        line = line[:-1]
    return [c.strip() for c in re.split(r'(?<!\\)\|', line)]


def parse_tables(markdown):
    """Every pipe table in the text: [{'header': [...], 'rows': [[...], ...],
    'start': first line index, 'end': index after the last row}].
    Header cells are lower-cased; body cells are raw (see clean_cell)."""
    tables, lines, i = [], markdown.splitlines(), 0
    while i < len(lines) - 1:
        if (lines[i].lstrip().startswith('|')
                and re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$', lines[i + 1])):
            header = [(clean_cell(c) or '').lower() for c in _split_row(lines[i])]
            start, rows, i = i, [], i + 2
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                rows.append(_split_row(lines[i]))
                i += 1
            tables.append({'header': header, 'rows': rows, 'start': start, 'end': i})
        else:
            i += 1
    return tables


def find_table(tables, *columns):
    """The first table whose first header cell is columns[0] and which has a
    header cell starting with each of the other columns. Other tabs reuse
    short headers ("Phase", "When"), so a single column isn't enough."""
    first, rest = columns[0].lower(), [c.lower() for c in columns[1:]]
    for t in tables:
        h = t['header']
        if h and h[0] == first and all(any(c.startswith(r) for c in h) for r in rest):
            return t
    return None


def _row_dict(table, row):
    """Map a row onto its header by column prefix ('block or event' -> 'block')."""
    cells = row + [''] * (len(table['header']) - len(row))
    return {h: clean_cell(c) for h, c in zip(table['header'], cells)}


def _col(rowd, *prefixes):
    for key, value in rowd.items():
        if any(key.startswith(p) for p in prefixes):
            return value
    return None


def split_week_sections(markdown):
    """{week_number: (title, body)} for each '## Week N · date · title' section.
    A section runs to the next level-2 heading."""
    sections, current, buf = {}, None, []

    def close():
        if current:
            sections[current[0]] = (current[1], '\n'.join(buf).strip())

    for line in markdown.splitlines():
        if line.startswith('## ') or line.startswith('# '):
            close()
            current, buf = None, []
            m = WEEK_HEADING_RE.match(line)
            if m:
                parts = [p.strip() for p in m.group(2).split('·') if p.strip()]
                # Drop the date part ("4 Oct") if the heading has one
                if parts and DAY_MONTH_RE.fullmatch(parts[0]):
                    parts = parts[1:]
                current = (int(m.group(1)), clean_cell(' · '.join(parts)))
            continue
        if current:
            buf.append(line)
    close()
    return sections


def first_paragraph(markdown):
    """The first plain paragraph after the H1."""
    for block in re.split(r'\n\s*\n', markdown):
        block = block.strip()
        if block and not block.startswith(('#', '|', '-', '*', '>')):
            return block
    return None


def split_classroom_sections(markdown):
    """{'C1': (heading_rest, body)} for each '### C1 · Week 3 · ... · Title'
    section. A section runs to the next heading of level 1-3."""
    sections, current, buf = {}, None, []

    def close():
        if current:
            sections[current[0]] = (current[1], '\n'.join(buf).strip())

    for line in markdown.splitlines():
        if re.match(r'^#{1,3}\s', line):
            close()
            current, buf = None, []
            m = CLASSROOM_HEADING_RE.match(line)
            if m:
                current = (m.group(1).upper(), m.group(3).lstrip('·').strip())
            continue
        if current:
            buf.append(line)
    close()
    return sections


def _bold_field(body, label):
    """The text after '**Label:**' on its line."""
    m = re.search(r'^\*\*' + re.escape(label) + r':\*\*\s*(.+)$', body or '', re.M | re.I)
    return m.group(1).strip() if m else None


def _bold_list(body, label):
    """The '- ' items under a '**Label:**' line."""
    lines = (body or '').splitlines()
    for i, line in enumerate(lines):
        if re.match(r'^\*\*' + re.escape(label) + r':\*\*\s*$', line.strip(), re.I):
            items = []
            for nxt in lines[i + 1:]:
                text = nxt.strip()
                if text.startswith(('- ', '* ')):
                    items.append(text[2:].strip())
                elif text:
                    break
            return items
    return []


def classroom_prep(body):
    """A starting 'before the session' note for players: the idea, the
    discussion questions and the commitment, which coaches then refine."""
    parts = []
    idea = _bold_list(body, 'The idea')
    if idea:
        parts.append("**What it's about**\n\n" + '\n'.join(f'- {i}' for i in idea))
    elif _bold_field(body, 'The idea'):
        parts.append(f"**What it's about:** {_bold_field(body, 'The idea')}")
    questions = _bold_list(body, 'Small-group questions')
    if questions:
        parts.append("**Questions we'll discuss**\n\n" + '\n'.join(f'- {q}' for q in questions))
    commitment = _bold_field(body, 'Commitment')
    if commitment:
        parts.append(f"**What we'll ask you to try:** {commitment}")
    return '\n\n'.join(parts) or None


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def _day_month(text):
    """(day, month, year or None) for the first 'D Mon [YYYY]' in text."""
    m = DAY_MONTH_RE.search(text or '')
    if not m or m.group(2).lower()[:3] not in MONTHS:
        return None
    return int(m.group(1)), MONTHS[m.group(2).lower()[:3]], int(m.group(3)) if m.group(3) else None


def _after(day, month, cursor):
    """The first date on or after roughly `cursor` with this day and month.
    Dates without a year are assumed to run forward through the season."""
    candidate = date(cursor.year, month, day)
    if candidate < cursor - timedelta(days=45):
        candidate = date(cursor.year + 1, month, day)
    return candidate


def _all_dates(text):
    return [(int(d), MONTHS[m.lower()[:3]], int(y) if y else None)
            for d, m, y in DAY_MONTH_RE.findall(text or '') if m.lower()[:3] in MONTHS]


def _parse_range(text, cursor):
    """'4 Oct - 19 Dec 2027' / '20 Mar - 18 Jun' -> (start, end)."""
    found = _all_dates(text)
    if not found:
        return None, None
    (sd, sm, sy) = found[0]
    (ed, em, ey) = found[-1] if len(found) > 1 else found[0]
    if sy is None and ey is not None and cursor is None:
        sy = ey if (sm, sd) <= (em, ed) else ey - 1
    if cursor is None and sy is None:
        return None, None
    start = date(sy, sm, sd) if sy else _after(sd, sm, cursor)
    end = date(ey, em, ed) if ey else _after(ed, em, start)
    return start, end


def _int(text):
    m = re.match(r'^\s*(\d+)', text or '')
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Reading the export
# --------------------------------------------------------------------------

def load_export(folder):
    """Read manifest.json and the tab files. Returns (manifest, [(tab, text)])."""
    errors = []
    path = os.path.join(folder, 'manifest.json')
    if not os.path.isfile(path):
        raise SeasonPlanImportError([f'No manifest.json in {folder}'])
    try:
        with open(path, encoding='utf-8') as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        raise SeasonPlanImportError([f'manifest.json is not valid JSON: {e}'])

    tabs = sorted(manifest.get('tabs') or [], key=lambda t: t.get('order', 0))
    if not tabs:
        errors.append('manifest.json lists no tabs')
    loaded = []
    root = os.path.realpath(folder)
    for tab in tabs:
        rel = tab.get('file') or ''
        full = os.path.realpath(os.path.join(folder, rel))
        if not rel or not full.startswith(root + os.sep):
            errors.append(f'Tab {tab.get("slug")!r}: bad file path {rel!r}')
        elif not os.path.isfile(full):
            errors.append(f'Tab {tab.get("slug")!r}: {rel} not found')
        elif not tab.get('slug') or not tab.get('title'):
            errors.append(f'Tab {rel}: needs a slug and a title')
        else:
            with open(full, encoding='utf-8') as f:
                loaded.append((tab, f.read()))
    if errors:
        raise SeasonPlanImportError(errors)
    return manifest, loaded


def parse_export(manifest, tabs, season=None):
    """Turn the export into plain dicts, ready to write. Raises
    SeasonPlanImportError for problems that stop the import; rows that can't
    be parsed are listed in result['skipped']."""
    errors, skipped, warnings = [], [], []
    all_tables = [(tab, parse_tables(text)) for tab, text in tabs]
    # Look in the tab holding both the phase and the week tables first (the
    # "at a glance" tab): other tabs have look-alike milestone and squad tables.
    main = next((i for i, (_, tables) in enumerate(all_tables)
                 if find_table(tables, *PHASE_COLUMNS) and find_table(tables, *WEEK_COLUMNS)), None)
    if main is not None:
        all_tables.insert(0, all_tables.pop(main))

    def table(*names):
        for tab, tables in all_tables:
            t = find_table(tables, *names)
            if t:
                return tab, t
        return None, None

    title = clean_cell(manifest.get('plan')) or 'Season plan'
    if not season:
        m = re.search(r'(\d{4}\s*/\s*\d{2,4})', title)
        season = m.group(1).replace(' ', '') if m else None
    if not season:
        errors.append('No season found in the manifest title; pass --season (e.g. 2027/28)')

    # ---- phases -----------------------------------------------------------
    phase_tab, phase_table = table(*PHASE_COLUMNS)
    phases, cursor = [], None
    if not phase_table:
        errors.append('No phase table found (columns: Phase | Dates | Weeks | ...)')
    else:
        for row in phase_table['rows']:
            r = _row_dict(phase_table, row)
            label = r.get('phase') or ''
            m = re.match(r'^\s*(\d+)\s*[.:)]?\s*(.*)$', label)
            if not m:
                skipped.append(f'phase row {label!r}: no phase number')
                continue
            start, end = _parse_range(r.get('dates'), cursor)
            if r.get('dates') and not start:
                skipped.append(f'phase {m.group(1)}: could not read dates {r.get("dates")!r}')
            cursor = end or cursor
            weeks = re.findall(r'\d+', r.get('weeks') or '')
            number = int(m.group(1))
            phases.append({
                'number': number,
                'name': m.group(2).strip() or f'Phase {number}',
                'start_date': start, 'end_date': end,
                'start_week': int(weeks[0]) if weeks else None,
                'end_week': int(weeks[-1]) if weeks else None,
                'aim': r.get('aim'),
                'training_focus': _col(r, 'training focus', 'focus'),
                'events': r.get('events'),
                'classroom_refs': _col(r, 'classroom'),
                'strategic_anchor': _col(r, 'strategic anchor', 'anchor'),
                'colour': PHASE_COLOURS[(number - 1) % len(PHASE_COLOURS)],
                'progression': None,
            })
        if not phases:
            errors.append('The phase table has no rows that could be read')
    by_number = {p['number']: p for p in phases}
    season_start = min((p['start_date'] for p in phases if p['start_date']), default=None)

    # ---- squad progression -------------------------------------------------
    _, prog = table(*PROGRESSION_COLUMNS)
    if prog:
        for row in prog['rows']:
            r = _row_dict(prog, row)
            area = r.get('area')
            for key, value in r.items():
                n = _int(key.replace('phase', '', 1)) if key.startswith('phase') else None
                if area and value and n in by_number:
                    by_number[n]['progression'] = by_number[n]['progression'] or {}
                    by_number[n]['progression'][area] = value

    # ---- weeks ------------------------------------------------------------
    _, week_table = table(*WEEK_COLUMNS)
    weeks, cursor = [], season_start
    if not week_table:
        errors.append('No week table found (columns: Wk | w/c | Ph | ... | Joint ...)')
    elif cursor is None:
        errors.append('The week table needs the phase dates (with a year) to date the weeks')
    else:
        last_number = 0
        for row in week_table['rows']:
            r = _row_dict(week_table, row)
            raw_wk = r.get('wk') or r.get('week')
            wc_text = _col(r, 'w/c', 'week commencing', 'date')
            phase_no = _int(_col(r, 'ph'))
            dates = _all_dates(wc_text)
            fields = {
                'block': _col(r, 'block'),
                'joint_theme': _col(r, 'joint'),
                'firsts_theme': _col(r, '1s'),
                'seconds_theme': _col(r, '2s'),
                'classroom': _col(r, 'classroom'),
                'off_pitch': _col(r, 'off-pitch', 'off pitch'),
            }
            number = _int(raw_wk)
            if number is not None:
                numbers = [number]
            elif dates and (fields['block'] or '').lower().startswith('break'):
                # A break row covering several unnumbered weeks ("20 Dec, 27 Dec")
                numbers = list(range(last_number + 1, last_number + 1 + len(dates)))
            else:
                skipped.append(f'week row {raw_wk!r} ({wc_text or "no date"}): no week number')
                continue
            if not dates:
                skipped.append(f'week {numbers[0]}: could not read the date {wc_text!r}')
                continue
            for n, (d, mth, y) in zip(numbers, dates):
                wc = date(y, mth, d) if y else _after(d, mth, cursor)
                cursor = wc
                phase = by_number.get(phase_no) if phase_no else next(
                    (p for p in phases if p['start_week'] and p['end_week']
                     and p['start_week'] <= n <= p['end_week']), None)
                if phase_no and not phase:
                    warnings.append(f'week {n}: phase {phase_no} is not in the phase table')
                block = fields['block'] or ''
                weeks.append({
                    'week_number': n,
                    'week_commencing': wc,
                    'phase_number': phase['number'] if phase else None,
                    'is_break': block.lower().startswith('break') or (phase_no is None and number is None),
                    'is_event': bool((not TRAINING_BLOCK_RE.match(block) and EVENT_RE.search(block))
                                     or re.search(r'\btournament\b', fields['joint_theme'] or '', re.I)),
                    **fields,
                })
                last_number = max(last_number, n)
        seen = set()
        for w in weeks:
            if w['week_number'] in seen:
                errors.append(f'Week {w["week_number"]} appears twice in the week table')
            seen.add(w['week_number'])

    # ---- milestones -------------------------------------------------------
    _, ms_table = table(*MILESTONE_COLUMNS)
    milestones = []
    if ms_table:
        for i, row in enumerate(ms_table['rows']):
            r = _row_dict(ms_table, row)
            if not r.get('when') or not r.get('what'):
                skipped.append(f'milestone row {i + 1}: needs both When and What')
                continue
            m = WEEK_RANGE_RE.search(r['when'])
            milestones.append({
                'order': len(milestones) + 1, 'when_label': r['when'], 'what': r['what'],
                'start_week': int(m.group(1)) if m else None,
                'end_week': int(m.group(2) or m.group(1)) if m else None,
            })

    # ---- session notes and pages -------------------------------------------
    week_numbers = {w['week_number'] for w in weeks}
    notes, pages = {}, []
    for tab, text in tabs:
        for n, (heading, body) in split_week_sections(text).items():
            if n in notes:
                warnings.append(f'week {n} has session notes in two tabs; using {tab["slug"]}')
            if n not in week_numbers:
                skipped.append(f'"## Week {n}" in {tab["slug"]}: no such week in the week table')
                continue
            notes[n] = (heading, body)
        pages.append({'slug': tab['slug'], 'title': tab['title'],
                      'order': tab.get('order', len(pages) + 1), 'body_markdown': text})
    for w in weeks:
        heading, body = notes.get(w['week_number'], (None, None))
        w['session_title'], w['session_detail_md'] = heading, body

    classroom = _parse_classroom(tabs, table, week_numbers, skipped, warnings)

    summary = None
    if phase_tab:
        summary = first_paragraph(dict((t['slug'], txt) for t, txt in tabs)[phase_tab['slug']])

    plan = {
        'season': season, 'title': title, 'summary': summary,
        'start_date': min((w['week_commencing'] for w in weeks), default=season_start),
        'end_date': max([p['end_date'] for p in phases if p['end_date']]
                        + [w['week_commencing'] + timedelta(days=6) for w in weeks], default=None),
        'source': clean_cell(manifest.get('source')),
    }

    _check_lengths(errors, plan, phases, weeks, pages, milestones, classroom)
    if errors:
        raise SeasonPlanImportError(errors)
    return {'plan': plan, 'phases': phases, 'weeks': weeks, 'pages': pages,
            'milestones': milestones, 'classroom': classroom, 'skipped': skipped,
            'warnings': warnings, 'notes_count': len(notes)}


def _parse_classroom(tabs, table, week_numbers, skipped, warnings):
    """Classroom sessions from the series table and the '### C1 ...' sections.
    Either is enough on its own; the table wins where both give a value."""
    sections = {}
    for tab, text in tabs:
        for code, value in split_classroom_sections(text).items():
            if code in sections:
                warnings.append(f'classroom {code} appears in two tabs; using {tab["slug"]}')
            sections[code] = value

    rows = {}
    _, series = table(*CLASSROOM_COLUMNS)
    if series:
        for row in series['rows']:
            r = _row_dict(series, row)
            code = (r.get('#') or '').upper()
            if not re.fullmatch(r'C\d+', code):
                skipped.append(f'classroom row {r.get("#")!r}: no session code like C1')
                continue
            rows[code] = r

    sessions = []
    for code in sorted(set(rows) | set(sections), key=lambda c: int(c[1:])):
        r = rows.get(code, {})
        heading, body = sections.get(code, ('', None))
        # Heading: "Week 3 (w/c 18 Oct) · Online · [audience ·] Title"
        parts = [p.strip() for p in heading.split('·') if p.strip()]
        week_part = parts.pop(0) if parts and re.match(r'weeks?\b', parts[0], re.I) else None
        h_title = clean_cell(parts[-1]) if parts else None
        h_format = clean_cell(parts[0]) if len(parts) > 1 else None
        h_audience = clean_cell(' · '.join(parts[1:-1])) if len(parts) > 2 else None
        week_no = _int(r.get('week'))
        if week_no is None and week_part:
            week_no = _int(re.sub(r'(?i)^weeks?\s*', '', week_part))
        title = r.get('title') or h_title
        if not title:
            skipped.append(f'classroom {code}: no title')
            continue
        if week_no is not None and week_no not in week_numbers:
            warnings.append(f'classroom {code}: week {week_no} is not in the week table')
            week_no = None
        sessions.append({
            'code': code, 'number': int(code[1:]), 'title': title,
            'format': r.get('format') or h_format,
            'audience': _col(r, 'who', 'audience') or h_audience,
            'main_source': _col(r, 'main source', 'source'),
            'goal': _bold_field(body, 'Goal'),
            'plan_md': body or None,
            'prep_md': classroom_prep(body),
            'week_number': week_no,
        })
    return sessions


def _check_lengths(errors, plan, phases, weeks, pages, milestones, classroom=()):
    groups = {'plan': [plan], 'phase': phases, 'week': weeks, 'page': pages,
              'milestone': milestones, 'classroom': list(classroom)}
    for key, limit in LIMITS.items():
        kind, attr = key.split('.')
        for item in groups[kind]:
            value = item.get(attr)
            if isinstance(value, str) and len(value) > limit:
                errors.append(f'{kind} {attr} is longer than {limit} characters: {value[:40]!r}...')


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _apply(obj, values):
    for key, value in values.items():
        setattr(obj, key, value)


# Kept across --replace, so sessions built from the plan stay in step
SESSION_SETTINGS = ['joint_weekday', 'joint_start', 'joint_end', 'split_weekday', 'split_start',
                    'split_end', 'session_location', 'sessions_built_at']


def import_season_plan(folder, team, season=None, dry_run=False, replace=False, now=None,
                       build_sessions=None):
    """Import the export in `folder` into `team` (a TeamOrganization).
    build_sessions: True builds the plan's sessions, False leaves them, and
    None (the default) updates them only if they were built before."""
    from app.utils import season_sessions
    manifest, tabs = load_export(folder)
    data = parse_export(manifest, tabs, season=season)
    report = ImportReport(dry_run=dry_run, skipped=data['skipped'], warnings=data['warnings'])
    team_id = team.id

    try:
        plan = SeasonPlan.query.filter_by(team_organization_id=team_id,
                                          season=data['plan']['season']).first()
        kept = {}
        if plan and replace:
            kept = {name: getattr(plan, name) for name in SESSION_SETTINGS}
            db.session.delete(plan)
            db.session.flush()
            plan, report.replaced = None, True
        if plan is None:
            plan = SeasonPlan(team_organization_id=team_id, is_active=True)
            db.session.add(plan)
            report.plan_created = True
        _apply(plan, {**kept, **data['plan']})
        plan.imported_at = now or datetime.utcnow()
        db.session.flush()

        # Phases
        existing = {p.number: p for p in plan.phases}
        phase_objs = {}
        for values in data['phases']:
            phase = existing.pop(values['number'], None)
            if phase is None:
                phase = SeasonPhase(team_organization_id=team_id)
                plan.phases.append(phase)
            _apply(phase, values)
            phase_objs[values['number']] = phase
        db.session.flush()

        # Weeks: keep notes and session_plan_id, which aren't in the export
        existing_weeks = {w.week_number: w for w in plan.weeks}
        for values in data['weeks']:
            values = dict(values)
            phase_no = values.pop('phase_number')
            week = existing_weeks.pop(values['week_number'], None)
            if week is None:
                week = SeasonWeek(team_organization_id=team_id)
                plan.weeks.append(week)
            _apply(week, values)
            week.phase = phase_objs.get(phase_no)
        for week in existing_weeks.values():
            linked = ' (was linked to a session plan)' if week.session_plan_id else ''
            report.removed.append(f'week {week.week_number}{linked}')
            plan.weeks.remove(week)
        for phase in existing.values():
            report.removed.append(f'phase {phase.number} {phase.name}')
            plan.phases.remove(phase)

        # Pages: keep players_can_view
        existing_pages = {p.slug: p for p in plan.pages}
        for values in data['pages']:
            page = existing_pages.pop(values['slug'], None)
            if page is None:
                page = SeasonPage(team_organization_id=team_id)
                plan.pages.append(page)
            _apply(page, values)
        for page in existing_pages.values():
            report.removed.append(f'page {page.slug}')
            plan.pages.remove(page)

        # Milestones have no stable key, so they're rebuilt
        plan.milestones.clear()
        db.session.flush()
        for values in data['milestones']:
            plan.milestones.append(SeasonMilestone(team_organization_id=team_id, **values))

        _sync_classroom(plan, data['classroom'], team_id, report)

        db.session.flush()
        db.session.expire(plan, ['weeks'])  # in week order for the session build
        if build_sessions or (build_sessions is None and plan.sessions_built_at):
            report.sessions = season_sessions.build_sessions(plan, commit=False)
        report.counts = {'phases': len(data['phases']), 'weeks': len(data['weeks']),
                         'session notes': data['notes_count'], 'pages': len(data['pages']),
                         'milestones': len(data['milestones']),
                         'classroom sessions': len(data['classroom'])}
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return report


# Classroom fields an import fills only while they're empty, so a coach's
# refinements survive a re-import. plan_md and the week always follow the export.
CLASSROOM_FILL_ONLY = ('title', 'format', 'audience', 'main_source', 'goal', 'prep_md')


def _sync_classroom(plan, sessions, team_id, report):
    existing = {c.code: c for c in plan.classroom_sessions}
    week_by_number = {w.week_number: w for w in plan.weeks}
    for values in sessions:
        cs = existing.pop(values['code'], None)
        if cs is None:
            cs = ClassroomSession(team_organization_id=team_id, code=values['code'])
            plan.classroom_sessions.append(cs)
        cs.number = values['number']
        cs.plan_md = values['plan_md']
        cs.week = week_by_number.get(values['week_number'])
        for name in CLASSROOM_FILL_ONLY:
            if not getattr(cs, name) and values.get(name):
                setattr(cs, name, values[name])
    for cs in existing.values():
        if cs.has_coach_content:
            report.warnings.append(f'classroom {cs.code} is no longer in the export; kept because '
                                   'it has a date, link, summary or resources')
        else:
            report.removed.append(f'classroom {cs.code}')
            plan.classroom_sessions.remove(cs)
