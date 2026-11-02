"""The blank programme spreadsheet a club downloads, fills in and imports.

An Excel workbook with an Instructions sheet, then the "programme" and
"tests" sheets the importer reads (programme_import.parse). The data sheets
have frozen, labelled headers, a note on every column, example rows and
dropdowns for the columns with fixed values, so most mistakes are caught in
Excel before the file is uploaded. The same example rows are used for the
CSV templates.
"""
import io

from app.models.programme import AGGREGATIONS, LOG_FIELDS, MEASUREMENTS, REQUIREMENTS, SESSION_TYPES, WEEK_KINDS
from app.utils.programme_import import PROGRAMME_COLUMNS, REQUIRED_COLUMNS, TEST_COLUMNS, TEST_REQUIRED


def _keys(choices):
    return [k for k, _ in choices]


LOG_FIELD_KEYS = _keys(LOG_FIELDS)

# Column: (what to put in it, example). Mirrors docs/PROGRAMME_IMPORT.md.
PROGRAMME_HELP = {
    'track': ('Track name. Tracks run side by side, each with its own weeks.', 'Speed'),
    'track_first_week': ('Number of the track\'s first week: 1, or 0 for Week 0, 1, 2... Defaults to the lowest week.', '1'),
    'track_start_offset': ('Weeks after the programme starts that this track begins. Default 0.', '0'),
    'week': ('Week number within the track. Every week from the first to the last needs at least one row.', '1'),
    'week_title': ('Title of the week.', 'Acceleration fundamentals'),
    'week_type': ('training (default), deload or rest. Rest weeks have nothing to log.', 'rest'),
    'week_objective': ('What the week is for.', 'Learn the drive phase'),
    'week_skills': ('Supporting skills or key cues for the week.', 'Arm drive'),
    'session': ('Session title. Rows with the same title in the same week are one session. Not needed on a rest-week row.', 'Sprint day'),
    'session_type': ('Pick from the list, or type your own word (kept as a custom type, e.g. Plyometrics).', 'sprint'),
    'requirement': ('required (default), optional, or alternative (do any one of a group).', 'required'),
    'alternative_group': ('For alternatives: sessions in the same week with the same group name; doing one counts.', 'hills'),
    'session_minutes': ('How long the session takes, in whole minutes.', '45'),
    'session_focus': ('Focus and instructions for the session.', 'Quality over quantity'),
    'warmup': ('Warm-up.', '10 min dynamic warm-up'),
    'cooldown': ('Cool-down.', '5 min walk and stretch'),
    'coaching_cues': ('Coaching cues.', 'Lean, drive the arms'),
    'session_video': ('A web link (http:// or https://) to a video for the session.', 'https://youtu.be/...'),
    'log_fields': ('What players record, separated by commas: ' + ', '.join(LOG_FIELD_KEYS)
                   + '. Notes and done/partly/skipped are always offered.', 'duration_minutes, rpe'),
    'exercise': ('Exercise or drill name. Leave blank for a session with no exercises. Everything to the right needs it.', '10 m sprints'),
    'block': ('Block or label.', 'A1'),
    'sets': ('Sets. Text, so 3, 3-4 or AMRAP all work.', '15'),
    'reps': ('Reps. Text, so 8, 6-8 per leg or AMRAP all work.', '6-8 per leg'),
    'distance_m': ('Distance in metres (a number).', '10'),
    'duration_s': ('Duration in seconds (a whole number).', '120'),
    'rest': ('Rest between sets or reps.', 'Walk back'),
    'intensity': ('Intensity.', 'RPE 7'),
    'tempo': ('Tempo.', '3-1-X'),
    'instructions': ('Instructions and cues for the exercise.', 'Stay low'),
    'exercise_video': ('A web link (http:// or https://) to a video for the exercise.', 'https://youtu.be/...'),
}
TEST_HELP = {
    'test': ('Name of the test. Each name once.', '10 m sprint'),
    'unit': ('Unit results are recorded in.', 's'),
    'measurement': ('time, distance, count, score or other (default).', 'time'),
    'attempts': ('How many attempts each player records. Default 1.', '3'),
    'aggregation': ('Which attempt counts: best (default), mean or last.', 'best'),
    'better': ('lower (e.g. sprint times) or higher (e.g. jump distances).', 'lower'),
    'min': ('Lowest believable result; anything below is refused.', '1'),
    'max': ('Highest believable result; anything above is refused.', '4'),
    'description': ('What the test is.', 'Standing start'),
    'instructions': ('How to run it.', 'Best of three, 3 min rest'),
    'milestone_track': ('The track whose week numbers baseline_week and retest_weeks use.', 'Speed'),
    'baseline_week': ('Week of the baseline test.', '1'),
    'retest_weeks': ('Weeks of the retests, separated by commas.', '6, 12'),
}

# Fixed values offered as a dropdown. Session types also take any other word.
PROGRAMME_LISTS = {
    'week_type': _keys(WEEK_KINDS),
    'session_type': _keys(SESSION_TYPES),
    'requirement': _keys(REQUIREMENTS),
}
OPEN_LISTS = {'session_type'}
TEST_LISTS = {
    'measurement': _keys(MEASUREMENTS),
    'aggregation': _keys(AGGREGATIONS),
    'better': ['lower', 'higher'],
}
WHOLE_NUMBERS = {'track_first_week': 0, 'track_start_offset': 0, 'week': 0, 'session_minutes': 0, 'duration_s': 0,
                 'attempts': 1, 'baseline_week': 0}
DECIMALS = {'distance_m'}
NUMBER_COLUMNS = set(WHOLE_NUMBERS) | DECIMALS | {'min', 'max'}


def _row(columns, **cells):
    return [cells.get(c, '') for c in columns]


def _p(**cells):
    return _row(PROGRAMME_COLUMNS, **cells)


EXAMPLE_PROGRAMME = [
    _p(track='Speed', track_first_week='1', track_start_offset='0', week='1', week_title='Acceleration',
       week_objective='Learn the drive phase', week_skills='Arm drive', session='Sprint day', session_type='sprint',
       requirement='required', session_minutes='45', warmup='10 min dynamic warm-up',
       coaching_cues='Lean, drive the arms', log_fields='duration_minutes, rpe', exercise='10 m sprints', sets='15',
       distance_m='10', rest='Walk back', intensity='Max', instructions='Stay low'),
    _p(exercise='20 m sprints', sets='10', distance_m='20', rest='Walk back', intensity='Max'),
    _p(week='2', week_title='Rest week', week_type='rest'),
    _p(track='Conditioning', track_first_week='0', track_start_offset='0', week='0', week_title='Intervals',
       session='Intervals', session_type='conditioning', requirement='required', session_minutes='30',
       log_fields='duration_minutes, rpe, distance_m', exercise='ON interval', sets='4', duration_s='120',
       rest='2 min active recovery', intensity='Hard but steady'),
    _p(week='1', week_title='Hills', session='Hill sprints', session_type='conditioning', requirement='alternative',
       alternative_group='hills', exercise='Hill sprint', sets='7', duration_s='20', rest='Walk down'),
    _p(session='Deadmill', session_type='conditioning', requirement='alternative', alternative_group='hills',
       exercise='Deadmill push', sets='7', duration_s='25'),
]
EXAMPLE_TESTS = [
    _row(TEST_COLUMNS, test='10 m sprint', unit='s', measurement='time', attempts='3', aggregation='best',
         better='lower', min='1', max='4', description='Standing start', milestone_track='Speed', baseline_week='1',
         retest_weeks='2'),
]

DATA_ROWS = 2000  # rows the dropdowns and number checks cover


def _cell_value(column, value):
    """Numbers as numbers, so Excel doesn't flag them as text."""
    if column in NUMBER_COLUMNS and value:
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if number.is_integer() else number
    return value


def workbook_bytes():
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    header_fill = PatternFill('solid', fgColor='1F3A5F')
    required_fill = PatternFill('solid', fgColor='B23A48')
    example_font = Font(color='5B6B7F', italic=True)
    wrap = Alignment(wrap_text=True, vertical='top')

    wb = Workbook()
    guide = wb.active
    guide.title = 'Instructions'

    def data_sheet(title, columns, required, helps, lists, examples):
        ws = wb.create_sheet(title)
        ws.append(columns)
        for i, column in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=i)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = required_fill if column in required else header_fill
            text, example = helps[column]
            cell.comment = Comment(f'{"Required. " if column in required else ""}{text}\nExample: {example}',
                                   'Ultimate Coach', width=280, height=120)
            width = max(len(column) + 4, 12)
            if column in ('instructions', 'session_focus', 'week_objective', 'coaching_cues', 'description', 'warmup'):
                width = 28
            ws.column_dimensions[get_column_letter(i)].width = width
        for row in examples:
            ws.append([_cell_value(c, v) for c, v in zip(columns, row)])
            for i in range(1, len(columns) + 1):
                ws.cell(row=ws.max_row, column=i).font = example_font
        ws.freeze_panes = 'B2'
        last = DATA_ROWS + 1

        def rng(column):
            letter = get_column_letter(columns.index(column) + 1)
            return f'{letter}2:{letter}{last}'

        for column, values in lists.items():
            dv = DataValidation(type='list', formula1='"' + ','.join(values) + '"', allow_blank=True,
                                showDropDown=False)
            dv.promptTitle = column
            dv.prompt = helps[column][0][:255]
            dv.showInputMessage = True
            if column in OPEN_LISTS:
                dv.showErrorMessage = False
            else:
                dv.showErrorMessage = True
                dv.errorTitle = f'Not a {column}'
                dv.error = 'Pick one of: ' + ', '.join(values)
            dv.add(rng(column))
            ws.add_data_validation(dv)
        for column in columns:
            if column in WHOLE_NUMBERS:
                dv = DataValidation(type='whole', operator='greaterThanOrEqual', formula1=str(WHOLE_NUMBERS[column]),
                                    allow_blank=True)
                dv.errorTitle, dv.error = 'Whole number', f'{column} is a whole number of at least {WHOLE_NUMBERS[column]}.'
            elif column in DECIMALS:
                dv = DataValidation(type='decimal', operator='greaterThanOrEqual', formula1='0', allow_blank=True)
                dv.errorTitle, dv.error = 'Number', f'{column} is a number of metres (0 or more).'
            elif column in ('min', 'max'):
                dv = DataValidation(type='decimal', operator='between', formula1='-1000000', formula2='1000000',
                                    allow_blank=True)
                dv.errorTitle, dv.error = 'Number', f'{column} is a number.'
            else:
                continue
            dv.showErrorMessage = True
            dv.add(rng(column))
            ws.add_data_validation(dv)
        return ws

    data_sheet('programme', PROGRAMME_COLUMNS, REQUIRED_COLUMNS, PROGRAMME_HELP, PROGRAMME_LISTS, EXAMPLE_PROGRAMME)
    data_sheet('tests', TEST_COLUMNS, TEST_REQUIRED, TEST_HELP, TEST_LISTS, EXAMPLE_TESTS)

    # The Instructions sheet
    guide.column_dimensions['A'].width = 22
    guide.column_dimensions['B'].width = 11
    guide.column_dimensions['C'].width = 70
    guide.column_dimensions['D'].width = 26
    guide.sheet_view.showGridLines = False
    guide.sheet_properties.pageSetUpPr.fitToPage = True  # prints one page wide
    guide.page_setup.fitToWidth, guide.page_setup.fitToHeight = 1, 0
    guide['A1'] = 'Training programme template'
    guide['A1'].font = Font(bold=True, size=16)
    steps = [
        'How to use it',
        '1. Fill in the "programme" sheet: one row per exercise (or per session with no exercises, or per rest week).',
        '2. Optionally fill in the "tests" sheet: one row per performance test, with its baseline and retest weeks.',
        '3. Delete the grey example rows, or type over them.',
        '4. Save as .xlsx and upload it under Programmes > Import spreadsheet. Nothing is created until you have '
        'checked the preview, and any problems are listed with their row number.',
        '',
        'Tips',
        '• Blank track, week and session cells carry on from the row above, so list a session\'s exercises '
        'underneath it without repeating everything.',
        '• Week and session details (title, type, objective...) can go on any one of their rows.',
        '• Red headers are required. Hover over a header to see what it is for.',
        '• Columns with fixed values have a dropdown. session_type also takes your own word, e.g. Plyometrics.',
        '• Keep the sheet names "programme" and "tests" and the header row as they are. You can rename the file.',
    ]
    row = 3
    for line in steps:
        guide.cell(row=row, column=1, value=line)
        guide.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        guide.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical='top')
        if line in ('How to use it', 'Tips'):
            guide.cell(row=row, column=1).font = Font(bold=True, size=12)
        elif len(line) > 110:
            guide.row_dimensions[row].height = 30
        row += 1

    def column_table(title, columns, required, helps, lists):
        nonlocal row
        row += 1
        guide.cell(row=row, column=1, value=title).font = Font(bold=True, size=12)
        row += 1
        for i, head in enumerate(('Column', 'Required', 'What to put in it', 'Example'), start=1):
            cell = guide.cell(row=row, column=i, value=head)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = header_fill
        row += 1
        for column in columns:
            text, example = helps[column]
            if column in lists and column not in OPEN_LISTS:
                text += ' (dropdown)'
            guide.cell(row=row, column=1, value=column).font = Font(bold=True)
            guide.cell(row=row, column=2, value='yes' if column in required else '')
            guide.cell(row=row, column=3, value=text)
            guide.cell(row=row, column=4, value=example)
            for i in range(1, 5):
                guide.cell(row=row, column=i).alignment = wrap
            if len(text) > 75:
                guide.row_dimensions[row].height = 30 if len(text) < 150 else 45
            row += 1

    column_table('The programme sheet', PROGRAMME_COLUMNS, REQUIRED_COLUMNS, PROGRAMME_HELP, PROGRAMME_LISTS)
    column_table('The tests sheet', TEST_COLUMNS, TEST_REQUIRED, TEST_HELP, TEST_LISTS)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
