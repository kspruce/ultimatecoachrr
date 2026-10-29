"""Team roles: coaches and captains set up the team's roles and who plays
each one this season (first choice first); players say which they'd like;
roles carry into a new season without changing the old one; the playbook
says what each role does in a play."""
from datetime import date

import pytest

from app import db
from app.models.playbook import Play, PlayAssignment, PlayerPosition
from app.models.season import Season, SeasonRoster
from app.models.team_role import PlayerRole
from app.utils import roles as team_roles
from app.utils.season import start_new_season
from tests import stats_data
from tests.test_feedback import make_user

YEAR = date.today().year


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    season = Season(team_organization_id=team.id, year=YEAR, start_date=date(YEAR, 1, 1),
                    end_date=date(YEAR, 12, 31), is_current=True)
    db.session.add(season)
    db.session.commit()
    players = stats_data.build_players(team, 4)  # women and men alternately, on the season's roster
    coach = make_user(team, 'coach', 'coach')
    captain = make_user(team, 'captain', 'captain')
    ann = make_user(team, 'ann', 'player', players[0])
    other_coach = make_user(other, 'othercoach', 'coach')
    db.session.commit()
    return {'team': team.id, 'other': other.id, 'season': season.id, 'players': [p.id for p in players],
            'coach': stats_data.Client(app, coach.id, team.id),
            'captain': stats_data.Client(app, captain.id, team.id),
            'ann': stats_data.Client(app, ann.id, team.id),
            'other_coach': stats_data.Client(app, other_coach.id, other.id)}


def role(club, name):
    return PlayerPosition.query.filter_by(team_organization_id=club['team'], name=name).one()


def holders(role_id):
    db.session.expire_all()
    rows = (PlayerRole.query.filter_by(role_id=role_id, kind='assigned').order_by(PlayerRole.depth).all())
    return [(r.roster.player_id, r.depth) for r in rows]


def page(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def test_start_with_suggested_roles_once(app, club):
    assert 'Start with suggested roles' in page(club['coach'], '/team/roles/')
    club['coach'].post('/team/roles/starter')
    club['coach'].post('/team/roles/starter')
    roles = team_roles.team_roles(club['team'])
    assert len(roles) == len(team_roles.STARTER_ROLES)
    assert [r.line for r in roles][:5] == ['O'] * 5 and roles[0].name == 'Centre handler'
    body = page(club['coach'], '/team/roles/')
    assert 'O-line' in body and 'D-line' in body and 'Nobody yet' in body
    assert 'Not in a role yet (4)' in body


def test_depth_order_and_main_role(app, club):
    c = club['coach']
    c.post('/team/roles/add', data={'name': 'Initiation cutter', 'line': 'O'})
    c.post('/team/roles/add', data={'name': 'Deep', 'line': 'D', 'description': 'Protects the deep space'})
    cutter, deep = role(club, 'Initiation cutter'), role(club, 'Deep')
    p1, p2, p3, _ = club['players']
    for pid in (p1, p2, p3):
        c.post(f'/team/roles/{cutter.id}/assign', data={'player_id': pid})
    c.post(f'/team/roles/{deep.id}/assign', data={'player_id': p1})
    assert holders(cutter.id) == [(p1, 1), (p2, 2), (p3, 3)]

    # The first role someone gets is their main one
    rows = {r.role_id: r for r in PlayerRole.query.join(SeasonRoster).filter(SeasonRoster.player_id == p1)}
    assert rows[cutter.id].is_main and not rows[deep.id].is_main

    # Reorder, make Deep p1's main role, take p1 out of the cutter role
    third = PlayerRole.query.join(SeasonRoster).filter(SeasonRoster.player_id == p3, PlayerRole.role_id == cutter.id).one()
    c.post(f'/team/roles/holder/{third.id}/up')
    assert holders(cutter.id) == [(p1, 1), (p3, 2), (p2, 3)]
    c.post(f"/team/roles/holder/{rows[deep.id].id}/main")
    c.post(f"/team/roles/holder/{rows[cutter.id].id}/remove")
    assert holders(cutter.id) == [(p3, 1), (p2, 2)]
    db.session.expire_all()
    assert db.session.get(PlayerRole, rows[deep.id].id).is_main

    body = page(c, '/team/roles/')
    assert 'Only one player' in body  # Deep has just p1
    roster = page(c, '/team/')
    assert 'Deep' in roster


def test_mixed_teams_hear_when_a_role_is_all_one_gender(app, club):
    c = club['coach']
    c.post('/team/roles/add', data={'name': 'Cup', 'line': 'D'})
    cup = role(club, 'Cup')
    for pid in club['players'][1::2]:  # the men
        c.post(f'/team/roles/{cup.id}/assign', data={'player_id': pid})
    assert 'Only men' in page(c, '/team/roles/')


def test_who_can_change_roles(app, club):
    club['captain'].post('/team/roles/add', data={'name': 'Handler mark', 'line': 'D'})
    mark = role(club, 'Handler mark')  # captains can
    club['captain'].post(f'/team/roles/{mark.id}/assign', data={'player_id': club['players'][0]})
    assert holders(mark.id) == [(club['players'][0], 1)]

    assert club['ann'].get('/team/roles/').status_code == 302
    club['ann'].post('/team/roles/add', data={'name': 'Mine'})
    assert PlayerPosition.query.filter_by(name='Mine').count() == 0
    r = club['ann'].post(f"/team/roles/player/{club['players'][0]}", data={'kind': 'assigned', 'role_id': mark.id})
    assert r.status_code == 403

    outsider = club['other_coach']
    assert outsider.post(f'/team/roles/{mark.id}/edit', data={'name': 'Hacked'}).status_code == 404
    assert outsider.post(f'/team/roles/{mark.id}/assign', data={'player_id': club['players'][1]}).status_code == 404
    row = PlayerRole.query.one()
    assert outsider.post(f'/team/roles/holder/{row.id}/remove').status_code == 404
    assert outsider.post(f"/team/roles/player/{club['players'][0]}", data={'kind': 'assigned'}).status_code == 404
    db.session.expire_all()
    assert db.session.get(PlayerPosition, mark.id).name == 'Handler mark' and PlayerRole.query.count() == 1


def test_profile_roles_and_preferences(app, club):
    c = club['coach']
    for name, line in (('Centre handler', 'O'), ('Deep cutter', 'O'), ('Cup', 'D')):
        c.post('/team/roles/add', data={'name': name, 'line': line})
    handler, deep, cup = role(club, 'Centre handler'), role(club, 'Deep cutter'), role(club, 'Cup')
    ann_id = club['players'][0]

    # The player says what they'd like; they can't give themselves roles
    club['ann'].post(f'/team/roles/player/{ann_id}', data={'kind': 'preferred', 'role_id': [deep.id, cup.id]})
    mine = page(club['ann'], f'/team/player/{ann_id}')
    assert 'You’d like: Deep cutter, Cup' in mine and 'Set roles' not in mine
    assert 'Would like it: Herd Player 01' in page(c, '/team/roles/')

    # The coach sets them, with a main role
    c.post(f'/team/roles/player/{ann_id}', data={'kind': 'assigned', 'role_id': [handler.id, cup.id],
                                                 'main_role_id': cup.id})
    db.session.expire_all()
    rows = {r.role_id: r for r in PlayerRole.query.filter_by(kind='assigned')}
    assert set(rows) == {handler.id, cup.id} and rows[cup.id].is_main and not rows[handler.id].is_main
    profile = page(c, f'/team/player/{ann_id}')
    assert 'Set roles' in profile and 'Centre handler' in profile
    # Wanting a role you already have isn't flagged on the board
    assert 'Would like it' in page(c, '/team/roles/')  # (Deep cutter still)

    c.post(f'/team/roles/player/{ann_id}', data={'kind': 'assigned', 'role_id': [handler.id]})
    db.session.expire_all()
    only = PlayerRole.query.filter_by(kind='assigned').one()
    assert only.role_id == handler.id and only.is_main


def test_roles_are_season_by_season(app, club):
    c = club['coach']
    c.post('/team/roles/add', data={'name': 'Deep cutter', 'line': 'O'})
    c.post('/team/roles/add', data={'name': 'Cup', 'line': 'D'})
    deep, cup = role(club, 'Deep cutter'), role(club, 'Cup')
    p1, p2, p3, p4 = club['players']
    for pid in (p1, p2, p3):
        c.post(f'/team/roles/{deep.id}/assign', data={'player_id': pid})
    c.post(f'/team/roles/player/{p4}', data={'kind': 'preferred', 'role_id': [cup.id]})

    # A new season: p2 has left; everyone else keeps their roles, in order
    old = db.session.get(Season, club['season'])
    new = start_new_season(club['team'], YEAR + 1, date(YEAR + 1, 1, 1), date(YEAR + 1, 12, 31),
                           [{'player_id': pid} for pid in (p1, p3, p4)], previous=old)
    db.session.commit()
    new_id = new.id

    def season_holders(season_id):
        db.session.expire_all()
        return [(r.roster.player_id, r.depth) for r in PlayerRole.query.join(SeasonRoster).filter(
            SeasonRoster.season_id == season_id, PlayerRole.role_id == deep.id).order_by(PlayerRole.depth)]

    assert season_holders(new_id) == [(p1, 1), (p3, 2)]
    assert PlayerRole.query.join(SeasonRoster).filter(SeasonRoster.season_id == new_id,
                                                      PlayerRole.kind == 'preferred').count() == 1

    # Changing this season's roles leaves last season's alone
    p3_row = PlayerRole.query.join(SeasonRoster).filter(SeasonRoster.season_id == new_id,
                                                        SeasonRoster.player_id == p3).one()
    c.post(f'/team/roles/holder/{p3_row.id}/remove')
    assert season_holders(new_id) == [(p1, 1)]
    assert season_holders(club['season']) == [(p1, 1), (p2, 2), (p3, 3)]
    assert f'{YEAR}: Deep cutter' in page(c, f'/team/player/{p3}')

    # Someone not on this season's roster can't be given a role in it
    r = c.post(f'/team/roles/{deep.id}/assign', data={'player_id': p2}, follow_redirects=True)
    assert 'isn’t on the' in r.get_data(as_text=True)
    assert season_holders(new_id) == [(p1, 1)]


def test_the_playbook_uses_roles(app, club):
    c = club['coach']  # a coach, not an admin
    c.post('/team/roles/add', data={'name': 'Initiation cutter', 'line': 'O'})
    c.post('/team/roles/add', data={'name': 'Centre handler', 'line': 'O'})
    cutter = role(club, 'Initiation cutter')
    play = Play(name='Side stack', type='offense', team_organization_id=club['team'])
    db.session.add(play)
    db.session.commit()
    form = page(c, f'/playbook/plays/{play.id}/edit')
    assert f'<option value="{cutter.id}" >Initiation cutter</option>' in form and 'label="O-line"' in form
    c.post(f'/playbook/plays/{play.id}/edit', data={'name': 'Side stack', 'type': 'offense', 'status': 'active',
                                                    'role_id': [cutter.id], 'role_text': ['Go deep first'],
                                                    'action': 'save'})
    assert PlayAssignment.query.one().position_id == cutter.id
    assert 'In 1 play' in page(c, '/team/roles/')
    by_role = page(c, '/playbook/positions')
    assert by_role.index('Initiation cutter') < by_role.index('Centre handler')  # the Roles page's order

    c.post(f'/team/roles/{cutter.id}/delete')
    assert PlayAssignment.query.count() == 0 and PlayerPosition.query.filter_by(name='Initiation cutter').count() == 0


# ── Roles in a play's drawing ──────────────────────────────────────────────

def drawn_play(club, roles_by_label, stages=1):
    """A play drawn in the editor whose players have roles: {label: role id}."""
    import json
    from app.models.drill import DrillDiagram
    objects = [{'type': 'group', 'herdType': 'player-o', 'herdId': f'p{n}', 'herdLabel': label,
                'herdRole': role_id, 'left': 100 * n, 'top': 100}
               for n, (label, role_id) in enumerate(roles_by_label.items(), start=1)]
    state = {'version': 2, 'field': {}, 'stages': [{'name': f'Stage {i + 1}', 'objects': objects}
                                                   for i in range(stages)]}
    play = Play(name='Side stack', type='offense', team_organization_id=club['team'])
    db.session.add(play)
    db.session.flush()
    for i in range(stages):
        db.session.add(DrillDiagram(play_id=play.id, order=1000 + i, team_organization_id=club['team'],
                                    image_url='/x.png', source='Play editor',
                                    editor_json=json.dumps(state) if i == 0 else json.dumps({'stage': i + 1})))
    db.session.commit()
    return play.id


def test_drawing_role_ids():
    state = {'stages': [{'objects': [{'herdRole': 3}, {'herdRole': '4'}, {'herdRole': None}, {}]},
                        {'objects': [{'herdRole': 3}, {'herdRole': 'x'}]}]}
    assert team_roles.drawing_role_ids(state) == {3, 4}
    assert team_roles.drawing_role_ids(None) == set()


def test_pick_a_role_on_the_play(app, club):
    c = club['coach']
    for name in ('Initiation cutter', 'Centre handler', 'Deep'):
        c.post('/team/roles/add', data={'name': name, 'line': 'O'})
    cutter, handler, deep = role(club, 'Initiation cutter'), role(club, 'Centre handler'), role(club, 'Deep')
    play_id = drawn_play(club, {'C1': cutter.id, 'H1': handler.id})
    db.session.add(PlayAssignment(play_id=play_id, position_id=deep.id, instructions='Stay home',
                                  team_organization_id=club['team']))
    db.session.commit()

    # The editor (captains and admins draw plays) knows the team's roles
    editor = page(club['captain'], f'/playbook/plays/{play_id}/draw')
    assert 'id="play-roles"' in editor and 'Initiation cutter' in editor

    # One stage, but players have roles: the diagram is drawn so a role can be picked
    body = page(club['ann'], f'/playbook/plays/{play_id}?role={cutter.id}')
    assert 'data-animation="role"' in body and f'<option value="{cutter.id}" selected>' in body
    assert body.count("Show this role's path") == 2  # cutter and handler are drawn; Deep only has words
    assert 'Stay home' in body and 'drill_viewer.js' in body

    # By role: every play the role is in, with a link that picks out its path
    by_role = page(club['ann'], f'/playbook/positions/{cutter.id}')
    assert 'Side stack' in by_role and f'role={cutter.id}' in by_role
    assert 'Side stack' in page(club['ann'], f'/playbook/positions/{deep.id}')
    assert 'In 1 play' in page(c, '/team/roles/')


def test_players_find_their_plays(app, club):
    c = club['coach']
    c.post('/team/roles/add', data={'name': 'Initiation cutter', 'line': 'O'})
    cutter = role(club, 'Initiation cutter')
    play_id = drawn_play(club, {'C1': cutter.id})
    ann_id = club['players'][0]
    c.post(f'/team/roles/{cutter.id}/assign', data={'player_id': ann_id})

    # "Plays by role" opens on their main role
    r = club['ann'].get('/playbook/positions')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/playbook/positions/{cutter.id}')
    # Their profile lists the plays, and game-day cards link to their path
    profile = page(club['ann'], f'/team/player/{ann_id}')
    assert f'/playbook/plays/{play_id}?role={cutter.id}' in profile
    cards = page(club['ann'], '/playbook/cards')
    assert 'Your path' in cards and f'role={cutter.id}' in cards
    # Someone without the role gets the ordinary link
    assert 'Your path' not in page(c, '/playbook/cards')
