"""Clip library: saving clips, hiding them from players and sharing them."""
import pytest

from app import db
from app.models.annotation import AnnotationTag, ClipAnnotation
from app.models.clip import Clip
from app.models.game import Game
from app.models.point import Point
from tests import stats_data
from tests.test_team_isolation import make_user

YOUTUBE = 'https://www.youtube.com/watch?v=abc123XYZ_-'


@pytest.fixture
def herd(app):
    team = stats_data.build_team()
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    game = Game(opponent='Rival', youtube_link='https://youtu.be/gameVid', team_organization_id=team.id)
    db.session.add(game)
    db.session.flush()
    point = Point(game_id=game.id, point_number=3, our_line_type='O-line',
                  starting_position='offense', team_organization_id=team.id)
    hidden = Clip(title='Hidden clip', game_id=game.id, youtube_link=YOUTUBE,
                  is_hidden=True, team_organization_id=team.id)
    shown = Clip(title='Shown clip', game_id=game.id, youtube_link=YOUTUBE,
                 start_time=30, end_time=90, team_organization_id=team.id)
    db.session.add_all([point, hidden, shown])
    db.session.flush()
    db.session.add(ClipAnnotation(clip_id=hidden.id, timestamp=5, title='Secret note',
                                  visibility='team', team_organization_id=team.id))
    other_tag = AnnotationTag(name='Other tag', team_organization_id=other.id)
    own_tag = AnnotationTag(name='Own tag', team_organization_id=team.id)
    db.session.add_all([other_tag, own_tag])
    ids = {'team': team.id, 'game': game.id, 'point': point.id,
           'hidden': hidden.id, 'shown': shown.id}
    for role in ('admin', 'coach', 'player'):
        ids[role] = make_user(team, role, role).id
    db.session.commit()
    ids.update(other_tag=other_tag.id, own_tag=own_tag.id)
    return ids


def client(app, herd, who):
    return stats_data.Client(app, herd[who], herd['team'])


def clip_data(herd, **overrides):
    data = {'title': 'Break mark', 'game_id': herd['game'], 'point_id': herd['point'],
            'video_source': 'youtube', 'youtube_link': YOUTUBE,
            'start_time': '10', 'end_time': '20', 'is_featured': 'y'}
    data.update(overrides)
    return data


def test_add_clip_keeps_point_and_featured(app, herd):
    r = client(app, herd, 'admin').post('/clips/add_clip', data=clip_data(herd))
    assert r.status_code == 302
    clip = Clip.query.filter_by(title='Break mark').one()
    assert clip.point_id == herd['point']
    assert clip.is_featured


def test_add_clip_rejects_a_point_from_another_game(app, herd):
    other_game = Game(opponent='Elsewhere', team_organization_id=herd['team'])
    db.session.add(other_game)
    db.session.commit()
    r = client(app, herd, 'admin').post(
        '/clips/add_clip', data=clip_data(herd, game_id=other_game.id))
    assert r.status_code == 200
    assert Clip.query.filter_by(title='Break mark').count() == 0


def test_edit_clip_saves_source_point_and_featured(app, herd):
    c = client(app, herd, 'admin')
    body = c.get(f"/clips/edit/{herd['shown']}").get_data(as_text=True)
    assert 'Point 3' in body and 'Featured Clip' in body
    r = c.post(f"/clips/edit/{herd['shown']}",
               data=clip_data(herd, title='Shown clip', video_source='veo',
                              youtube_link='https://app.veo.co/matches/abc-123'))
    assert r.status_code == 302
    clip = db.session.get(Clip, herd['shown'])
    assert (clip.video_source, clip.point_id, clip.is_featured) == ('veo', herd['point'], True)


@pytest.mark.parametrize('url', [
    '/clips/{hidden}', '/clips/api/clip/{hidden}/annotations', '/clips/{hidden}/segments',
    '/clips/export_annotations_md/{hidden}', '/clips/export_annotations_csv/{hidden}',
    '/clips/{hidden}/annotation/add',
])
def test_players_cannot_open_hidden_clips(app, herd, url):
    url = url.format(**herd)
    assert client(app, herd, 'player').get(url).status_code == 404
    assert client(app, herd, 'coach').get(url).status_code == 200


@pytest.mark.parametrize('url', ['/clips/', '/clips/game/{game}', '/clips/point/{point}'])
def test_clip_lists_leave_hidden_clips_out_for_players(app, herd, url):
    db.session.get(Clip, herd['hidden']).point_id = herd['point']
    db.session.commit()
    url = url.format(**herd)
    assert 'Hidden clip' not in client(app, herd, 'player').get(url).get_data(as_text=True)
    assert 'Hidden clip' in client(app, herd, 'coach').get(url).get_data(as_text=True)


def test_views_count_once_per_session(app, herd):
    c = client(app, herd, 'player')
    for _ in range(3):
        assert c.get(f"/clips/{herd['shown']}").status_code == 200
    assert db.session.get(Clip, herd['shown']).view_count == 1


def test_bad_creator_filter_is_ignored(app, herd):
    r = client(app, herd, 'player').get(f"/clips/{herd['shown']}?creator_filter=abc")
    assert r.status_code == 200


def share_url(c, clip_id):
    r = c.post(f'/clips/{clip_id}/share_link')
    return r.status_code, r.get_json()


def test_share_link_plays_the_clip_and_can_be_revoked(app, herd):
    c = client(app, herd, 'coach')
    status, data = share_url(c, herd['shown'])
    assert status == 200
    anon = app.test_client()
    body = anon.get(data['url']).get_data(as_text=True)
    assert 'youtube.com/embed/abc123XYZ_-?start=30&amp;end=90' in body

    assert c.post(f"/clips/{herd['shown']}/revoke_share_links").status_code == 302
    assert anon.get(data['url']).status_code == 410
    _, fresh = share_url(c, herd['shown'])
    assert anon.get(fresh['url']).status_code == 200


def test_hidden_clips_cannot_be_shared(app, herd):
    c = client(app, herd, 'coach')
    status, _ = share_url(c, herd['hidden'])
    assert status == 400
    clip = db.session.get(Clip, herd['shown'])
    _, data = share_url(c, clip.id)
    clip.is_hidden = True
    db.session.commit()
    assert app.test_client().get(data['url']).status_code == 404


def test_veo_clips_embed_on_share_page(app, herd):
    clip = db.session.get(Clip, herd['shown'])
    clip.video_source, clip.youtube_link = 'veo', 'https://app.veo.co/matches/abc-123'
    db.session.commit()
    _, data = share_url(client(app, herd, 'coach'), clip.id)
    body = app.test_client().get(data['url']).get_data(as_text=True)
    assert 'https://app.veo.co/embed/abc-123' in body


def test_annotation_tag_parent_must_be_your_team(app, herd):
    r = client(app, herd, 'admin').post(
        f"/clips/annotation-tags/edit/{herd['own_tag']}",
        data={'name': 'Own tag', 'parent_tag_id': herd['other_tag'], 'is_active': 'y'})
    assert r.status_code == 200
    assert db.session.get(AnnotationTag, herd['own_tag']).parent_tag_id is None


@pytest.fixture
def notes(app, herd):
    """One annotation per visibility on the shown clip; 'Aimed' targets the player."""
    other_player = make_user(db.session.get(Clip, herd['shown']).team_organization, 'player2', 'player')
    rows = [('Team note', 'team', herd['coach'], None),
            ('Coaches note', 'coaches', herd['coach'], None),
            ('Aimed note', 'specific', herd['coach'], herd['player']),
            ('Aimed elsewhere', 'specific', herd['coach'], other_player.id),
            ('Own private', 'private', herd['player'], None),
            ('Coach private', 'private', herd['coach'], None)]
    for i, (title, visibility, author, target) in enumerate(rows):
        db.session.add(ClipAnnotation(clip_id=herd['shown'], timestamp=i, title=title, visibility=visibility,
                                      user_id=author, target_user_id=target, team_organization_id=herd['team']))
    db.session.commit()
    return {title for title, *_ in rows}


@pytest.mark.parametrize('url', ['/clips/{shown}', '/clips/api/clip/{shown}/annotations',
                                 '/clips/export_annotations_md/{shown}', '/clips/export_annotations_csv/{shown}'])
def test_annotation_visibility_by_role(app, herd, notes, url):
    url = url.format(**herd)
    player_sees = {'Team note', 'Aimed note', 'Own private'}
    body = client(app, herd, 'player').get(url).get_data(as_text=True)
    assert {n for n in notes if n in body} == player_sees
    body = client(app, herd, 'coach').get(url).get_data(as_text=True)
    assert {n for n in notes if n in body} == notes


def test_shared_page_shows_only_team_notes(app, herd, notes):
    _, data = share_url(client(app, herd, 'coach'), herd['shown'])
    body = app.test_client().get(data['url']).get_data(as_text=True)
    assert {n for n in notes if n in body} == {'Team note'}


@pytest.mark.parametrize('link', [
    'https://www.youtube.com/watch?v=abc123XYZ_-&t=4', 'https://youtu.be/abc123XYZ_-?si=x',
    'https://www.youtube.com/shorts/abc123XYZ_-', 'https://www.youtube.com/live/abc123XYZ_-',
    'https://www.youtube.com/embed/abc123XYZ_-', 'https://m.youtube.com/watch?v=abc123XYZ_-',
])
def test_youtube_links_embed(link):
    from app.utils.clip_video import youtube_embed_url, youtube_timestamp_link
    assert youtube_embed_url(link, 5, 9) == 'https://www.youtube.com/embed/abc123XYZ_-?start=5&end=9'
    assert youtube_timestamp_link(link, 12) == 'https://www.youtube.com/watch?v=abc123XYZ_-&t=12s'


def test_non_youtube_links_do_not_embed():
    from app.utils.clip_video import youtube_embed_url
    for link in (None, '', 'https://vimeo.com/123', 'https://www.youtube.com/watch?v=<script>'):
        assert youtube_embed_url(link) is None
