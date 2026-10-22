"""Clip playlists: coaches line clips up, the team watches them in order."""
import json
import re

import pytest

from app import db
from app.models.clip import Clip
from app.models.clip_playlist import ClipPlaylist, ClipPlaylistItem
from tests import stats_data
from tests.test_clips import YOUTUBE, client, herd  # noqa: F401
from tests.test_team_isolation import make_user


@pytest.fixture
def playlist(app, herd):
    """'Film night' with the shown clip, then the hidden clip, then a Veo clip."""
    veo = Clip(title='Veo clip', video_source='veo', youtube_link='https://app.veo.co/matches/abc-123',
               start_time=60, end_time=75, team_organization_id=herd['team'])
    db.session.add(veo)
    db.session.flush()
    playlist = ClipPlaylist(title='Film night', team_organization_id=herd['team'])
    for position, clip_id in enumerate((herd['shown'], herd['hidden'], veo.id)):
        playlist.items.append(ClipPlaylistItem(clip_id=clip_id, position=position,
                                               team_organization_id=herd['team']))
    db.session.add(playlist)
    db.session.commit()
    return {'id': playlist.id, 'veo': veo.id}


def order(playlist_id):
    db.session.expire_all()
    return [item.clip.title for item in db.session.get(ClipPlaylist, playlist_id).items]


def tracks(body):
    return json.loads(re.search(r'tracks: (\[.*?\]), startIndex', body).group(1))


def test_coach_builds_a_playlist(app, herd):
    c = client(app, herd, 'coach')
    r = c.post(f"/clips/playlists/new?clip_id={herd['shown']}", data={'title': 'Zone D', 'description': 'Homework'})
    assert r.status_code == 302
    playlist = ClipPlaylist.query.filter_by(title='Zone D').one()
    assert c.post(f'/clips/playlists/{playlist.id}/items', data={'clip_id': herd['hidden']}).status_code == 302
    c.post(f'/clips/playlists/{playlist.id}/items', data={'clip_id': herd['shown']})  # already there
    assert order(playlist.id) == ['Shown clip', 'Hidden clip']


def test_reorder_remove_and_notes(app, herd, playlist):
    c = client(app, herd, 'coach')
    items = [i.id for i in db.session.get(ClipPlaylist, playlist['id']).items]
    base = f"/clips/playlists/{playlist['id']}"
    c.post(f'{base}/items/{items[2]}/move/up')
    assert order(playlist['id']) == ['Shown clip', 'Veo clip', 'Hidden clip']
    c.post(f'{base}/items/{items[0]}/move/up')  # already first: nothing changes
    c.post(f'{base}/items/{items[0]}/move/down')
    assert order(playlist['id']) == ['Veo clip', 'Shown clip', 'Hidden clip']
    c.post(f'{base}/items/{items[1]}/remove')
    assert order(playlist['id']) == ['Veo clip', 'Shown clip']
    assert [i.position for i in db.session.get(ClipPlaylist, playlist['id']).items] == [0, 1]
    c.post(f'{base}/notes', data={f'note-{items[0]}': '  Watch the force  ', f'note-{items[2]}': ''})
    db.session.expire_all()
    assert db.session.get(ClipPlaylistItem, items[0]).note == 'Watch the force'
    assert db.session.get(ClipPlaylistItem, items[2]).note is None


def test_players_watch_but_do_not_see_hidden_clips(app, herd, playlist):
    body = client(app, herd, 'player').get(f"/clips/playlists/{playlist['id']}").get_data(as_text=True)
    played = tracks(body)
    assert [t['title'] for t in played] == ['Shown clip', 'Veo clip']
    assert played[0] | {'id': 0, 'clip_url': ''} == {
        'id': 0, 'clip_url': '', 'title': 'Shown clip', 'note': '', 'video_id': 'abc123XYZ_-', 'veo_link': None,
        'start': 30, 'end': 90, 'hidden': False}
    assert played[1]['video_id'] is None and played[1]['veo_link'] == 'https://app.veo.co/matches/abc-123'
    listing = client(app, herd, 'player').get('/clips/playlists').get_data(as_text=True)
    assert 'Film night' in listing and '2 clips' in listing
    coach = client(app, herd, 'coach').get(f"/clips/playlists/{playlist['id']}").get_data(as_text=True)
    assert [t['title'] for t in tracks(coach)] == ['Shown clip', 'Hidden clip', 'Veo clip']


@pytest.mark.parametrize('method, url', [
    ('get', '/clips/playlists/new'), ('get', '/clips/playlists/{id}/edit'),
    ('post', '/clips/playlists/{id}/delete'), ('post', '/clips/playlists/{id}/items'),
    ('post', '/clips/playlists/{id}/notes'),
])
def test_players_cannot_change_playlists(app, herd, playlist, method, url):
    r = getattr(client(app, herd, 'player'), method)(url.format(**playlist), data={'clip_id': herd['shown']})
    assert r.status_code == 403
    assert len(order(playlist['id'])) == 3


def test_other_teams_cannot_see_or_add_to_playlists(app, herd, playlist):
    other = stats_data.build_team('Rival Club', 'rival-club')
    coach = make_user(other, 'other-coach', 'coach')
    other_clip = Clip(title='Other clip', youtube_link=YOUTUBE, team_organization_id=other.id)
    db.session.add(other_clip)
    db.session.commit()
    c = stats_data.Client(app, coach.id, other.id)
    assert c.get(f"/clips/playlists/{playlist['id']}").status_code == 404
    assert c.post(f"/clips/playlists/{playlist['id']}/items", data={'clip_id': other_clip.id}).status_code == 404
    assert 'Film night' not in c.get('/clips/playlists').get_data(as_text=True)
    # and our coach can't put the other team's clip in our playlist
    client(app, herd, 'coach').post(f"/clips/playlists/{playlist['id']}/items", data={'clip_id': other_clip.id})
    assert 'Other clip' not in order(playlist['id'])


def test_deleting_a_clip_takes_it_out_of_playlists(app, herd, playlist):
    assert client(app, herd, 'admin').post(f"/clips/delete/{herd['hidden']}").status_code == 302
    assert order(playlist['id']) == ['Shown clip', 'Veo clip']


def test_deleting_a_playlist_keeps_the_clips(app, herd, playlist):
    assert client(app, herd, 'coach').post(f"/clips/playlists/{playlist['id']}/delete").status_code == 302
    assert db.session.get(ClipPlaylist, playlist['id']) is None
    assert ClipPlaylistItem.query.count() == 0 and db.session.get(Clip, herd['shown'])


def test_clip_page_offers_playlists_to_coaches(app, herd, playlist):
    url = f"/clips/{playlist['veo']}"
    body = client(app, herd, 'coach').get(url).get_data(as_text=True)
    assert 'Add to playlist' in body and 'bi-check2 me-1"></i>Film night' in body
    assert 'Add to playlist' not in client(app, herd, 'player').get(url).get_data(as_text=True)


def test_start_at_a_chosen_item(app, herd, playlist):
    second = db.session.get(ClipPlaylist, playlist['id']).items[2].id
    body = client(app, herd, 'coach').get(f"/clips/playlists/{playlist['id']}?item={second}").get_data(as_text=True)
    assert 'startIndex: 2' in body
