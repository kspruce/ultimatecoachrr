"""Season plans for any club: creating one on the website (from scratch or
a template), editing settings, squads, phases, milestones and pages, the
spreadsheet import and export, the year view with programmes linked to
phases, and the starter programmes."""
import io
from datetime import date, timedelta

import pytest

from app import db
from app.models.programme import Programme
from app.models.season import Squad
from app.models.season_plan import SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, SeasonMilestone
from app.models.session import SessionPlan
from app.models.team_settings import TeamSettings
from app.utils import season_plan_build as build
from app.utils import season_plan_sheet as sheet
from app.utils.programme_import import rows_from_xlsx
from app.utils.programme_starters import STARTERS, parsed as starter_parsed
from app.utils.season_plan_templates import TEMPLATES, template_weeks
from tests import stats_data
from tests.test_teams import make_user

MONDAY = date(2027, 10, 4)


@pytest.fixture
def club(app):
    team = stats_data.build_team('New Club', 'new-club')
    db.session.add(TeamSettings(team_id=team.id, season_plan_enabled=True))
    db.session.commit()
    return {'team': team.id, 'coach': make_user(team, 'coach', role='coach').id,
            'player': make_user(team, 'player', role='player').id}


def as_(app, club, who):
    return stats_data.Client(app, club[who], club['team'])


def plan():
    return SeasonPlan.query.filter_by(is_active=True).one()


def create(app, club, **extra):
    data = {'title': 'Club plan', 'season': '2027/28', 'start_date': '2027-10-06',
            'phase_name': ['Foundations', 'Compete', ''], 'phase_weeks': ['3', '2', ''],
            'players_see': 'on', 'joint_weekday': '1', 'joint_start': '19:00', 'joint_end': '21:00'}
    data.update(extra)
    return as_(app, club, 'coach').post('/season-plan/new', data=data)


# --------------------------------------------------------------------------
# Creating a plan
# --------------------------------------------------------------------------

def test_empty_state_offers_create_templates_and_import(app, club):
    page = as_(app, club, 'coach').get('/season-plan/').get_data(as_text=True)
    assert 'Create a plan' in page and 'Import a spreadsheet' in page
    for t in TEMPLATES:
        assert t['name'] in page
    assert as_(app, club, 'coach').get('/season-plan/new').status_code == 200
    # Players can't create one, and see nothing until there is a plan
    assert as_(app, club, 'player').get('/season-plan/').status_code == 404
    r = as_(app, club, 'player').post('/season-plan/new', data={'title': 'x'})
    assert r.status_code == 302 and SeasonPlan.query.count() == 0


def test_create_from_scratch_makes_monday_weeks_and_phases(app, club):
    r = create(app, club)
    assert r.status_code == 302
    p = plan()
    assert (p.title, p.season, p.squads, p.source) == ('Club plan', '2027/28', [], 'Created on the website')
    assert [w.week_number for w in p.weeks] == [1, 2, 3, 4, 5]
    assert p.weeks[0].week_commencing == MONDAY  # the Wednesday's week
    assert p.weeks[-1].week_commencing == MONDAY + timedelta(weeks=4)
    assert (p.start_date, p.end_date) == (MONDAY, MONDAY + timedelta(weeks=5) - timedelta(days=1))
    assert [(ph.number, ph.name, ph.start_week, ph.end_week) for ph in p.phases] == \
        [(1, 'Foundations', 1, 3), (2, 'Compete', 4, 5)]
    assert p.phases[1].start_date == MONDAY + timedelta(weeks=3)
    assert all(w.phase for w in p.weeks)
    # Players can see the overview, weeks and phases straight away
    assert p.players_see_overview and p.players_see_weeks and p.players_see_phases
    assert not p.players_see_session_notes
    assert (p.joint_weekday, p.joint_start.hour) == (1, 19)
    assert as_(app, club, 'player').get('/season-plan/').status_code == 200
    overview = as_(app, club, 'coach').get('/season-plan/').get_data(as_text=True)
    assert 'Next: give each week a theme' in overview


def test_create_checks_what_the_coach_entered(app, club):
    assert create(app, club, season='').status_code == 400
    assert create(app, club, phase_name=['A'], phase_weeks=['']).status_code == 400
    assert create(app, club, phase_name=['A'], phase_weeks=['61']).status_code == 400
    assert create(app, club, other_squads='Joint').status_code == 400
    assert SeasonPlan.query.count() == 0
    assert create(app, club).status_code == 302
    assert create(app, club).status_code == 400  # same season again
    assert SeasonPlan.query.count() == 1


def test_create_with_squads_from_the_club_and_by_name(app, club):
    db.session.add_all([Squad(team_organization_id=club['team'], name='Open', sort_order=1),
                        Squad(team_organization_id=club['team'], name='Women', sort_order=2)])
    db.session.commit()
    page = as_(app, club, 'coach').get('/season-plan/new').get_data(as_text=True)
    assert 'value="Open"' in page and 'value="Women"' in page
    create(app, club, squad=['Open', 'Women'], other_squads='Masters, open')
    assert plan().squads == ['Open', 'Women', 'Masters']
    assert [label for _, label in plan().theme_columns] == ['Joint session', 'Open', 'Women', 'Masters']


@pytest.mark.parametrize('template', TEMPLATES, ids=[t['key'] for t in TEMPLATES])
def test_templates_fill_in_phases_themes_milestones_and_pages(app, club, template):
    assert sum(p['weeks'] for p in template['phases']) == template_weeks(template)
    assert set(template['weeks']) == set(range(1, template_weeks(template) + 1))
    create(app, club, template=template['key'], other_squads='1s, 2s', phase_name=[], phase_weeks=[])
    p = plan()
    assert len(p.weeks) == template_weeks(template)
    assert [ph.name for ph in p.phases] == [ph['name'] for ph in template['phases']]
    assert all(w.joint_theme for w in p.weeks)
    assert p.milestones and all(1 <= m.start_week <= len(p.weeks) for m in p.milestones)
    assert [pg.title for pg in p.pages] == [title for title, _ in template['pages']]
    with_squads = [w for w in p.weeks if w.squad_themes]
    if any(row.get('squads') for row in template['weeks'].values()):
        assert with_squads and set(with_squads[0].squad_themes) <= {'1s', '2s'}
    assert any(w.is_event for w in p.weeks)
    # Every page renders
    coach = as_(app, club, 'coach')
    for url in ('/season-plan/', '/season-plan/weeks', '/season-plan/week/1', '/season-plan/phase/1',
                f'/season-plan/page/{p.pages[0].slug}', '/season-plan/year'):
        assert coach.get(url).status_code == 200, url


def test_a_new_plan_becomes_the_one_shown(app, club):
    create(app, club)
    first_id = plan().id
    create(app, club, season='2028/29', title='Next year', start_date='2028-10-02')
    assert plan().title == 'Next year'
    assert db.session.get(SeasonPlan, first_id).is_active is False
    coach = as_(app, club, 'coach')
    assert coach.post(f'/season-plan/plans/{first_id}/current').status_code == 302
    assert plan().id == first_id


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def test_settings_redate_extend_trim_and_rename_squads(app, club):
    create(app, club, other_squads='1s, 2s')
    p = plan()
    p.weeks[0].set_theme('1s', 'Zone O')
    p.weeks[0].set_theme('2s', 'Vert')
    p.weeks[3].joint_theme = 'Kept'
    db.session.commit()
    coach = as_(app, club, 'coach')
    assert coach.get('/season-plan/settings').status_code == 200
    r = coach.post('/season-plan/settings', data={
        'title': 'Renamed', 'season': '2027/28', 'summary': 'Short', 'start_date': '2027-11-03',
        'week_count': '7', 'squad_0': 'Firsts', 'remove_squad_1': 'on', 'new_squad': ['Masters']})
    assert r.status_code == 302
    db.session.expire_all()
    p = plan()
    assert (p.title, p.summary, p.squads) == ('Renamed', 'Short', ['Firsts', 'Masters'])
    assert p.weeks[0].squad_themes == {'Firsts': 'Zone O'}
    assert len(p.weeks) == 7 and p.weeks[0].week_commencing == date(2027, 11, 1)
    assert p.weeks[6].week_commencing == date(2027, 11, 1) + timedelta(weeks=6)
    assert p.phases[0].start_date == date(2027, 11, 1)
    # Trimming stops at a week with something in it
    coach.post('/season-plan/settings', data={'title': 'Renamed', 'season': '2027/28', 'week_count': '2'})
    db.session.expire_all()
    assert [w.week_number for w in plan().weeks] == [1, 2, 3, 4]


def test_settings_refuse_another_plans_season(app, club):
    create(app, club)
    create(app, club, season='2028/29', title='Next', start_date='2028-10-02')
    r = as_(app, club, 'coach').post('/season-plan/settings', data={'title': 'Next', 'season': '2027/28'})
    assert r.status_code == 400 and plan().season == '2028/29'


def test_deleting_a_plan_needs_the_season_typed(app, club):
    create(app, club)
    create(app, club, season='2028/29', title='Next', start_date='2028-10-02')
    coach = as_(app, club, 'coach')
    pid = plan().id
    coach.post(f'/season-plan/plans/{pid}/delete', data={'confirm': 'yes'})
    assert db.session.get(SeasonPlan, pid) is not None
    coach.post(f'/season-plan/plans/{pid}/delete', data={'confirm': '2028/29'})
    db.session.expire_all()
    assert db.session.get(SeasonPlan, pid) is None
    assert plan().season == '2027/28'  # the other plan is shown again


# --------------------------------------------------------------------------
# Phases, milestones, pages, weeks
# --------------------------------------------------------------------------

def test_phases_add_edit_overlap_and_delete(app, club):
    create(app, club, phase_name=['Only'], phase_weeks=['2'])
    coach = as_(app, club, 'coach')
    coach.post('/season-plan/settings', data={'title': 'Club plan', 'season': '2027/28', 'week_count': '5'})
    page = coach.get('/season-plan/phases').get_data(as_text=True)
    assert 'Weeks 3, 4, 5 are not in a phase' in page
    # Overlap is refused
    r = coach.post('/season-plan/phases/new', data={'name': 'Clash', 'start_week': '2', 'end_week': '4'})
    assert r.status_code == 400
    # A phase before an existing one is numbered first
    coach.post('/season-plan/phases/1/edit', data={'name': 'Only', 'start_week': '4', 'end_week': '5'})
    r = coach.post('/season-plan/phases/new', data={'name': 'Early', 'start_week': '1', 'end_week': '3',
                                                    'aim': 'Basics', 'colour': '#123456'})
    assert r.status_code == 302
    db.session.expire_all()
    p = plan()
    assert [(ph.number, ph.name, ph.start_week) for ph in p.phases] == [(1, 'Early', 1), (2, 'Only', 4)]
    assert p.phases[0].aim == 'Basics' and p.phases[0].colour == '#123456'
    assert p.weeks[0].phase.name == 'Early' and p.weeks[4].phase.name == 'Only'
    coach.post('/season-plan/phases/1/delete')
    db.session.expire_all()
    p = plan()
    assert [ph.name for ph in p.phases] == ['Only'] and p.phases[0].number == 1
    assert p.weeks[0].phase is None and len(p.weeks) == 5


def test_milestones_are_saved_in_week_order(app, club):
    create(app, club)
    coach = as_(app, club, 'coach')
    assert coach.get('/season-plan/milestones').status_code == 200
    r = coach.post('/season-plan/milestones', data={
        'what': ['Retest', 'Baseline', '', 'Social'], 'start_week': ['5', '1', '', ''],
        'end_week': ['', '2', '', ''], 'when': ['', '', '', 'After every event']})
    assert r.status_code == 302
    rows = [(m.when_label, m.what, m.start_week, m.end_week) for m in plan().milestones]
    assert rows == [('Weeks 1-2', 'Baseline', 1, 2), ('Week 5', 'Retest', 5, 5),
                    ('After every event', 'Social', None, None)]
    # Remove one; a week outside the plan is refused
    coach.post('/season-plan/milestones', data={'what': ['Baseline', 'Retest'], 'start_week': ['1', '5'],
                                                'end_week': ['', ''], 'when': ['', ''], 'remove': ['1']})
    assert [m.what for m in plan().milestones] == ['Baseline']
    assert coach.post('/season-plan/milestones', data={'what': ['X'], 'start_week': ['9']}).status_code == 400


def test_pages_add_edit_move_and_delete(app, club):
    create(app, club)
    coach = as_(app, club, 'coach')
    coach.post('/season-plan/pages/new', data={'title': 'How we train', 'body_markdown': '# Hi',
                                               'players_can_view': 'on'})
    coach.post('/season-plan/pages/new', data={'title': 'How we train', 'body_markdown': 'Coaches'})
    pages = plan().pages
    assert [p.slug for p in pages] == ['how-we-train', 'how-we-train-2']
    assert pages[0].players_can_view and not pages[1].players_can_view
    assert as_(app, club, 'player').get('/season-plan/page/how-we-train').status_code == 200
    assert as_(app, club, 'player').get('/season-plan/page/how-we-train-2').status_code == 404
    coach.post('/season-plan/page/how-we-train-2/move', data={'direction': 'up'})
    db.session.expire_all()
    assert [p.slug for p in plan().pages] == ['how-we-train-2', 'how-we-train']
    coach.post('/season-plan/page/how-we-train-2/edit', data={'title': 'Captains', 'body_markdown': 'x'})
    db.session.expire_all()
    assert plan().pages[0].title == 'Captains'
    coach.post('/season-plan/page/how-we-train/delete')
    assert [p.title for p in plan().pages] == ['Captains']


def test_week_edit_has_a_field_per_squad(app, club):
    create(app, club, other_squads='Open, Women')
    coach = as_(app, club, 'coach')
    page = coach.get('/season-plan/week/1/edit').get_data(as_text=True)
    assert 'Open theme' in page and 'Women theme' in page
    coach.post('/season-plan/week/1/edit', data={'theme_0': 'Throwing', 'theme_1': 'Ho stack', 'theme_2': ''})
    week = SeasonWeek.query.filter_by(week_number=1).one()
    assert (week.joint_theme, week.squad_themes) == ('Throwing', {'Open': 'Ho stack'})
    weeks = coach.get('/season-plan/weeks?squad=Women').get_data(as_text=True)
    assert 'Throwing' in weeks and 'Ho stack' not in weeks
    assert 'Ho stack' in coach.get('/season-plan/weeks').get_data(as_text=True)


def test_one_theme_a_week_without_squads(app, club):
    create(app, club)
    coach = as_(app, club, 'coach')
    coach.post('/season-plan/week/1/edit', data={'theme_0': 'Catching'})
    assert plan().theme_columns == [('joint', 'Theme')]
    page = coach.get('/season-plan/week/1').get_data(as_text=True)
    assert 'Catching' in page and 'Joint session' not in page


def test_players_see_nothing_prompt(app, club):
    create(app, club, players_see='')
    page = as_(app, club, 'coach').get('/season-plan/').get_data(as_text=True)
    assert "Players can't see any of this plan yet" in page
    assert as_(app, club, 'player').get('/season-plan/').status_code == 404


def test_session_building_uses_the_plans_squads(app, club):
    create(app, club, other_squads='Open, Women')
    week = plan().weeks[0]
    week.session_detail_md = ('**Split session**\n\n| Time | Open group | Women group (suggested) | Source |\n'
                              '| --- | --- | --- | --- |\n| 19:00 | Zone O | Same, with a stall of 7 | |\n'
                              '| 19:30 | Scrimmage | Scrimmage | |\n')
    db.session.commit()
    from app.utils.season_sessions import build_sessions, week_sessions
    report = build_sessions(plan())
    assert report.count('created') == 2
    sessions = week_sessions(plan(), plan().weeks[0])
    assert [s.external_id[-5:] for s in sessions] == ['-open', 'women']
    assert sessions[0].squad is None  # not one of the sessions page's joint / 1s / 2s labels
    women = sessions[1].components.all()
    assert women[0].title == 'Zone O' and 'Women: with a stall of 7' in women[0].description


# --------------------------------------------------------------------------
# Spreadsheet import and export
# --------------------------------------------------------------------------

def _csv(rows):
    return '\n'.join(','.join(str(c) for c in r) for r in rows)


def test_sheet_parser_reads_weeks_squads_phases_and_dates():
    weeks = [['Week', 'w/c', 'Phase', 'Block', 'Event', 'Theme', 'Open', 'Women', 'Off pitch'],
             ['1', '', 'Basics', 'Throwing', '', 'Grip', 'Ho', 'Vert', 'Tests'],
             ['2', '', 'Basics', '', '', 'Catching', '', 'Dump', ''],
             ['3', '18/10/2027', 'Compete', 'Tour 1', 'yes', 'Light', '', '', '']]
    data = sheet.parse_sheets(weeks, season='2027', title='T')
    assert data['errors'] == []
    assert data['plan']['squad_names'] == ['Open', 'Women']
    assert [w['week_commencing'] for w in data['weeks']] == [date(2027, 10, 4), date(2027, 10, 11),
                                                              date(2027, 10, 18)]
    assert data['weeks'][0]['squad_themes'] == {'Open': 'Ho', 'Women': 'Vert'}
    assert data['weeks'][1]['squad_themes'] == {'Women': 'Dump'}
    assert data['weeks'][2]['is_event'] and data['weeks'][0]['off_pitch'] == 'Tests'
    assert [(p['number'], p['name'], p['start_week'], p['end_week']) for p in data['phases']] == \
        [(1, 'Basics', 1, 2), (2, 'Compete', 3, 3)]


def test_sheet_parser_reports_problems_by_row():
    weeks = [['week', 'week_commencing', 'theme'], ['1', 'someday', 'A'], ['1', '', 'B'], ['x', '', 'C']]
    errors = sheet.parse_sheets(weeks, season='2027')['errors']
    assert any('weeks row 2' in e and 'date' in e for e in errors)
    assert any('weeks row 3' in e and 'already' in e for e in errors)
    assert any('weeks row 4' in e for e in errors)
    no_dates = sheet.parse_sheets([['week', 'theme'], ['1', 'A']], season='2027')['errors']
    assert any('start date' in e for e in no_dates)
    overlap = sheet.parse_sheets([['week', 'theme'], ['1', 'A'], ['2', 'B']],
                                 [['phase', 'name', 'start_week', 'end_week'], ['1', 'A', '1', '2'],
                                  ['2', 'B', '2', '2']], start=MONDAY, season='2027')['errors']
    assert any('overlap' in e for e in overlap)


def test_import_csv_preview_then_create(app, club):
    coach = as_(app, club, 'coach')
    assert coach.get('/season-plan/import').status_code == 200
    weeks = _csv([['week', 'theme', '1s', '2s'], ['1', 'Throw', 'Zone', 'Vert'], ['2', 'Catch', '', '']])
    r = coach.post('/season-plan/import', data={
        'file': (io.BytesIO(weeks.encode()), 'plan.csv'), 'season': '2027/28', 'start_date': '2027-10-04'},
        content_type='multipart/form-data')
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and '2 weeks' in page and SeasonPlan.query.count() == 0
    r = coach.post('/season-plan/import', data={'weeks_csv': weeks, 'season': '2027/28', 'start_date': '2027-10-04',
                                                'title': 'From a sheet', 'confirm': '1', 'players_see': 'on'})
    assert r.status_code == 302
    p = plan()
    assert (p.title, p.squads, len(p.weeks), p.players_see_weeks) == ('From a sheet', ['1s', '2s'], 2, True)
    assert p.weeks[0].squad_themes == {'1s': 'Zone', '2s': 'Vert'}


def test_export_and_reimport_round_trip_keeps_notes_and_pages(app, club):
    create(app, club, template='season-16', other_squads='1s, 2s', phase_name=[], phase_weeks=[])
    p = plan()
    p.weeks[0].notes = 'Bring cones'
    p.weeks[0].squad_themes = {'1s': 'Ho stack'}
    p.phases[0].aim = 'Basics'
    db.session.commit()
    coach = as_(app, club, 'coach')
    r = coach.get('/season-plan/export.xlsx')
    assert r.status_code == 200 and r.mimetype.endswith('sheet')
    sheets = rows_from_xlsx(r.data)
    assert {'instructions', 'weeks', 'phases', 'milestones'} <= set(sheets)
    weeks = sheets['weeks']
    assert weeks[0][:7] == sheet.WEEK_COLUMNS[:7] and weeks[0][7:9] == ['1s', '2s']
    edited = _edited_workbook(r.data)
    upload = coach.post('/season-plan/import', data={'file': (io.BytesIO(edited), 'p.xlsx'), 'season': '2027/28'},
                        content_type='multipart/form-data')
    assert upload.status_code == 200 and 'Updates' in upload.get_data(as_text=True)
    assert plan().weeks[1].joint_theme != 'Changed in the sheet'  # nothing saved by the preview
    r = coach.post('/season-plan/import', data={'file': (io.BytesIO(edited), 'p.xlsx'), 'season': '2027/28',
                                                'confirm': '1'}, content_type='multipart/form-data')
    assert r.status_code == 302
    db.session.expire_all()
    p = plan()
    assert SeasonPlan.query.count() == 1
    assert p.weeks[1].joint_theme == 'Changed in the sheet'
    assert p.weeks[0].notes == 'Bring cones' and p.weeks[0].squad_themes == {'1s': 'Ho stack'}
    assert p.phases[0].aim == 'Basics' and len(p.milestones) == 4
    assert [pg.title for pg in p.pages] == ['How we train', 'Measuring improvement']  # kept


def _edited_workbook(data):
    """The export with week 2's theme (column G) changed."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data))
    wb['weeks']['G3'] = 'Changed in the sheet'
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_template_downloads(app, club):
    coach = as_(app, club, 'coach')
    sheets = rows_from_xlsx(coach.get('/season-plan/import/template.xlsx').data)
    data = sheet.parse_sheets(sheets['weeks'], sheets['phases'], sheets['milestones'], season='2027')
    assert data['errors'] == [] and len(data['weeks']) == 3 and data['plan']['squad_names'] == ['1s', '2s']
    assert 'week,week_commencing' in coach.get('/season-plan/import/template-weeks.csv').get_data(as_text=True)


# --------------------------------------------------------------------------
# The year, programmes and starters
# --------------------------------------------------------------------------

def _starter_programme(app, club, key='off-season-10', start='2027-10-04'):
    coach = as_(app, club, 'coach')
    r = coach.post(f'/programmes/starters/{key}', data={'start_date': start})
    assert r.status_code == 302
    return Programme.query.filter_by(team_organization_id=club['team']).order_by(Programme.id.desc()).first()


@pytest.mark.parametrize('starter', STARTERS, ids=[s['key'] for s in STARTERS])
def test_starter_programmes_parse_cleanly(app, starter):
    parsed, _ = starter_parsed(starter)
    assert parsed['errors'] == [] and parsed['warnings'] == []
    assert parsed['counts']['sessions'] > 0


def test_starter_is_added_as_a_draft_with_its_start_date(app, club):
    page = as_(app, club, 'coach').get('/programmes/').get_data(as_text=True)
    assert 'Starter templates' in page and STARTERS[0]['name'] in page
    programme = _starter_programme(app, club)
    assert programme.draft and not programme.published and programme.start_date == MONDAY
    assert programme.source_kind == 'template'
    again = _starter_programme(app, club)
    assert again.name.endswith('(2)')


def test_year_view_and_programme_sessions_on_each_week(app, club):
    from app.utils import programmes as svc
    create(app, club)
    programme = _starter_programme(app, club)
    svc.publish(programme, None)
    db.session.commit()
    coach = as_(app, club, 'coach')
    year = coach.get('/season-plan/year').get_data(as_text=True)
    assert programme.name in year and 'Not linked to a phase' in year
    r = coach.post('/season-plan/phases/1/edit', data={'name': 'Foundations', 'start_week': '1', 'end_week': '3',
                                                       'programme_id': str(programme.id)})
    assert r.status_code == 302
    assert db.session.get(SeasonPhase, plan().phases[0].id).programme_id == programme.id
    week = coach.get('/season-plan/week/1').get_data(as_text=True)
    assert programme.name in week and 'Strength A' in week and 'Speed &amp; agility' in week
    # A week in a phase without a programme shows none
    assert 'Strength A' not in coach.get('/season-plan/week/4').get_data(as_text=True)
    # Players who can see the week see the programme's sessions too
    assert 'Strength A' in as_(app, club, 'player').get('/season-plan/week/1').get_data(as_text=True)
    # Another club's programme can't be linked
    other = stats_data.build_team('Other', 'other')
    foreign = Programme(team_organization_id=other.id, name='Theirs')
    db.session.add(foreign)
    db.session.commit()
    coach.post('/season-plan/phases/1/edit', data={'name': 'Foundations', 'start_week': '1', 'end_week': '3',
                                                   'programme_id': str(foreign.id)})
    assert db.session.get(SeasonPhase, plan().phases[0].id).programme_id is None


def test_year_without_a_plan_goes_to_the_start_page(app, club):
    r = as_(app, club, 'coach').get('/season-plan/year')
    assert r.status_code == 302 and r.headers['Location'].endswith('/season-plan/')


def test_edit_pages_are_for_coaches_only(app, club):
    create(app, club)
    player = as_(app, club, 'player')
    for url in ('/season-plan/settings', '/season-plan/phases', '/season-plan/phases/new', '/season-plan/milestones',
                '/season-plan/pages', '/season-plan/import', '/season-plan/export.xlsx', '/season-plan/year'):
        r = player.get(url)
        assert r.status_code == 302 and '/season-plan' not in r.headers['Location'], url


def test_build_helpers_directly(app, club):
    with pytest.raises(build.PlanError):
        build.clean_squads(['x' * 51])
    assert build.clean_squads([' 1s ', '1S', '', '2s']) == ['1s', '2s']
    create(app, club)
    p = plan()
    p.weeks[-1].off_pitch = 'Something'
    db.session.commit()
    assert build.set_week_count(p, 3) == [5]
    assert len(p.weeks) == 5
    assert build.week_label(2, 4) == 'Weeks 2-4' and build.week_label(3) == 'Week 3'
    assert SeasonPage.query.count() == 0 and SeasonMilestone.query.count() == 0
    assert SessionPlan.query.count() == 0
