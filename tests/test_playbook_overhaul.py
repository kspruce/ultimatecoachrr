"""The playbook overhaul: offence and defence plays only (concepts moved to
Theory), coaches and captains edit, roles and tags typed in, draft / in use
/ retired, links to theory, drills and clips both ways, plays inside theory
articles, usual roles, learning plays, and session plans keeping their plays."""
import io
from datetime import date

import pytest
from PIL import Image

from app import db
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.models.playbook import (Formation, Play, PlayAssignment, PlayerPosition, PlayerUsualRole, PlayLearned, PlayTag,
                                 PlayToLearn)
from app.models.session import SessionComponent, SessionPlan
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from tests import stats_data
from tests.test_teams import make_user
from tests.test_theory import fresh, text, welcomed


@pytest.fixture
def club(app):
    team = stats_data.build_team('Herd', 'herd')
    other = stats_data.build_team('Other', 'other')
    db.session.add_all([TeamSettings(team_id=team.id), TeamSettings(team_id=other.id)])
    db.session.flush()
    section = TheorySection(name='Offence', slug='offence', order=1, team_organization_id=team.id)
    db.session.add(section)
    db.session.flush()
    why = TheoryTopic(section_id=section.id, name='Why we iso', content='Space.', order=1, published=True,
                      team_organization_id=team.id)
    secret = TheoryTopic(section_id=section.id, name='Draft idea', content='x', order=2, published=False,
                         team_organization_id=team.id)
    drill = SavedDrill(title='Iso drill', team_organization_id=team.id)
    clip = Clip(title='Iso vs Ka-Pow', team_organization_id=team.id)
    their_drill = SavedDrill(title='Their drill', team_organization_id=other.id)
    db.session.add_all([why, secret, drill, clip, their_drill])
    db.session.flush()
    plays = {}
    for name, kind, status, order in [('Side stack', 'offense', 'active', 1), ('Hammer', 'offense', 'active', 2),
                                      ('Cup', 'defense', 'active', 1), ('Secret set', 'offense', 'draft', 3),
                                      ('Old zone', 'defense', 'retired', 2)]:
        plays[name] = Play(name=name, type=kind, status=status, sort_order=order, team_organization_id=team.id)
    their_play = Play(name='Their play', type='offense', team_organization_id=other.id)
    db.session.add_all(list(plays.values()) + [their_play])
    db.session.commit()
    ids = {k: v.id for k, v in plays.items()}
    return {
        'team': team.id, 'other': other.id, 'why': why.id, 'secret': secret.id, 'drill': drill.id, 'clip': clip.id,
        'their_drill': their_drill.id, 'their_play': their_play.id, 'section': section.id, **ids,
        'coach': make_user(team, 'coach', role='coach').id,
        'captain': make_user(team, 'captain', role='captain').id,
        'player': make_user(team, 'player', role='player').id,
        'other_coach': make_user(other, 'othercoach', role='coach').id,
    }


def client(app, club, who, team='team'):
    return stats_data.Client(app, club[who], club[team])


def form(**kw):
    data = {'name': 'Iso', 'type': 'offense', 'status': 'active', 'call': 'Iso', 'signal': 'Fist',
            'description': 'Clear the break side.', 'notes': '', 'image_url': '', 'ultiplay_embed': '',
            'tags': '', 'role_name': ['Handler 1', 'Iso cutter'],
            'role_text': ['Swing it to the break side.', 'Cut under from the back.'], 'action': 'save'}
    data.update(kw)
    return data


# ── Switching it off and who can do what ──────────────────────────────────

def test_off_means_404_everywhere(app, club):
    TeamSettings.query.filter_by(team_id=club['team']).one().playbook_enabled = False
    db.session.commit()
    c = client(app, club, 'coach')
    for url in ('/playbook/', f'/playbook/plays/{club["Hammer"]}', '/playbook/cards', '/playbook/roles',
                '/playbook/plays/add', '/playbook/plays/draw'):
        assert c.get(url).status_code == 404, url
    # ...and Theory stops showing plays
    assert 'Hammer' not in text(c.get('/theory/?q=hammer'))


def test_coaches_and_captains_edit_players_dont(app, club):
    for who in ('coach', 'captain'):
        assert client(app, club, who).get('/playbook/plays/add').status_code == 200, who
    p = client(app, club, 'player')
    for url in ('/playbook/plays/add', f'/playbook/plays/{club["Hammer"]}/edit', '/playbook/plays/draw',
                f'/playbook/plays/{club["Hammer"]}/learners'):
        assert p.get(url).status_code == 403, url
    for url in (f'/playbook/plays/{club["Hammer"]}/delete', f'/playbook/plays/{club["Hammer"]}/move',
                f'/playbook/plays/{club["Hammer"]}/status', '/playbook/images'):
        assert p.post(url).status_code == 403, url
    assert fresh(Play, club['Hammer']) is not None
    assert 'Edit details' not in text(p.get(f'/playbook/plays/{club["Hammer"]}'))


def test_other_teams_plays_are_404(app, club):
    c = client(app, club, 'coach')
    assert c.get(f'/playbook/plays/{club["their_play"]}').status_code == 404
    assert c.post(f'/playbook/plays/{club["their_play"]}/delete').status_code == 404


# ── What players see ──────────────────────────────────────────────────────

def test_drafts_and_retired_plays(app, club):
    p = client(app, club, 'player')
    page = text(p.get('/playbook/'))
    assert 'Side stack' in page and 'Cup' in page
    assert 'Secret set' not in page and 'Old zone' not in page
    assert p.get(f'/playbook/plays/{club["Secret set"]}').status_code == 404
    retired = text(p.get('/playbook/?show=retired'))
    assert 'Old zone' in retired and 'Side stack' not in retired
    assert p.get(f'/playbook/plays/{club["Old zone"]}').status_code == 200
    cards = text(p.get('/playbook/cards'))
    assert 'Side stack' in cards and 'Old zone' not in cards and 'Secret set' not in cards
    from app.routes.playbook import export_plays
    assert {pl.name for pl in export_plays(club['team'])} == {'Side stack', 'Hammer', 'Cup'}

    c = client(app, club, 'coach')
    assert 'Secret set' in text(c.get('/playbook/'))
    c.post(f'/playbook/plays/{club["Secret set"]}/status', data={'status': 'active'})
    assert fresh(Play, club['Secret set']).status == 'active'
    assert 'Secret set' in text(p.get('/playbook/'))


def test_concepts_are_gone_and_their_links_go_to_theory(app, club):
    page = text(client(app, club, 'coach').get('/playbook/'))
    assert 'Concept' not in page and 'formation' not in page.lower()
    formation = Formation(name='Vert', team_organization_id=club['team'], moved_to_topic_id=club['why'])
    old = Formation(name='Never moved', team_organization_id=club['team'])
    db.session.add_all([formation, old])
    db.session.commit()
    r = client(app, club, 'player').get(f'/playbook/formation/{formation.id}')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/theory/topic/{club["why"]}')
    assert client(app, club, 'player').get(f'/playbook/formation/{old.id}').status_code == 404


def test_search_and_filters(app, club):
    db.session.add(PlayAssignment(play_id=club['Cup'], position=PlayerPosition(name='Wing', team_organization_id=club['team']),
                                  instructions='Take away the swing', team_organization_id=club['team']))
    play = db.session.get(Play, club['Hammer'])
    play.call = 'Thor'
    play.tags = [PlayTag(name='endzone', team_organization_id=club['team'])]
    db.session.commit()
    p = client(app, club, 'player')
    assert 'Hammer' in text(p.get('/playbook/?q=thor')) and 'Cup' not in text(p.get('/playbook/?q=thor'))
    assert 'Cup' in text(p.get('/playbook/?q=swing'))
    page = text(p.get('/playbook/?type=defense'))
    assert 'Cup' in page and 'Hammer' not in page
    assert 'Hammer' in text(p.get('/playbook/?tag=endzone')) and 'Side stack' not in text(p.get('/playbook/?tag=endzone'))


# ── Writing a play ────────────────────────────────────────────────────────

def test_write_a_play_with_roles_tags_and_links(app, club):
    c = client(app, club, 'coach')
    r = c.post('/playbook/plays/add', data=form(tags='iso, Endzone,iso', topics=[club['why']],
                                                drills=[club['drill'], club['their_drill']], clips=[club['clip']]))
    assert r.status_code == 302, text(r)
    play = Play.query.filter_by(name='Iso').one()
    assert (play.call, play.signal, play.status, play.type) == ('Iso', 'Fist', 'active', 'offense')
    assert play.sort_order == 4 and play.created_by == club['coach']
    assert [(a.position.name, a.order) for a in play.assignments] == [('Handler 1', 1), ('Iso cutter', 2)]
    assert sorted(t.name for t in play.tags) == ['Endzone', 'iso']
    assert [t.id for t in play.theory_topics] == [club['why']]
    assert [d.id for d in play.drills] == [club['drill']]  # not the other team's
    assert [cl.id for cl in play.clips] == [club['clip']]

    page = text(client(app, club, 'player').get(f'/playbook/plays/{play.id}'))
    for bit in ('Call: <b>Iso</b>', 'Signal: <b>Fist</b>', 'Handler 1', 'Swing it to the break side.', 'Read the why',
                'Why we iso', 'Iso drill', 'Iso vs Ka-Pow'):
        assert bit in page, bit
    # Both ways: the topic, the clip
    topic = text(client(app, club, 'player').get(f'/theory/topic/{club["why"]}'))
    assert 'Plays that use this' in topic and f'/playbook/plays/{play.id}' in topic
    assert 'In the playbook' in text(client(app, club, 'player').get(f'/clips/{club["clip"]}'))

    # Edit: rename a role, drop one, drop a tag; unused roles and tags go
    r = c.post(f'/playbook/plays/{play.id}/edit', data=form(tags='iso', role_name=['Handler 1'],
                                                            role_text=['Swing it early.'], status='retired'))
    assert r.status_code == 302
    play = fresh(Play, play.id)
    assert [a.instructions for a in play.assignments] == ['Swing it early.'] and play.status == 'retired'
    assert [t.name for t in play.tags] == ['iso']
    assert PlayTag.query.filter_by(team_organization_id=club['team']).count() == 1
    assert PlayerPosition.query.filter_by(team_organization_id=club['team']).count() == 1
    assert play.theory_topics == [] and play.drills == []


def test_role_mistakes_keep_the_page(app, club):
    c = client(app, club, 'coach')
    r = c.post('/playbook/plays/add', data=form(role_name=['Cup', 'cup'], role_text=['a', 'b']))
    assert r.status_code == 200 and 'cup is in the list twice' in text(r) and 'value="Iso"' in text(r)
    r = c.post('/playbook/plays/add', data=form(role_name=['Cup'], role_text=['']))
    assert 'Say what Cup does' in text(r)
    assert Play.query.filter_by(name='Iso').count() == 0


def test_save_and_draw(app, club):
    r = client(app, club, 'coach').post('/playbook/plays/add', data=form(action='draw'))
    play = Play.query.filter_by(name='Iso').one()
    assert r.headers['Location'].endswith(f'/playbook/plays/{play.id}/draw')


def test_deleting_takes_roles_and_learning_with_it(app, club):
    play = db.session.get(Play, club['Hammer'])
    play.assignments = [PlayAssignment(position=PlayerPosition(name='Thrower', team_organization_id=club['team']),
                                       instructions='Throw it', team_organization_id=club['team'])]
    db.session.add_all([PlayLearned(user_id=club['player'], play_id=play.id, team_organization_id=club['team']),
                        PlayToLearn(play_id=play.id, team_organization_id=club['team'])])
    db.session.commit()
    r = client(app, club, 'coach').post(f'/playbook/plays/{club["Hammer"]}/delete')
    assert r.status_code == 302
    assert PlayAssignment.query.count() == 0 and PlayLearned.query.count() == 0 and PlayToLearn.query.count() == 0
    assert PlayerPosition.query.count() == 0


def test_reorder(app, club):
    c = client(app, club, 'coach')
    c.post(f'/playbook/plays/{club["Hammer"]}/move', data={'direction': 'up'})
    names = [p.name for p in Play.query.filter_by(team_organization_id=club['team'], type='offense')
             .order_by(Play.sort_order)]
    assert names[:2] == ['Hammer', 'Side stack']


def test_photo_upload(app, club):
    buf = io.BytesIO()
    Image.new('RGB', (2400, 1200), 'white').save(buf, 'PNG')
    buf.seek(0)
    c = client(app, club, 'coach')
    r = c.post('/playbook/images', data={'image': (buf, 'play.png')}, content_type='multipart/form-data')
    url = r.get_json()['url']
    assert url.startswith('/playbook/image/') and c.get(url).status_code == 200
    assert client(app, club, 'other_coach', team='other').get(url).status_code == 404
    r = c.post(f'/playbook/plays/{club["Hammer"]}/edit', data=form(name='Hammer', image_url=url))
    assert r.status_code == 302 and fresh(Play, club['Hammer']).image_url == url
    # It goes into the PDF inline
    from app.utils.playbook_export import _item
    with app.test_request_context():
        assert _item('play', db.session.get(Play, club['Hammer']))['image'].startswith('data:image/webp;base64,')


# ── Plays inside theory ───────────────────────────────────────────────────

def test_plays_inside_a_theory_article(app, club):
    topic = db.session.get(TheoryTopic, club['why'])
    topic.content = (f'Look:\n\n[[play:{club["Hammer"]}]]\n\nAnd [[play:{club["Secret set"]}]]\n\n'
                     f'[[play:{club["their_play"]}]]')
    db.session.commit()
    page = text(client(app, club, 'player').get(f'/theory/topic/{club["why"]}'))
    assert f'href="/playbook/plays/{club["Hammer"]}"' in page and 'pb-embed' in page
    assert 'Secret set' not in page and 'Their play' not in page and '[[play:' not in page
    assert 'Secret set' in text(client(app, club, 'coach').get(f'/theory/topic/{club["why"]}'))
    html = client(app, club, 'coach').post('/theory/preview', data={'content': f'[[play:{club["Cup"]}]]'}).get_json()['html']
    assert 'pb-embed' in html and 'Cup' in html

    # Linking plays from the topic's side
    c = client(app, club, 'coach')
    assert 'data-insert-play' in text(c.get(f'/theory/edit_topic/{club["why"]}'))
    r = c.post(f'/theory/edit_topic/{club["why"]}', data={'name': 'Why we iso', 'section_id': club['section'],
                                                           'content': 'x', 'action': 'save', 'plays': [club['Cup'], club['their_play']]})
    assert r.status_code == 302
    assert [p.id for p in fresh(TheoryTopic, club['why']).plays] == [club['Cup']]


def test_theory_search_finds_plays(app, club):
    page = text(client(app, club, 'player').get('/theory/?q=hammer'))
    assert 'In the playbook' in page and f'/playbook/plays/{club["Hammer"]}' in page
    assert 'Nothing matches' not in page
    assert 'Secret set' not in text(client(app, club, 'player').get('/theory/?q=secret'))


def test_read_the_why_hides_draft_topics_from_players(app, club):
    play = db.session.get(Play, club['Hammer'])
    play.theory_topics = [db.session.get(TheoryTopic, club['why']), db.session.get(TheoryTopic, club['secret'])]
    db.session.commit()
    page = text(client(app, club, 'player').get(f'/playbook/plays/{club["Hammer"]}'))
    assert 'Why we iso' in page and 'Draft idea' not in page
    TeamSettings.query.filter_by(team_id=club['team']).one().theory_enabled = False
    db.session.commit()
    assert 'Read the why' not in text(client(app, club, 'player').get(f'/playbook/plays/{club["Hammer"]}'))


# ── Roles and learning ────────────────────────────────────────────────────

def test_usual_role(app, club):
    cup = PlayerPosition(name='Cup', team_organization_id=club['team'])
    db.session.add(PlayAssignment(play_id=club['Cup'], position=cup, instructions='Stop the swing.',
                                  team_organization_id=club['team'], order=1))
    db.session.commit()
    p = client(app, club, 'player')
    assert 'Pick your usual role' in text(p.get(f'/playbook/plays/{club["Cup"]}'))
    p.post('/playbook/roles/mine', data={'position_id': cup.id})
    assert PlayerUsualRole.query.one().position_id == cup.id
    page = text(p.get(f'/playbook/plays/{club["Cup"]}'))
    assert 'Your role: Cup' in page
    assert 'You (Cup):' in text(p.get('/playbook/cards'))
    roles = text(p.get('/playbook/roles'))
    assert 'Stop the swing.' in roles and 'Not my role' in roles
    p.post('/playbook/roles/mine', data={'position_id': ''})
    assert PlayerUsualRole.query.count() == 0
    # Another team's role can't be picked
    theirs = PlayerPosition(name='X', team_organization_id=club['other'])
    db.session.add(theirs)
    db.session.commit()
    assert p.post('/playbook/roles/mine', data={'position_id': theirs.id}).status_code == 404


def test_learning_plays(app, club):
    c = client(app, club, 'coach')
    r = c.post(f'/playbook/plays/{club["Hammer"]}/learners', data={'due_date': '2026-11-14', 'note': 'For Nationals'})
    assert r.status_code == 302 and PlayToLearn.query.one().due_date == date(2026, 11, 14)

    welcomed(club['player'])
    p = client(app, club, 'player')
    page = text(p.get('/playbook/'))
    assert 'To learn' in page and 'Learn by Sat 14 Nov' in page and 'For Nationals' in page
    assert 'Play to learn · learn by Sat 14 Nov' in text(p.get('/'))
    r = p.post(f'/playbook/plays/{club["Hammer"]}/learned', data={'read': '1'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.get_json() == {'read': True} and PlayLearned.query.count() == 1
    assert 'Play to learn' not in text(p.get('/'))
    assert "You've learned <strong>1</strong> of 3 plays" in text(p.get('/playbook/'))
    learners = text(c.get(f'/playbook/plays/{club["Hammer"]}/learners'))
    assert 'Learned' in learners and 'Not yet' in learners
    c.post(f'/playbook/plays/{club["Hammer"]}/unassign')
    assert PlayToLearn.query.count() == 0


def test_session_plans_keep_their_plays(app, club):
    session = SessionPlan(title='Tuesday', date=date(2026, 11, 3), team_organization_id=club['team'])
    db.session.add(session)
    db.session.commit()
    c = client(app, club, 'coach')
    r = c.post(f'/sessions/{session.id}/add_component', data={
        'title': 'Hammer reps', 'order': 1, 'component_type': 'drill', 'drill_id': 0,
        'plays': [club['Hammer']]})
    assert r.status_code == 302, text(r)
    component = SessionComponent.query.one()
    assert [p.id for p in component.plays] == [club['Hammer']]
    assert 'Practised: Tuesday' in text(client(app, club, 'player').get(f'/playbook/plays/{club["Hammer"]}'))
    form_page = text(c.get(f'/sessions/edit_component/{component.id}'))
    assert f'<option selected value="{club["Hammer"]}">' in form_page
    c.post(f'/sessions/edit_component/{component.id}', data={'title': 'Hammer reps', 'order': 1,
                                                            'component_type': 'drill', 'drill_id': 0, 'plays': []})
    db.session.expire_all()
    assert SessionComponent.query.one().plays.count() == 0
