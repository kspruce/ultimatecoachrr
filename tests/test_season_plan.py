"""Season plan: the off-by-default toggle, the markdown table parser (run on
the real 2027/28 export), the import command and who can see what."""
import json
import os
import shutil
from datetime import date

import pytest

from app import db
from app.models.season_plan import SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, SeasonMilestone
from app.models.session import SessionPlan
from app.models.team_settings import TeamSettings
from app.utils.season_plan_import import (
    import_season_plan, load_export, parse_export, parse_tables, clean_cell, split_week_sections,
)
from tests import stats_data
from tests.test_teams import make_user

EXPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'imports', 'season-plan-export')
needs_export = pytest.mark.skipif(not os.path.isdir(EXPORT), reason='season plan export not present')

# Any page with the site nav (the home page may redirect to onboarding)
NAV_PAGE = '/team/'

MODELS = (SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, SeasonMilestone)


def counts():
    return [m.query.count() for m in MODELS]


@pytest.fixture
def herd(app):
    team = stats_data.build_team('Herd 2028', 'herd-2028')
    db.session.add(TeamSettings(team_id=team.id))
    db.session.commit()
    return {
        'team': team.id,
        'coach': make_user(team, 'coach', role='coach').id,
        'captain': make_user(team, 'captain', role='captain').id,
        'player': make_user(team, 'player', role='player').id,
    }


def enable(team_id, on=True):
    TeamSettings.query.filter_by(team_id=team_id).one().season_plan_enabled = on
    db.session.commit()


def do_import(team_id, **kw):
    from app.models.team_organization import TeamOrganization
    return import_season_plan(EXPORT, db.session.get(TeamOrganization, team_id), **kw)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def test_clean_cell_and_tables_tolerate_blanks_dashes_and_short_rows():
    assert clean_cell('') is None and clean_cell(' - ') is None and clean_cell('—') is None
    assert clean_cell('Solent (\\~7 Mar)') == 'Solent (~7 Mar)'
    tables = parse_tables('| Wk | Joint | 1s |\n| --- | --- | --- |\n| 1 | Throwing |\n| 2 | — |  |\n')
    assert tables[0]['header'] == ['wk', 'joint', '1s']
    assert tables[0]['rows'] == [['1', 'Throwing'], ['2', '—', '']]


def test_split_week_sections_stops_at_the_next_level_two_heading():
    md = ('# Phase\n\n## How it works\nintro\n\n## Week 3 · 18 Oct · Catching\nbody 3\n### Sub\nmore\n\n'
          '## Week 4 · 25 Oct · Cutting\nbody 4\n\n## Phase review\nreview')
    sections = split_week_sections(md)
    assert sections[3] == ('Catching', 'body 3\n### Sub\nmore')
    assert sections[4] == ('Cutting', 'body 4')


@needs_export
def test_parser_reads_the_real_export():
    data = parse_export(*load_export(EXPORT))
    assert data['skipped'] == [] and data['warnings'] == []
    assert data['plan']['season'] == '2027/28'
    assert data['plan']['start_date'] == date(2027, 10, 4)

    phases = {p['number']: p for p in data['phases']}
    assert sorted(phases) == [1, 2, 3, 4, 5]
    assert phases[1]['name'] == 'Foundations'
    assert (phases[1]['start_date'], phases[1]['end_date']) == (date(2027, 10, 4), date(2027, 12, 19))
    # "20 Mar - 18 Jun" has no year: it follows on from phase 2 in 2028
    assert (phases[3]['start_date'], phases[3]['end_date']) == (date(2028, 3, 20), date(2028, 6, 18))
    assert (phases[3]['start_week'], phases[3]['end_week']) == (25, 37)
    assert phases[2]['classroom_refs'] == 'C4, C5'
    assert phases[1]['strategic_anchor'] == 'Resets: dump and swing'
    assert phases[4]['progression']['2s defence'] == 'Arrowhead in full'

    weeks = {w['week_number']: w for w in data['weeks']}
    assert len(weeks) == 51 and sorted(weeks) == list(range(1, 52))
    # The unnumbered Christmas row becomes weeks 12 and 13
    assert weeks[12]['is_break'] and weeks[13]['is_break']
    assert weeks[12]['week_commencing'] == date(2027, 12, 20)
    assert weeks[13]['week_commencing'] == date(2027, 12, 27)
    assert weeks[12]['phase_number'] is None and weeks[12]['firsts_theme'] is None
    # Year rolls over in January
    assert weeks[14]['week_commencing'] == date(2028, 1, 3)
    assert weeks[51]['week_commencing'] == date(2028, 9, 18)
    # Escapes, dash cells and joint-only weeks
    assert weeks[26]['block'] == 'UKU Tour 1 (~28 Mar)'
    assert weeks[48]['seconds_theme'] is None and weeks[48]['joint_theme'] == 'Light: throwing, set pieces'
    assert weeks[50]['joint_theme'] is None
    assert weeks[3]['classroom'] == 'C1 How we learn (online)'
    assert weeks[1]['off_pitch'] == 'Baseline benchmarks'
    # Events, and training blocks that mention one aren't flagged
    events = {n for n, w in weeks.items() if w['is_event']}
    assert {11, 18, 19, 20, 23, 26, 29, 30, 31, 37, 42, 43, 49} == events
    # Session notes from the phase tabs
    assert weeks[1]['session_title'] == 'Welcome, baseline tests, grip and pivot'
    assert weeks[1]['session_detail_md'].startswith('**Learning points:**')
    assert '## Week 2' not in weeks[1]['session_detail_md']
    assert 'Phase 1 review' not in weeks[11]['session_detail_md']
    assert data['notes_count'] == 49 and weeks[12]['session_detail_md'] is None

    assert [p['slug'] for p in data['pages']][:3] == ['season-plan', 'season-at-a-glance', 'weekly-plan']
    assert len(data['pages']) == 11
    ms = data['milestones']
    assert len(ms) == 9
    assert (ms[2]['when_label'], ms[2]['start_week'], ms[2]['end_week']) == ('Weeks 18-20', 18, 20)
    assert ms[7]['start_week'] is None  # "After every event"


def test_unparseable_rows_are_reported_not_fatal(tmp_path):
    (tmp_path / 'tabs').mkdir()
    (tmp_path / 'tabs' / 'a.md').write_text(
        '# Plan\n\nIntro.\n\n'
        '| Phase | Dates | Weeks | Aim |\n| --- | --- | --- | --- |\n'
        '| 1. One | 4 Oct - 12 Oct 2027 | 1-2 | Aim |\n| Bogus | | | |\n\n'
        '| Wk | w/c | Ph | Block | Joint |\n| --- | --- | --- | --- | --- |\n'
        '| 1 | 4 Oct | 1 | A | Throw |\n| ? | | | Huh | |\n| 2 | someday | 1 | A | Catch |\n')
    (tmp_path / 'manifest.json').write_text(json.dumps(
        {'plan': 'Test 2027/28', 'tabs': [{'order': 1, 'title': 'A', 'slug': 'a', 'file': 'tabs/a.md'}]}))
    data = parse_export(*load_export(str(tmp_path)))
    assert [w['week_number'] for w in data['weeks']] == [1]
    assert len(data['skipped']) == 3
    assert data['weeks'][0]['firsts_theme'] is None


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

@needs_export
def test_dry_run_writes_nothing(app, herd):
    report = do_import(herd['team'], dry_run=True)
    assert counts() == [0, 0, 0, 0, 0]
    assert report.counts == {'phases': 5, 'weeks': 51, 'session notes': 49, 'pages': 11, 'milestones': 9,
                             'classroom sessions': 12}
    assert 'DRY RUN' in report.text()


@needs_export
def test_dry_run_from_the_command_line(app, herd):
    result = app.test_cli_runner().invoke(
        args=['import-season-plan', EXPORT, '--team', 'herd-2028', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert 'DRY RUN' in result.output and 'weeks: 51' in result.output
    assert counts() == [0, 0, 0, 0, 0]


@needs_export
def test_dry_run_on_an_existing_plan_changes_nothing(app, herd):
    do_import(herd['team'])
    week = SeasonWeek.query.filter_by(week_number=5).one()
    week.joint_theme = 'Edited'
    db.session.commit()
    do_import(herd['team'], dry_run=True)
    db.session.expire_all()
    assert SeasonWeek.query.filter_by(week_number=5).one().joint_theme == 'Edited'


@needs_export
def test_import_is_idempotent_and_keeps_links_and_access(app, herd):
    first = do_import(herd['team'])
    assert first.plan_created and counts() == [1, 5, 51, 11, 9]
    plan = SeasonPlan.query.one()
    assert plan.season == '2027/28' and plan.team_organization_id == herd['team']
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().season_plan_enabled is False

    sp = SessionPlan(title='Week 5 session', team_organization_id=herd['team'])
    db.session.add(sp)
    week = SeasonWeek.query.filter_by(week_number=5).one()
    week.session_plan = sp
    week.notes = 'Bring cones'
    week.joint_theme = 'Edited in the app'
    SeasonPage.query.filter_by(slug='weekly-plan').one().players_can_view = True
    plan.players_see_weeks = True
    db.session.commit()
    ids = {w.week_number: w.id for w in SeasonWeek.query}

    second = do_import(herd['team'])
    assert not second.plan_created and second.removed == []
    db.session.expire_all()
    assert counts() == [1, 5, 51, 11, 9]
    assert {w.week_number: w.id for w in SeasonWeek.query} == ids  # same rows, updated in place
    week = SeasonWeek.query.filter_by(week_number=5).one()
    assert week.session_plan_id == sp.id and week.notes == 'Bring cones'
    assert week.joint_theme.startswith('Throwing to space')  # export text wins
    assert SeasonPage.query.filter_by(slug='weekly-plan').one().players_can_view
    assert SeasonPlan.query.one().players_see_weeks


@needs_export
def test_replace_wipes_and_reimports(app, herd):
    do_import(herd['team'])
    week = SeasonWeek.query.filter_by(week_number=5).one()
    week.notes = 'Bring cones'
    db.session.commit()
    report = do_import(herd['team'], replace=True)
    assert report.replaced and counts() == [1, 5, 51, 11, 9]
    assert SeasonWeek.query.filter_by(week_number=5).one().notes is None


@needs_export
def test_reimport_removes_what_left_the_export(app, herd, tmp_path):
    folder = tmp_path / 'export'
    shutil.copytree(EXPORT, folder)
    from app.models.team_organization import TeamOrganization
    team = db.session.get(TeamOrganization, herd['team'])
    import_season_plan(str(folder), team)

    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['tabs'] = [t for t in manifest['tabs'] if t['slug'] != 'drills-by-phase-and-source']
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    report = import_season_plan(str(folder), team)
    assert report.removed == ['page drills-by-phase-and-source']
    assert SeasonPage.query.count() == 10


@needs_export
def test_plans_are_per_team(app, herd):
    other = stats_data.build_team('Thundering Herd', 'herd')
    do_import(herd['team'])
    do_import(other.id)
    assert SeasonPlan.query.count() == 2
    assert {w.team_organization_id for w in SeasonWeek.query} == {herd['team'], other.id}


def test_unknown_team_fails_cleanly(app, herd):
    result = app.test_cli_runner().invoke(args=['import-season-plan', EXPORT, '--team', 'nope'])
    assert result.exit_code != 0 and "No team with slug 'nope'" in result.output


# --------------------------------------------------------------------------
# Toggle and access
# --------------------------------------------------------------------------

def client(app, herd, who):
    return stats_data.Client(app, herd[who], herd['team'])


def test_toggle_is_off_by_default(app, herd):
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().season_plan_enabled is False
    assert TeamSettings(team_id=herd['team']).season_plan_enabled in (False, None)


@needs_export
def test_off_hides_the_nav_and_every_route_is_404(app, herd):
    do_import(herd['team'])
    c = client(app, herd, 'coach')
    home = c.get(NAV_PAGE).get_data(as_text=True)
    assert '/season-plan/' not in home
    for url in ('/season-plan/', '/season-plan/weeks', '/season-plan/week/1', '/season-plan/week/1/edit',
                '/season-plan/phase/1', '/season-plan/page/season-plan', '/season-plan/access'):
        assert c.get(url).status_code == 404, url
    assert c.post('/season-plan/week/1/edit', data={'block': 'x'}).status_code == 404


@needs_export
def test_coach_switches_it_on_in_feature_settings(app, herd):
    do_import(herd['team'])
    c = client(app, herd, 'coach')
    page = c.get('/team/settings/features').get_data(as_text=True)
    assert 'name="season_plan_enabled"' in page
    r = c.post('/team/settings/features', data={'season_plan_enabled': 'on', 'sessions_enabled': 'on'})
    assert r.status_code == 302
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().season_plan_enabled is True
    assert 'href="/season-plan/"' in c.get(NAV_PAGE).get_data(as_text=True)
    assert c.get('/season-plan/').status_code == 200


@needs_export
def test_every_page_renders_for_a_coach(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'coach')
    overview = c.get('/season-plan/?on=2028-03-29').get_data(as_text=True)
    assert 'Week 26' in overview and 'This week' in overview and 'sp-today' in overview
    assert 'UKU Tour 1 (~28 Mar)' in overview
    weeks = c.get('/season-plan/weeks?phase=3&squad=2s&on=2028-03-29')
    assert weeks.status_code == 200
    body = weeks.get_data(as_text=True)
    assert 'sp-current' in body and 'Walkthroughs' in body and 'Week 1 ·' not in body
    week = c.get('/season-plan/week/1').get_data(as_text=True)
    assert 'Welcome, baseline tests, grip and pivot' in week and '<strong>Learning points:</strong>' in week
    assert c.get('/season-plan/week/12').status_code == 200
    assert c.get('/season-plan/week/99').status_code == 404
    phase = c.get('/season-plan/phase/2').get_data(as_text=True)
    assert 'Breaking the mark' in phase and 'Phase 2 sessions' in phase
    page = c.get('/season-plan/page/captains-and-coaches-guide').get_data(as_text=True)
    assert 'sp-toc' in page and 'Classroom sessions' in page
    assert c.get('/season-plan/page/nope').status_code == 404
    assert c.get('/season-plan/week/5/edit').status_code == 200
    assert c.get('/season-plan/access').status_code == 200
    # Before the season starts
    assert 'Season starts in' in c.get('/season-plan/?on=2027-09-01').get_data(as_text=True)


@needs_export
def test_coach_can_edit_a_week(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    sp = SessionPlan(title='Linked', team_organization_id=herd['team'])
    db.session.add(sp)
    db.session.commit()
    sp_id = sp.id
    c = client(app, herd, 'coach')
    r = c.post('/season-plan/week/5/edit', data={
        'block': 'B', 'joint_theme': 'New joint', 'firsts_theme': '', 'notes': 'Cones',
        'is_event': 'on', 'session_plan_id': str(sp_id)})
    assert r.status_code == 302
    week = SeasonWeek.query.filter_by(week_number=5).one()
    assert (week.joint_theme, week.firsts_theme, week.notes, week.is_event, week.session_plan_id) == \
        ('New joint', None, 'Cones', True, sp_id)
    assert 'Linked' in c.get('/season-plan/week/5').get_data(as_text=True)


@needs_export
def test_players_see_only_what_a_coach_opens(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    player = client(app, herd, 'player')
    assert '/season-plan/' not in player.get(NAV_PAGE).get_data(as_text=True)
    assert player.get('/season-plan/').status_code == 404
    assert player.get('/season-plan/weeks').status_code == 404
    assert player.get('/season-plan/page/season-plan').status_code == 404
    # Players can't edit or change access
    assert player.post('/season-plan/week/1/edit', data={'block': 'x'}).status_code == 302
    assert SeasonWeek.query.filter_by(week_number=1).one().block != 'x'
    assert player.post('/season-plan/access', data={'weeks': 'on'}).status_code == 302

    coach = client(app, herd, 'coach')
    page_id = SeasonPage.query.filter_by(slug='weekly-plan').one().id
    coach.post('/season-plan/access', data={'weeks': 'on', f'page_{page_id}': 'on'})
    plan = SeasonPlan.query.one()
    assert plan.players_see_weeks and not plan.players_see_session_notes

    assert 'href="/season-plan/"' in player.get(NAV_PAGE).get_data(as_text=True)
    assert player.get('/season-plan/').headers['Location'].endswith('/season-plan/weeks')
    assert player.get('/season-plan/weeks').status_code == 200
    week = player.get('/season-plan/week/1').get_data(as_text=True)
    assert 'Five Frisbee Habits' in week and 'Learning points' not in week  # no session notes
    assert player.get('/season-plan/phase/1').status_code == 404
    assert player.get('/season-plan/page/weekly-plan').status_code == 200
    assert player.get('/season-plan/page/season-plan').status_code == 404


@needs_export
def test_captains_see_and_manage_everything(app, herd):
    """Captains are team admins, so they can edit and set player access too."""
    do_import(herd['team'])
    enable(herd['team'])
    captain = client(app, herd, 'captain')
    for url in ('/season-plan/', '/season-plan/weeks', '/season-plan/phase/1', '/season-plan/page/season-plan',
                '/season-plan/week/1/edit', '/season-plan/access'):
        assert captain.get(url).status_code == 200, url
    assert 'Learning points' in captain.get('/season-plan/week/1').get_data(as_text=True)


@needs_export
def test_another_teams_plan_is_not_visible(app, herd):
    do_import(herd['team'])
    other = stats_data.build_team('Thundering Herd', 'herd')
    db.session.add(TeamSettings(team_id=other.id, season_plan_enabled=True))
    db.session.commit()
    coach = stats_data.Client(app, make_user(other, 'othercoach', role='coach').id, other.id)
    assert 'No season plan has been imported' in coach.get('/season-plan/').get_data(as_text=True)
    assert coach.get('/season-plan/weeks').status_code == 404
    assert coach.get('/season-plan/week/1').status_code == 404
