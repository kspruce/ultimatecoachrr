import copy
import json
import os

import pytest

from app import db
from app.models.drill import SavedDrill, DrillDiagram
from app.models.session import SessionPlan, SessionComponent
from app.utils.season_import import import_season, SeasonImportError

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
IMAGES = os.path.join(FIXTURES, 'season_images')


@pytest.fixture
def season():
    with open(os.path.join(FIXTURES, 'sample_season.json')) as f:
        return json.load(f)


def counts():
    return (SavedDrill.query.count(), DrillDiagram.query.count(),
            SessionPlan.query.count(), SessionComponent.query.count())


def test_first_import_creates_everything(app, team, season):
    summary = import_season(season, IMAGES, team.id)

    assert counts() == (3, 3, 2, 7)
    assert summary.counts['drill']['created'] == 2
    assert summary.counts['card']['created'] == 1
    assert summary.counts['session']['created'] == 2

    card = SavedDrill.query.filter_by(external_id='card-a').one()
    assert card.is_standard_card and card.card_code == 'Card A'
    assert '**4v3 mini (20 min)**' in card.description

    wrinkle = SavedDrill.query.filter_by(external_id='flik-sideline-wrinkle').one()
    assert [d.step_label for d in wrinkle.diagrams] == ['1 Set-up', '2 Reset']
    assert wrinkle.diagrams[0].svg_url and wrinkle.diagrams[1].svg_url is None
    assert wrinkle.source == 'Flik' and not wrinkle.is_standard_card

    plan = SessionPlan.query.filter_by(external_id='w02-split-2s').one()
    assert plan.team_organization_id == team.id
    assert plan.season == '2027/28' and plan.week_number == 2 and plan.squad == '2s'
    assert plan.phase_number == 1 and plan.phase_name == 'Phase 1: Foundations'
    assert plan.week_commencing.isoformat() == '2027-10-11'
    assert plan.learning_points == ['Reset early', 'Pivot to open space', 'Cut up the line']
    assert plan.key_terms[0] == ['Sideline trap', 'Mark forcing the thrower along the sideline']
    assert plan.notes == '- Bring spare discs\n- Pitch 3 if pitch 2 is waterlogged'
    assert plan.date is None  # no date in the file: left empty, not guessed

    comps = plan.components.order_by(SessionComponent.order).all()
    assert [c.component_type for c in comps] == ['warmup', 'drill', 'water', 'drill']
    assert comps[0].saved_drill.external_id == 'card-a'
    assert comps[1].description == 'Swap marker every 5 throws.'
    assert comps[1].coach_cue == 'Step out low and wide.'
    assert comps[2].drill_id is None

    joint = SessionPlan.query.filter_by(external_id='w02-joint').one()
    assert joint.date.isoformat() == '2027-10-16'
    assert joint.start_time.strftime('%H:%M') == '10:00'
    assert joint.end_time.strftime('%H:%M') == '12:00'  # start + length_minutes


def test_second_run_changes_nothing(app, team, season):
    import_season(season, IMAGES, team.id)
    ids_before = sorted(c.id for c in SessionComponent.query.all())

    summary = import_season(season, IMAGES, team.id)

    assert counts() == (3, 3, 2, 7)
    assert sorted(c.id for c in SessionComponent.query.all()) == ids_before
    for kind, c in summary.counts.items():
        assert c['created'] == 0 and c['updated'] == 0, kind


def test_changed_file_updates_in_place(app, team, season):
    import_season(season, IMAGES, team.id)
    plan_id = SessionPlan.query.filter_by(external_id='w02-split-2s').one().id

    changed = copy.deepcopy(season)
    changed['sessions'][0]['aim'] = 'New aim'
    changed['sessions'][0]['activities'].pop(2)  # drop the water break
    changed['drills'][0]['diagrams'][1]['caption'] = 'New caption'
    summary = import_season(changed, IMAGES, team.id)

    plan = SessionPlan.query.filter_by(external_id='w02-split-2s').one()
    assert plan.id == plan_id and plan.aim == 'New aim'
    assert [c.order for c in plan.components.order_by(SessionComponent.order)] == [1, 2, 3]
    assert summary.counts['session'] == {'created': 0, 'updated': 1, 'unchanged': 1}
    wrinkle = SavedDrill.query.filter_by(external_id='flik-sideline-wrinkle').one()
    assert wrinkle.diagrams[1].caption == 'New caption'
    assert counts() == (3, 3, 2, 6)


def test_dry_run_writes_nothing(app, team, season):
    summary = import_season(season, IMAGES, team.id, dry_run=True)

    assert counts() == (0, 0, 0, 0)
    assert summary.dry_run and summary.counts['session']['created'] == 2
    assert 'DRY RUN' in summary.report()


def test_sessions_can_use_drills_from_an_earlier_import(app, team, season):
    import_season(season, IMAGES, team.id)
    sessions_only = {'schema': season['schema'], 'season': season['season'],
                     'sessions': season['sessions']}

    import_season(sessions_only, None, team.id)

    assert counts() == (3, 3, 2, 7)


def test_invalid_file_is_rejected_with_every_problem(app, team, season):
    bad = copy.deepcopy(season)
    bad['sessions'][0]['activities'][1]['drill_id'] = 'no-such-drill'
    bad['sessions'][0]['activities'][2]['type'] = 'nap'
    bad['sessions'][0]['squad'] = '3s'
    bad['drills'][1]['diagrams'][0]['file'] = 'panels/missing.png'

    with pytest.raises(SeasonImportError) as exc:
        import_season(bad, IMAGES, team.id)

    text = str(exc.value)
    assert "'no-such-drill'" in text and "'nap'" in text and "'3s'" in text
    assert 'missing.png' in text
    assert counts() == (0, 0, 0, 0)


def test_images_outside_images_dir_are_refused(app, team, season):
    bad = copy.deepcopy(season)
    bad['drills'][0]['diagrams'][0]['file'] = '../sample_season.json'
    with pytest.raises(SeasonImportError, match='outside --images-dir'):
        import_season(bad, IMAGES, team.id)


def test_external_ids_are_per_team(app, team, season):
    from app.models.team_organization import TeamOrganization
    other = TeamOrganization(name='Other', slug='other')
    db.session.add(other)
    db.session.commit()

    import_season(season, IMAGES, team.id)
    import_season(season, IMAGES, other.id)

    assert SessionPlan.query.filter_by(external_id='w02-split-2s').count() == 2


def test_diagram_routes_and_guest_page(app, team, season):
    import_season(season, IMAGES, team.id)
    client = app.test_client()
    wrinkle = SavedDrill.query.filter_by(external_id='flik-sideline-wrinkle').one()
    diagram = wrinkle.diagrams[0]

    png = client.get(diagram.image_url)
    assert png.status_code == 200 and png.mimetype == 'image/png'
    with open(os.path.join(IMAGES, 'panels', 'flik-sideline-wrinkle-1.png'), 'rb') as f:
        assert png.data == f.read()
    svg = client.get(diagram.svg_url)
    assert svg.mimetype == 'image/svg+xml' and 'sandbox' in svg.headers['Content-Security-Policy']
    assert client.get(f'/sessions/drills/diagrams/{diagram.id}/0000000000000000.png').status_code == 404

    plan = SessionPlan.query.filter_by(external_id='w02-split-2s').one()
    plan.share_token = 'tok'
    db.session.commit()
    page = client.get(f'/sessions/{plan.id}/guest/tok').get_data(as_text=True)
    for text in ('Season Plan', 'Block A: throwing, catching, resets', '2s captains',
                 'Pivot to open space', 'Sideline trap', 'Step out low and wide.',
                 diagram.image_url, 'droplet'):
        assert text in page, text


def test_logged_in_pages_show_season_fields(app, team, season):
    from app.models.user import User
    import_season(season, IMAGES, team.id)
    user = User(username='coach', role='coach', team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.commit()
    user_id, team_id = user.id, team.id

    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(user_id)
        s['_fresh'] = True
        s['current_team_id'] = team_id

    plan_id = SessionPlan.query.filter_by(external_id='w02-split-2s').one().id
    wrinkle_id = SavedDrill.query.filter_by(external_id='flik-sideline-wrinkle').one().id

    def get(url):
        # A fresh app context per request, as in production (Flask-Login
        # caches the user on g, which is per app context).
        with app.app_context():
            response = client.get(url)
            assert response.status_code == 200, url
            return response.get_data(as_text=True)

    detail = get(f'/sessions/{plan_id}/detail')
    assert 'Getting off the sideline' in detail and 'Reset cutter goes on stall 4.' in detail
    printable = get(f'/sessions/{plan_id}/printable')
    assert 'Run by:' in printable and 'Coach:' in printable and 'Sideline trap' in printable

    drill_page = get(f'/sessions/drills/{wrinkle_id}')
    assert '2 Reset' in drill_page and 'Reset cuts up the line' in drill_page

    listing = get('/sessions/?season=2027/28&squad=joint')
    assert 'Joint session: resets under pressure' in listing
    assert 'Getting off the sideline' not in listing
    listing = get('/sessions/?phase=1&block=Block A: throwing, catching, resets')
    assert 'Getting off the sideline' in listing
