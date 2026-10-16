"""The drill diagram editor saves drills with a PNG, an SVG and the editable
drawing, and reopens them; the season import leaves editor diagrams alone."""
import io
import json
import os

import pytest
from PIL import Image

from app import db
from app.models.drill import SavedDrill, DrillDiagram
from tests import stats_data
from tests.test_teams import make_user

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')

STATE = {'version': 1, 'field': {'length': 70, 'width': 40, 'endzone': 20},
         'objects': [{'type': 'circle', 'left': 100, 'top': 50, 'radius': 7, 'herdType': 'disc'}]}


def png_bytes(colour='red'):
    buf = io.BytesIO()
    Image.new('RGB', (40, 20), colour).save(buf, 'PNG')
    return buf.getvalue()


def editor_form(title='Ho stack', colour='red', state=STATE):
    return {'data': json.dumps({'title': title, 'skill_level': 'beginner',
                                'recommended_duration': '15', 'min_players': ''}),
            'editor': json.dumps(state),
            'svg': '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            'diagram': (io.BytesIO(png_bytes(colour)), 'diagram.png')}


@pytest.fixture
def coach(app, team):
    user = make_user(team, 'coachy', role='coach')
    return stats_data.Client(app, user.id, team.id)


def test_editor_pages_render(app, team, coach):
    page = coach.get('/sessions/drills/editor')
    assert page.status_code == 200
    assert b'drill_editor.js' in page.data and b'id="editor-state"' in page.data
    assert b'Draw a Drill' in coach.get('/sessions/drills').data


def test_create_reopen_and_update_a_drill(app, team, coach):
    r = coach.post('/sessions/api/drills', data=editor_form(),
                   content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    drill_id = r.get_json()['drill_id']

    drill = db.session.get(SavedDrill, drill_id)
    assert drill.title == 'Ho stack' and drill.recommended_duration == 15
    assert drill.min_players is None and drill.team_organization_id == team.id
    diagram = drill.editor_diagram
    assert json.loads(diagram.editor_json) == STATE
    image = coach.get(diagram.image_url)
    assert image.status_code == 200 and image.data == png_bytes('red')
    assert coach.get(diagram.svg_url).status_code == 200

    # Reopening embeds the drawing; the API returns it too
    page = coach.get(f'/sessions/drills/editor/{drill_id}').get_data(as_text=True)
    assert '"herdType": "disc"' in page or '"herdType":"disc"' in page
    assert coach.get(f'/sessions/api/drills/{drill_id}').get_json()['editor'] == STATE
    assert 'Edit Diagram' in coach.get(f'/sessions/drills/{drill_id}').get_data(as_text=True)

    # Saving again replaces the same diagram
    new_state = {**STATE, 'objects': []}
    r = coach.put(f'/sessions/api/drills/{drill_id}',
                  data=editor_form('Renamed', 'blue', new_state), content_type='multipart/form-data')
    assert r.status_code == 200, r.get_data(as_text=True)
    db.session.expire_all()
    drill = db.session.get(SavedDrill, drill_id)
    assert drill.title == 'Renamed' and len(drill.diagrams) == 1
    assert json.loads(drill.editor_diagram.editor_json) == new_state
    assert coach.get(drill.editor_diagram.image_url).data == png_bytes('blue')


def test_bad_uploads_and_permissions(app, team, coach):
    form = editor_form()
    form['diagram'] = (io.BytesIO(b'<script>not a png</script>'), 'diagram.png')
    r = coach.post('/sessions/api/drills', data=form, content_type='multipart/form-data')
    assert r.status_code == 400
    assert SavedDrill.query.count() == 0

    player = stats_data.Client(app, make_user(team, 'playa', role='player').id, team.id)
    r = player.post('/sessions/api/drills', data=editor_form(), content_type='multipart/form-data')
    assert r.status_code in (302, 403)
    assert SavedDrill.query.count() == 0

    r = coach.post('/sessions/api/drills', data=editor_form(), content_type='multipart/form-data')
    drill_id = r.get_json()['drill_id']
    assert player.put(f'/sessions/api/drills/{drill_id}', data=editor_form('Hacked'),
                      content_type='multipart/form-data').status_code == 403

    other_team = stats_data.build_team('Herd 2028', 'herd-2028')
    other = stats_data.Client(app, make_user(other_team, 'othercoach', role='coach').id, other_team.id)
    assert other.get(f'/sessions/api/drills/{drill_id}').status_code == 404
    assert other.get(f'/sessions/drills/editor/{drill_id}').status_code == 404


def test_season_reimport_keeps_editor_diagrams(app, team, coach):
    from app.utils.season_import import import_season
    with open(os.path.join(FIXTURES, 'sample_season.json')) as f:
        season = json.load(f)
    images = os.path.join(FIXTURES, 'season_images')
    import_season(season, images, team.id)
    drill = SavedDrill.query.filter_by(external_id='flik-sideline-wrinkle').one()
    imported = len(drill.diagrams)
    page = coach.get(f'/sessions/drills/editor/{drill.id}').get_data(as_text=True)
    assert 'already has' in page

    r = coach.put(f'/sessions/api/drills/{drill.id}', data=editor_form(drill.title),
                  content_type='multipart/form-data')
    assert r.status_code == 200, r.get_data(as_text=True)
    db.session.expire_all()
    assert len(db.session.get(SavedDrill, drill.id).diagrams) == imported + 1

    # A changed file re-syncs the imported diagrams but keeps the drawn one
    season['drills'][0]['diagrams'][0]['caption'] = 'Changed'
    import_season(season, images, team.id)
    db.session.expire_all()
    drill = db.session.get(SavedDrill, drill.id)
    assert len(drill.diagrams) == imported + 1
    assert drill.diagrams[0].caption == 'Changed'
    assert drill.editor_diagram is not None
    assert DrillDiagram.query.filter(DrillDiagram.editor_json.isnot(None)).count() == 1
