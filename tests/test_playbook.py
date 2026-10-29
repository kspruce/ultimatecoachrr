"""Playbook plays drawn in the drill editor: saved in stages, played back on
the play's page, shown on the game-day cards and in the PDF, and picked
for a game in a scouting report's game plan."""
import io
import json

import pytest

from app import db
from app.models.playbook import Formation, Play
from app.models.scouting import ScoutingReport
from app.utils.playbook_export import build_sections
from tests import stats_data
from tests.test_drill_editor import png_bytes
from tests.test_teams import make_user

STAGES = {'version': 2, 'field': {'length': 70, 'width': 40, 'endzone': 20},
          'stages': [{'name': 'Set up', 'notes': '', 'objects': []},
                     {'name': 'Break-side cut', 'notes': 'Clear early', 'objects': []}]}


def play_form(title='Side stack', stages=2, play_type='offense', formation_id='', state=STAGES):
    return {'data': json.dumps({'title': title, 'description': 'Iso the break side', 'notes': 'Patience',
                                'type': play_type, 'formation_id': formation_id}),
            'editor': json.dumps(state),
            'svg': ['<svg xmlns="http://www.w3.org/2000/svg"></svg>'] * stages,
            'stage_name': ['Set up', 'Break-side cut'][:stages],
            'stage_notes': ['', 'Clear early'][:stages],
            'diagram': [(io.BytesIO(png_bytes(c)), f'stage-{i}.png') for i, c in enumerate(['red', 'blue'][:stages])]}


@pytest.fixture
def club(app, team):
    admin = make_user(team, 'admin1', role='admin')
    player = make_user(team, 'player1', role='player')
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    other_admin = make_user(other, 'otheradmin', role='admin')
    formation = Formation(name='Vert stack', type='offense', team_organization_id=team.id)
    other_formation = Formation(name='Their stack', type='offense', team_organization_id=other.id)
    db.session.add_all([formation, other_formation])
    db.session.commit()
    return {'team': team.id, 'other': other.id, 'formation': formation.id, 'other_formation': other_formation.id,
            'admin': stats_data.Client(app, admin.id, team.id),
            'player': stats_data.Client(app, player.id, team.id),
            'other_admin': stats_data.Client(app, other_admin.id, other.id)}


def draw(club, **kw):
    r = club['admin'].post('/playbook/api/plays', data=play_form(**kw), content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['play_id']


def test_draw_a_play_in_stages(app, club):
    assert 'data-kind="play"' in club['admin'].get('/playbook/plays/draw').get_data(as_text=True)
    play_id = draw(club, formation_id=str(club['formation']))
    play = db.session.get(Play, play_id)
    assert play.name == 'Side stack' and play.type == 'offense' and play.formation_id == club['formation']
    assert play.notes == 'Patience' and play.stage_count == 2
    assert [d.step_label for d in play.editor_diagrams] == ['Set up', 'Break-side cut']
    assert club['admin'].get(play.editor_diagrams[1].image_url).data == png_bytes('blue')

    # The page plays it; players see it too, without the editing buttons
    page = club['player'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)
    assert 'id="drill-animation"' in page and 'drill_viewer.js' in page
    assert 'Edit drawing' not in page and '/assignments' not in page
    assert 'Edit drawing' in club['admin'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)

    # Redrawn with one stage: the second goes
    r = club['admin'].put(f'/playbook/api/plays/{play_id}', data=play_form('Side stack 2', stages=1, state={**STAGES, 'stages': STAGES['stages'][:1]}),
                          content_type='multipart/form-data')
    assert r.status_code == 200
    db.session.expire_all()
    play = db.session.get(Play, play_id)
    assert play.name == 'Side stack 2' and play.stage_count == 1
    assert 'id="drill-animation"' not in club['admin'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)


def test_only_admins_draw_and_only_their_own_plays(app, club):
    r = club['player'].post('/playbook/api/plays', data=play_form(), content_type='multipart/form-data')
    assert r.status_code == 302 and Play.query.count() == 0
    play_id = draw(club)
    r = club['other_admin'].put(f'/playbook/api/plays/{play_id}', data=play_form('Mine now'),
                                content_type='multipart/form-data')
    assert r.status_code == 404
    assert club['other_admin'].get(f'/playbook/plays/{play_id}/draw').status_code == 404
    # Another team's formation isn't taken
    other_play = club['other_admin'].post('/playbook/api/plays', data=play_form(formation_id=str(club['formation'])),
                                          content_type='multipart/form-data').get_json()['play_id']
    assert db.session.get(Play, other_play).formation_id is None


def test_cards_and_pdf_show_the_drawing(app, club):
    o_play = draw(club)
    d_play = draw(club, title='Cup', play_type='defense', stages=1)
    cards = club['player'].get('/playbook/cards').get_data(as_text=True)
    assert 'Side stack' in cards and 'Cup' in cards and '2/2 · Break-side cut' in cards
    only_d = club['player'].get('/playbook/cards?type=defense').get_data(as_text=True)
    assert 'Cup' in only_d and 'Side stack' not in only_d

    with app.test_request_context():
        plays = Play.query.filter_by(team_organization_id=club['team']).all()
        sections = dict(build_sections([], plays))
        side = next(i for i in sections['Offense'] if i['obj'].id == o_play)
        cup = next(i for i in sections['Defense'] if i['obj'].id == d_play)
    assert len(side['stages']) == 2 and side['stages'][0]['src'].startswith('data:image/png;base64,')
    assert len(cup['stages']) == 1


def test_game_plan_picks_plays(app, club):
    o_play = draw(club)
    d_play = draw(club, title='Cup', play_type='defense', stages=1)
    other_play = club['other_admin'].post('/playbook/api/plays', data=play_form('Not yours'),
                                          content_type='multipart/form-data').get_json()['play_id']
    form = club['admin'].get('/scouting/add').get_data(as_text=True)
    assert 'Side stack' in form and 'Not yours' not in form

    r = club['admin'].post('/scouting/add', data={'team_name': 'Ka-Pow', 'tournament_id': 0, 'game_id': 0,
                                                  'play_ids': [d_play, o_play, other_play]})
    assert r.status_code == 302
    report = ScoutingReport.query.one()
    assert [p.id for p in report.plays_in_order] == [o_play, d_play]
    assert report.has_game_plan

    detail = club['admin'].get(f'/scouting/{report.id}').get_data(as_text=True)
    assert 'Plays to run' in detail and f'/playbook/cards?report={report.id}' in detail
    cards = club['player'].get(f'/playbook/cards?report={report.id}').get_data(as_text=True)
    assert 'Plays vs Ka-Pow' in cards and 'Side stack' in cards and 'Cup' in cards
    assert club['other_admin'].get(f'/playbook/cards?report={report.id}').status_code == 404

    # Editing keeps the picks unless they're changed; deleting a play drops it
    club['admin'].post(f'/scouting/edit/{report.id}', data={'team_name': 'Ka-Pow', 'tournament_id': 0,
                                                            'game_id': 0, 'play_ids': [o_play, d_play]})
    club['admin'].post(f'/playbook/plays/{d_play}/delete')
    db.session.expire_all()
    assert [p.id for p in db.session.get(ScoutingReport, report.id).plays] == [o_play]
