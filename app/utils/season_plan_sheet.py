"""Season plans as a spreadsheet: the template a club downloads, reading an
upload into the same data the markdown import produces (so
season_plan_import.write_plan writes either), and exporting a plan back to
the same format.

Sheets (an .xlsx; or one CSV for the weeks):

  weeks       one row per week: week, week_commencing, phase, block, event,
              break, theme, classroom, off_pitch, session_title,
              session_notes. Any other column is a squad's theme, headed with
              the squad's name ("1s", "Women").
  phases      optional: phase, name, start_week, end_week, aim,
              training_focus, events, strategic_anchor, colour
  milestones  optional: when, what, start_week, end_week
"""
import io
import re
from datetime import date, timedelta

from app.utils.season_plan_import import PHASE_COLOURS, SQUAD_NAME_LIMIT, _check_lengths

WEEK_COLUMNS = ['week', 'week_commencing', 'phase', 'block', 'event', 'break', 'theme', 'classroom',
                'off_pitch', 'session_title', 'session_notes']
WEEK_ALIASES = {'wk': 'week', 'w/c': 'week_commencing', 'date': 'week_commencing', 'joint': 'theme',
                'joint_theme': 'theme', 'joint_session': 'theme', 'off-pitch': 'off_pitch', 'ph': 'phase',
                'block_or_event': 'block', 'notes': 'session_notes', 'session_detail': 'session_notes'}
PHASE_COLUMNS = ['phase', 'name', 'start_week', 'end_week', 'aim', 'training_focus', 'events',
                 'strategic_anchor', 'colour']
MILESTONE_COLUMNS = ['when', 'what', 'start_week', 'end_week']
YES = {'yes', 'y', 'true', 'x', '1', '✓'}
MAX_ROWS = 200

WEEK_HELP = {
    'week': ('Week number: 1, 2, 3... Required.', '1'),
    'week_commencing': ('The Monday the week starts (2027-10-04). Leave blank to count on from the start date '
                        'you give when you upload.', '2027-10-04'),
    'phase': ('The phase the week is in: its number or its name.', '1'),
    'block': ('A short name for the week or block of weeks, or the event.', 'Throwing base'),
    'event': ('yes for a tournament or other event week.', ''),
    'break': ('yes for a week with no training.', ''),
    'theme': ('The week\'s theme: for the whole club, or the joint session when squads have their own.',
              'Grip, pivot and the backhand'),
    'classroom': ('An off-pitch session that week, if any.', 'C1 How we learn'),
    'off_pitch': ('Anything else off the pitch: tests, socials, deadlines.', 'Baseline tests'),
    'session_title': ('A title for the week\'s session notes.', 'Welcome and baseline tests'),
    'session_notes': ('The session notes (markdown). A timed table here can be built into a session.', ''),
}
SQUAD_HELP = ('A squad\'s own theme that week. Name the column after the squad (1s, Women...); add a '
              'column per squad, or delete these if you have one squad.')
PHASE_HELP = {
    'phase': ('Phase number: 1, 2, 3...', '1'),
    'name': ('Phase name.', 'Foundations'),
    'start_week': ('First week of the phase. Blank: worked out from the weeks sheet.', '1'),
    'end_week': ('Last week of the phase. Blank: worked out from the weeks sheet.', '4'),
    'aim': ('What the phase is for.', 'Every player throws better'),
    'training_focus': ('What training concentrates on.', 'Throwing, catching, cutting'),
    'events': ('Events during the phase.', 'Tournament in week 12'),
    'strategic_anchor': ('One idea that runs through the phase.', 'Resets'),
    'colour': ('A colour for the timeline, like #2E7D5B. Blank picks one.', '#2E7D5B'),
}
MILESTONE_HELP = {
    'when': ('When, in words. Blank: made from the weeks.', 'Week 1'),
    'what': ('What happens. Required.', 'Baseline tests'),
    'start_week': ('The week it happens (or starts).', '1'),
    'end_week': ('The last week, for something that runs over several weeks.', ''),
}

EXAMPLE_WEEKS = [
    {'week': 1, 'week_commencing': '2027-10-04', 'phase': 1, 'block': 'Throwing base',
     'theme': 'Grip, pivot and the backhand', '1s': 'Throwing under a mark', '2s': 'Throwing to targets',
     'off_pitch': 'Baseline tests'},
    {'week': 2, 'phase': 1, 'block': 'Throwing base', 'theme': 'Catching and the dump-swing',
     '1s': 'Resets under pressure', '2s': 'Dump and swing'},
    {'week': 3, 'phase': 2, 'block': 'Tournament', 'event': 'yes', 'theme': 'Light session: set plays'},
]
EXAMPLE_PHASES = [
    {'phase': 1, 'name': 'Foundations', 'start_week': 1, 'end_week': 2, 'aim': 'Every player throws better',
     'colour': '#2E7D5B'},
    {'phase': 2, 'name': 'Competing', 'start_week': 3, 'end_week': 3, 'aim': 'Play well as a team'},
]
EXAMPLE_MILESTONES = [{'when': 'Week 1', 'what': 'Baseline tests', 'start_week': 1}]


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def _norm(header):
    return re.sub(r'\s+', '_', (header or '').strip().lower())


def _records(rows, known, aliases=None, keep_unknown=False):
    """(header list, [(row number, {column: value})]). Unknown columns are
    kept under their own text when keep_unknown is set, else dropped."""
    rows = [r for r in rows if any((c or '').strip() for c in r)]
    if not rows:
        return [], []
    raw = [(h or '').strip() for h in rows[0]]
    header = []
    for h in raw:
        key = _norm(h)
        key = (aliases or {}).get(key, key)
        header.append(key if key in known else (h if keep_unknown and h else None))
    out = []
    for i, row in enumerate(rows[1:], start=2):
        out.append((i, {col: (value or '').strip() for col, value in zip(header, row) if col}))
    return header, out


def _int(text):
    text = (text or '').strip()
    if re.fullmatch(r'\d+(\.0+)?', text):
        return int(float(text))
    return None


def parse_date(text):
    """2027-10-04, 4/10/2027 (day first), or an Excel date as text."""
    text = (text or '').strip()
    if not text:
        return None
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', text)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r'^(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})$', text)
        if m:
            year = int(m.group(3))
            return date(year + 2000 if year < 100 else year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def parse_sheets(weeks_rows, phase_rows=None, milestone_rows=None, start=None, season=None, title=None,
                 summary=None):
    """Read the sheets into write_plan's data, or {'errors': [...]} with
    "weeks row 4: ..." messages. `start` dates weeks with no
    week_commencing (the first week starts that Monday)."""
    errors, warnings = [], []

    header, week_records = _records(weeks_rows, WEEK_COLUMNS, WEEK_ALIASES, keep_unknown=True)
    if not week_records:
        errors.append('The weeks sheet is empty: it needs a header row and a row per week.')
    elif 'week' not in header:
        errors.append('The weeks sheet needs a "week" column with the week numbers.')
    squads = [h for h in header if h and h not in WEEK_COLUMNS]
    for name in squads:
        if len(name) > SQUAD_NAME_LIMIT:
            errors.append(f'weeks sheet: the squad column "{name[:40]}" is longer than '
                          f'{SQUAD_NAME_LIMIT} characters.')
        if name.lower() == 'joint':
            errors.append('weeks sheet: call the joint session\'s column "theme".')
    if len(week_records) > MAX_ROWS:
        errors.append(f'The weeks sheet has more than {MAX_ROWS} rows.')
    if errors:
        return {'errors': errors, 'warnings': warnings}

    # ---- phases sheet -----------------------------------------------------
    phases, by_name = {}, {}
    _, phase_records = _records(phase_rows or [], PHASE_COLUMNS)
    for row, r in phase_records:
        number = _int(r.get('phase'))
        name = r.get('name') or (f'Phase {number}' if number else None)
        if number is None:
            errors.append(f'phases row {row}: the phase needs a number.')
            continue
        if number in phases:
            errors.append(f'phases row {row}: phase {number} appears twice.')
            continue
        colour = r.get('colour') or None
        if colour and not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
            warnings.append(f'phases row {row}: colour {colour!r} isn\'t like #2E7D5B; picked one instead.')
            colour = None
        phases[number] = {
            'number': number, 'name': name, 'start_week': _int(r.get('start_week')),
            'end_week': _int(r.get('end_week')), 'aim': r.get('aim') or None,
            'training_focus': r.get('training_focus') or None, 'events': r.get('events') or None,
            'strategic_anchor': r.get('strategic_anchor') or None, 'classroom_refs': None,
            'colour': colour or PHASE_COLOURS[(number - 1) % len(PHASE_COLOURS)], 'progression': None,
            'start_date': None, 'end_date': None,
        }
        by_name[name.lower()] = number

    # ---- weeks ------------------------------------------------------------
    weeks, seen = [], {}
    for row, r in week_records:
        number = _int(r.get('week'))
        if number is None or number < 1:
            if any(v for k, v in r.items() if k != 'week'):
                errors.append(f'weeks row {row}: "{r.get("week", "")}" isn\'t a week number (1, 2, 3...).')
            continue
        if number in seen:
            errors.append(f'weeks row {row}: week {number} is already on row {seen[number]}.')
            continue
        seen[number] = row
        wc = None
        if r.get('week_commencing'):
            wc = parse_date(r['week_commencing'])
            if wc is None:
                errors.append(f'weeks row {row}: couldn\'t read the date {r["week_commencing"]!r} '
                              '(use 2027-10-04).')
                continue
        phase_cell = r.get('phase') or ''
        phase_no = _int(phase_cell)
        if phase_cell and phase_no is None:
            phase_no = by_name.get(phase_cell.lower())
            if phase_no is None:
                # A phase named only on the weeks sheet
                phase_no = max(list(phases) + [0]) + 1
                phases[phase_no] = {
                    'number': phase_no, 'name': phase_cell[:100], 'start_week': None, 'end_week': None,
                    'aim': None, 'training_focus': None, 'events': None, 'strategic_anchor': None,
                    'classroom_refs': None, 'colour': PHASE_COLOURS[(phase_no - 1) % len(PHASE_COLOURS)],
                    'progression': None, 'start_date': None, 'end_date': None}
                by_name[phase_cell.lower()] = phase_no
        elif phase_no is not None and phase_no not in phases:
            phases[phase_no] = {
                'number': phase_no, 'name': f'Phase {phase_no}', 'start_week': None, 'end_week': None,
                'aim': None, 'training_focus': None, 'events': None, 'strategic_anchor': None,
                'classroom_refs': None, 'colour': PHASE_COLOURS[(phase_no - 1) % len(PHASE_COLOURS)],
                'progression': None, 'start_date': None, 'end_date': None}
        weeks.append({
            'row': row, 'week_number': number, 'week_commencing': wc, 'phase_number': phase_no,
            'block': r.get('block') or None, 'joint_theme': r.get('theme') or None,
            'squad_themes': {q: r[q] for q in squads if r.get(q)} or None,
            'classroom': r.get('classroom') or None, 'off_pitch': r.get('off_pitch') or None,
            'session_title': r.get('session_title') or None,
            'session_detail_md': r.get('session_notes') or None,
            'is_event': (r.get('event') or '').lower() in YES,
            'is_break': (r.get('break') or '').lower() in YES,
        })
    weeks.sort(key=lambda w: w['week_number'])
    if not weeks and not errors:
        errors.append('The weeks sheet has no week numbers.')

    # Dates: from the start date, or counted from the first dated week
    if weeks:
        if start is None:
            first_dated = next((w for w in weeks if w['week_commencing']), None)
            if first_dated:
                start = first_dated['week_commencing'] - timedelta(
                    weeks=first_dated['week_number'] - weeks[0]['week_number'])
        if start is None and any(w['week_commencing'] is None for w in weeks):
            errors.append('Give a start date, or a week_commencing date on at least one week.')
        else:
            first = start - timedelta(days=start.weekday()) if start else None
            for w in weeks:
                if w['week_commencing'] is None:
                    w['week_commencing'] = first + timedelta(weeks=w['week_number'] - weeks[0]['week_number'])

    # Phase week ranges from the weeks sheet where the phases sheet has none
    for p in phases.values():
        numbers = [w['week_number'] for w in weeks if w['phase_number'] == p['number']]
        if not p['start_week'] and numbers:
            p['start_week'] = min(numbers)
        if not p['end_week'] and numbers:
            p['end_week'] = max(numbers)
    week_numbers = {w['week_number'] for w in weeks}
    for w in weeks:
        if w['phase_number'] is None:
            p = next((p for p in phases.values() if p['start_week'] and p['end_week']
                      and p['start_week'] <= w['week_number'] <= p['end_week']), None)
            w['phase_number'] = p['number'] if p else None
    by_number = {w['week_number']: w for w in weeks}
    ordered = sorted(phases.values(), key=lambda p: (p['start_week'] or 0))
    for a, b in zip(ordered, ordered[1:]):
        if a['end_week'] and b['start_week'] and b['start_week'] <= a['end_week']:
            errors.append(f'Phases {a["number"]} and {b["number"]} overlap (weeks {b["start_week"]}-'
                          f'{a["end_week"]}).')
    for p in phases.values():
        if p['start_week'] and p['start_week'] not in week_numbers:
            warnings.append(f'phase {p["number"]} starts in week {p["start_week"]}, which isn\'t on the weeks sheet.')
        first, last = by_number.get(p['start_week']), by_number.get(p['end_week'])
        p['start_date'] = first['week_commencing'] if first else None
        p['end_date'] = last['week_commencing'] + timedelta(days=6) if last and last['week_commencing'] else None

    # ---- milestones -------------------------------------------------------
    milestones = []
    _, milestone_records = _records(milestone_rows or [], MILESTONE_COLUMNS)
    for row, r in milestone_records:
        if not r.get('what'):
            errors.append(f'milestones row {row}: say what the milestone is (the "what" column).')
            continue
        start_week, end_week = _int(r.get('start_week')), _int(r.get('end_week'))
        when = r.get('when') or (f'Weeks {start_week}-{end_week}' if start_week and end_week and end_week != start_week
                                 else f'Week {start_week}' if start_week else None)
        if not when:
            errors.append(f'milestones row {row}: give a "when" or a start_week.')
            continue
        milestones.append({'order': len(milestones) + 1, 'when_label': when[:100], 'what': r['what'],
                           'start_week': start_week, 'end_week': end_week or start_week})

    for w in weeks:
        w.pop('row')
    plan = {
        'season': season, 'title': title or 'Season plan', 'summary': summary or None,
        'start_date': weeks[0]['week_commencing'] if weeks else None,
        'end_date': (max(w['week_commencing'] for w in weeks) + timedelta(days=6)) if weeks and not errors else None,
        'source': 'Spreadsheet import', 'squad_names': squads or None,
    }
    if not errors:
        _check_lengths(errors, plan, list(phases.values()), weeks, None, milestones)
    return {'errors': errors, 'warnings': warnings, 'plan': plan,
            'phases': sorted(phases.values(), key=lambda p: p['number']), 'weeks': weeks,
            'milestones': milestones, 'pages': None, 'classroom': None, 'skipped': [],
            'notes_count': sum(1 for w in weeks if w['session_detail_md'])}


# --------------------------------------------------------------------------
# Writing: the template and exports
# --------------------------------------------------------------------------

def plan_rows(plan):
    """(weeks rows, phases rows, milestones rows) for a plan, each with its
    header first."""
    squads = plan.squads
    weeks = [WEEK_COLUMNS[:7] + squads + WEEK_COLUMNS[7:]]
    for w in plan.weeks:
        weeks.append([w.week_number, w.week_commencing.isoformat() if w.week_commencing else '',
                      w.phase.number if w.phase else '', w.block or '', 'yes' if w.is_event else '',
                      'yes' if w.is_break else '', w.joint_theme or '']
                     + [w.theme_for(q) or '' for q in squads]
                     + [w.classroom or '', w.off_pitch or '', w.session_title or '', w.session_detail_md or ''])
    phases = [PHASE_COLUMNS] + [[p.number, p.name, p.start_week or '', p.end_week or '', p.aim or '',
                                 p.training_focus or '', p.events or '', p.strategic_anchor or '', p.colour or '']
                                for p in plan.phases]
    milestones = [MILESTONE_COLUMNS] + [[m.when_label, m.what, m.start_week or '', m.end_week or '']
                                        for m in plan.milestones]
    return weeks, phases, milestones


def _example_rows():
    squads = ['1s', '2s']
    weeks = [WEEK_COLUMNS[:7] + squads + WEEK_COLUMNS[7:]]
    for r in EXAMPLE_WEEKS:
        weeks.append([r.get(c, '') for c in weeks[0]])
    phases = [PHASE_COLUMNS] + [[r.get(c, '') for c in PHASE_COLUMNS] for r in EXAMPLE_PHASES]
    milestones = [MILESTONE_COLUMNS] + [[r.get(c, '') for c in MILESTONE_COLUMNS] for r in EXAMPLE_MILESTONES]
    return weeks, phases, milestones


def workbook_bytes(plan=None):
    """The blank template (example rows in grey), or a plan's export."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    header_fill = PatternFill('solid', fgColor='1F3A5F')
    squad_fill = PatternFill('solid', fgColor='2E7D5B')
    required_fill = PatternFill('solid', fgColor='B23A48')
    example_font = Font(color='5B6B7F', italic=True)
    wrap = Alignment(wrap_text=True, vertical='top')
    sheets = plan_rows(plan) if plan else _example_rows()

    wb = Workbook()
    guide = wb.active
    guide.title = 'Instructions'

    def sheet(title, rows, helps, required):
        ws = wb.create_sheet(title)
        columns = rows[0]
        ws.append(columns)
        for i, column in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=i)
            cell.font = Font(bold=True, color='FFFFFF')
            known = column in helps
            cell.fill = required_fill if column in required else (header_fill if known else squad_fill)
            text = helps[column][0] if known else SQUAD_HELP
            cell.comment = Comment(text, 'Ultimate Coach', width=280, height=110)
            wide = column in ('theme', 'session_notes', 'aim', 'training_focus', 'what') or not known
            ws.column_dimensions[get_column_letter(i)].width = 32 if wide else max(len(str(column)) + 4, 12)
        for row in rows[1:]:
            ws.append(row)
            if plan is None:
                for i in range(1, len(columns) + 1):
                    ws.cell(row=ws.max_row, column=i).font = example_font
        ws.freeze_panes = 'B2'
        for column in ('event', 'break'):
            if column in columns:
                letter = get_column_letter(columns.index(column) + 1)
                dv = DataValidation(type='list', formula1='"yes"', allow_blank=True)
                dv.add(f'{letter}2:{letter}{MAX_ROWS + 1}')
                ws.add_data_validation(dv)
        return ws

    sheet('weeks', sheets[0], WEEK_HELP, {'week'})
    sheet('phases', sheets[1], PHASE_HELP, {'phase', 'name'})
    sheet('milestones', sheets[2], MILESTONE_HELP, {'what'})

    guide.column_dimensions['A'].width = 100
    guide.sheet_view.showGridLines = False
    lines = [
        (f'Season plan: {plan.title}' if plan else 'Season plan template', Font(bold=True, size=16)),
        ('', None),
        ('How to use it', Font(bold=True, size=12)),
        ('1. "weeks": one row per week. The week column is required; everything else is optional.', None),
        ('2. Columns after "theme" in green are squads\' own themes: rename them to your squads (1s, Women...), '
         'add more, or delete them if the whole club has one theme a week.', None),
        ('3. "phases" (optional): name each phase and its weeks. Without it, the weeks\' phase column makes the '
         'phases.', None),
        ('4. "milestones" (optional): tests, trials, reviews and other dates to look out for.', None),
        ('5. Leave week_commencing blank to count on from the start date you give when you upload.', None),
        ('6. Delete the grey example rows. Save as .xlsx and upload under Season plan > Import spreadsheet. '
         'Nothing changes until you have checked the preview.', None),
        ('', None),
        ('Importing into an existing plan for the same season updates it: weeks and phases are matched on their '
         'numbers, and coaches\' notes, linked sessions and pages are kept.', None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        cell = guide.cell(row=i, column=1, value=text)
        cell.alignment = wrap
        if font:
            cell.font = font

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def weeks_csv_rows(plan=None):
    return (plan_rows(plan) if plan else _example_rows())[0]
