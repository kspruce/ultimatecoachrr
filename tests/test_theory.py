"""Theory hub: the feature switch, who can see and change what, drafts,
sections and tags per team, photos, videos, drills, reading progress and
assigned reading."""
import base64
import io
import json
from datetime import date

import pytest
from PIL import Image

from app import db
from app.models.drill import SavedDrill
from app.models.team_settings import TeamSettings
from app.models.theory import (TheoryAssignment, TheoryImage, TheoryRead, TheorySection, TheoryTag, TheoryTopic,
                               TheoryVideo, video_embed_url)
from app.utils import theory as hub
from tests import stats_data
from tests.test_teams import make_user


@pytest.fixture
def herd(app):
    team = stats_data.build_team('Herd', 'herd')
    other = stats_data.build_team('Other', 'other')
    db.session.add_all([TeamSettings(team_id=team.id), TeamSettings(team_id=other.id)])
    db.session.commit()
    section = TheorySection(name='Defence', slug='defence', order=1, team_organization_id=team.id)
    db.session.add(section)
    db.session.flush()
    topics = [TheoryTopic(section_id=section.id, name=name, content=f'## {name}\n\nAbout {name.lower()}.',
                          order=n, team_organization_id=team.id, published=published)
              for n, (name, published) in enumerate([('Force', True), ('Cup', True), ('Secret plan', False)], start=1)]
    db.session.add_all(topics)
    other_section = TheorySection(name='Defence', slug='defence', order=1, team_organization_id=other.id)
    db.session.add(other_section)
    db.session.flush()
    other_topic = TheoryTopic(section_id=other_section.id, name='Their zone', content='x', team_organization_id=other.id)
    db.session.add(other_topic)
    db.session.commit()
    return {
        'team': team.id, 'other': other.id, 'section': section.id,
        'force': topics[0].id, 'cup': topics[1].id, 'draft': topics[2].id, 'other_topic': other_topic.id,
        'coach': make_user(team, 'coach', role='coach').id,
        'captain': make_user(team, 'captain', role='captain').id,
        'player': make_user(team, 'player', role='player').id,
        'player2': make_user(team, 'player2', role='player').id,
        'other_coach': make_user(other, 'othercoach', role='coach').id,
    }


def welcomed(user_id, role='player'):
    """Past the first-visit welcome, so / is the dashboard."""
    from app.models.onboarding import UserOnboarding
    db.session.add(UserOnboarding(user_id=user_id, welcomed_role=role, completed_steps=[]))
    db.session.commit()


def client(app, herd, who, team='team'):
    return stats_data.Client(app, herd[who], herd[team])


def fresh(model, row_id):
    db.session.expire_all()  # the requests ran in their own sessions
    return db.session.get(model, row_id)


def text(response):
    return response.get_data(as_text=True)


def photo(size=(3000, 2000), fmt='JPEG', exif_rotate=False):
    img = Image.new('RGB', size, (200, 30, 30))
    buf = io.BytesIO()
    kw = {}
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # taken on its side: turn 90° clockwise to view
        kw['exif'] = exif
    img.save(buf, format=fmt, **kw)
    buf.seek(0)
    return buf


def topic_form(herd, **kw):
    data = {'name': 'Mark the force', 'section_id': herd['section'], 'content': '## Why\n\nBecause.',
            'image_url': '', 'tags': '', 'action': 'publish'}
    data.update(kw)
    return data


# ── Switching it off ──────────────────────────────────────────────────────

def test_off_means_every_page_is_404_and_no_nav(app, herd):
    TeamSettings.query.filter_by(team_id=herd['team']).one().theory_enabled = False
    db.session.commit()
    c = client(app, herd, 'coach')
    for url in ('/theory/', '/theory/section/defence', f'/theory/topic/{herd["force"]}', '/theory/add_topic',
                f'/theory/topic/{herd["force"]}/readers'):
        assert c.get(url).status_code == 404, url
    assert c.post(f'/theory/topic/{herd["force"]}/read').status_code == 404
    assert 'href="/theory/"' not in text(c.get('/team/'))


def test_signed_out_goes_to_login(app, herd):
    r = app.test_client().get('/theory/')
    assert r.status_code == 302 and '/login' in r.headers['Location']


# ── Who sees what ─────────────────────────────────────────────────────────

def test_players_never_see_drafts(app, herd):
    p = client(app, herd, 'player')
    hub_page = text(p.get('/theory/'))
    assert 'Force' in hub_page and 'Secret plan' not in hub_page
    assert 'Secret plan' not in text(p.get('/theory/section/defence'))
    assert p.get(f'/theory/topic/{herd["draft"]}').status_code == 404
    assert p.post(f'/theory/topic/{herd["draft"]}/read').status_code == 404
    assert 'Secret plan' not in text(p.get('/theory/?q=secret'))

    c = client(app, herd, 'coach')
    assert 'Secret plan' in text(c.get('/theory/section/defence'))
    page = text(c.get(f'/theory/topic/{herd["draft"]}'))
    assert 'Draft: only coaches can see this.' in page


def test_players_cannot_change_anything(app, herd):
    p = client(app, herd, 'player')
    for url in ('/theory/add_topic', '/theory/add_section', f'/theory/edit_topic/{herd["force"]}',
                f'/theory/edit_section/{herd["section"]}', f'/theory/topic/{herd["force"]}/readers'):
        assert p.get(url).status_code == 403, url
    for url in (f'/theory/delete_topic/{herd["force"]}', f'/theory/delete_section/{herd["section"]}',
                f'/theory/topic/{herd["force"]}/move', f'/theory/topic/{herd["draft"]}/publish', '/theory/preview',
                '/theory/images'):
        assert p.post(url).status_code == 403, url
    assert fresh(TheoryTopic, herd['force']) is not None
    page = text(p.get(f'/theory/topic/{herd["force"]}'))
    assert '/theory/edit_topic/' not in page and 'Mark as read' in page


def test_captains_can_write(app, herd):
    c = client(app, herd, 'captain')
    assert c.get('/theory/add_topic').status_code == 200
    assert 'edit_topic' in text(c.get(f'/theory/topic/{herd["force"]}'))


def test_other_teams_topics_are_404(app, herd):
    c = client(app, herd, 'coach')
    assert c.get(f'/theory/topic/{herd["other_topic"]}').status_code == 404
    assert c.get(f'/theory/edit_topic/{herd["other_topic"]}').status_code == 404
    assert c.post(f'/theory/delete_topic/{herd["other_topic"]}').status_code == 404
    assert fresh(TheoryTopic, herd['other_topic']) is not None


# ── Writing ───────────────────────────────────────────────────────────────

def test_new_topic_from_a_section_starts_in_it(app, herd):
    second = TheorySection(name='Offence', slug='offence', order=2, team_organization_id=herd['team'])
    db.session.add(second)
    db.session.commit()
    page = text(client(app, herd, 'coach').get(f'/theory/add_topic?section_id={second.id}'))
    assert f'<option selected value="{second.id}">Offence</option>' in page


def test_save_a_draft_then_publish(app, herd):
    c = client(app, herd, 'coach')
    r = c.post('/theory/add_topic', data=topic_form(herd, content='', action='draft'))
    assert r.status_code == 302
    topic = TheoryTopic.query.filter_by(name='Mark the force').one()
    assert topic.published is False and topic.order == 4 and topic.created_by == herd['coach']
    assert 'saved=1' in r.headers['Location']
    # Publishing needs something written
    r = c.post(f'/theory/edit_topic/{topic.id}', data=topic_form(herd, content='  ', action='publish'))
    assert r.status_code == 200 and 'Write something before publishing' in text(r)
    assert fresh(TheoryTopic, topic.id).published is False
    c.post(f'/theory/edit_topic/{topic.id}', data=topic_form(herd, action='publish'))
    topic = fresh(TheoryTopic, topic.id)
    assert topic.published is True and topic.updated_by == herd['coach']
    # Saving keeps it published; "move back to drafts" doesn't
    c.post(f'/theory/edit_topic/{topic.id}', data=topic_form(herd, action='save'))
    assert fresh(TheoryTopic, topic.id).published is True
    c.post(f'/theory/edit_topic/{topic.id}', data=topic_form(herd, action='draft'))
    assert fresh(TheoryTopic, topic.id).published is False


def test_publish_button_on_a_draft(app, herd):
    c = client(app, herd, 'coach')
    assert c.post(f'/theory/topic/{herd["draft"]}/publish').status_code == 302
    assert fresh(TheoryTopic, herd['draft']).published is True


def test_edit_keeps_the_page_when_something_is_wrong(app, herd):
    c = client(app, herd, 'coach')
    r = c.post(f'/theory/edit_topic/{herd["force"]}',
               data=topic_form(herd, name='Renamed', video_url=['https://example.com/v'], video_title=['x']))
    assert r.status_code == 200 and "isn&#39;t a YouTube or Vimeo link" in text(r)
    assert 'value="Renamed"' in text(r)
    assert fresh(TheoryTopic, herd['force']).name == 'Force'


def test_moving_to_another_section_puts_it_at_the_end(app, herd):
    second = TheorySection(name='Offence', slug='offence', order=2, team_organization_id=herd['team'])
    db.session.add(second)
    db.session.flush()
    db.session.add(TheoryTopic(section_id=second.id, name='Stack', content='x', order=1, team_organization_id=herd['team']))
    db.session.commit()
    client(app, herd, 'coach').post(f'/theory/edit_topic/{herd["force"]}',
                                    data=topic_form(herd, name='Force', section_id=second.id, action='save'))
    topic = fresh(TheoryTopic, herd['force'])
    assert topic.section_id == second.id and topic.order == 2


def test_tags_and_drills_belong_to_the_team(app, herd):
    db.session.add(TheoryTag(name='Zone', team_organization_id=herd['other']))
    mine = [SavedDrill(title=f'Drill {n}', team_organization_id=herd['team']) for n in (1, 2)]
    theirs = SavedDrill(title='Their drill', team_organization_id=herd['other'])
    db.session.add_all(mine + [theirs])
    db.session.commit()
    c = client(app, herd, 'coach')
    r = c.post(f'/theory/edit_topic/{herd["force"]}', data=topic_form(
        herd, name='Force', tags='zone, Handler resets,  ZONE ,', action='save',
        related_drills=[mine[0].id, mine[1].id, theirs.id]))
    assert r.status_code == 302
    topic = fresh(TheoryTopic, herd['force'])
    assert [t.name for t in topic.tags] == ['Handler resets', 'zone']
    assert all(t.team_organization_id == herd['team'] for t in topic.tags)
    assert sorted(d.title for d in topic.related_drills) == ['Drill 1', 'Drill 2']
    # Both teams can have a "Zone" tag
    assert TheoryTag.query.filter(db.func.lower(TheoryTag.name) == 'zone').count() == 2
    page = text(c.get(f'/theory/topic/{herd["force"]}'))
    assert 'Drill 1' in page and 'Their drill' not in page
    # The edit form has them ticked and the tags filled in
    form = text(c.get(f'/theory/edit_topic/{herd["force"]}'))
    assert f'value="{mine[0].id}" checked' in form and 'value="Handler resets, zone"' in form
    # Unused tags go when the last topic drops them
    c.post(f'/theory/edit_topic/{herd["force"]}', data=topic_form(herd, name='Force', tags='zone', action='save'))
    assert TheoryTag.query.filter_by(team_organization_id=herd['team']).count() == 1


def test_topics_link_clips_from_the_library(app, herd):
    from app.models.clip import Clip
    shown = Clip(title='Cup in the wind', team_organization_id=herd['team'])
    hidden = Clip(title='Coaches only film', is_hidden=True, team_organization_id=herd['team'])
    theirs = Clip(title='Their clip', team_organization_id=herd['other'])
    db.session.add_all([shown, hidden, theirs])
    db.session.commit()
    c = client(app, herd, 'coach')
    form = text(c.get(f'/theory/edit_topic/{herd["cup"]}'))
    assert 'Cup in the wind' in form and 'Their clip' not in form
    r = c.post(f'/theory/edit_topic/{herd["cup"]}', data=topic_form(
        herd, name='Cup', action='save', clips=[shown.id, hidden.id, theirs.id]))
    assert r.status_code == 302
    assert sorted(cl.title for cl in fresh(TheoryTopic, herd['cup']).clips) == ['Coaches only film', 'Cup in the wind']
    assert f'value="{shown.id}" checked' in text(c.get(f'/theory/edit_topic/{herd["cup"]}'))

    player = text(client(app, herd, 'player').get(f'/theory/topic/{herd["cup"]}'))
    assert 'See it in a game' in player and 'Cup in the wind' in player and 'Coaches only film' not in player
    assert 'Coaches only film' in text(c.get(f'/theory/topic/{herd["cup"]}'))


def test_sections_have_per_team_slugs(app, herd):
    c = client(app, herd, 'coach')
    c.post('/theory/add_section', data={'name': 'Defence', 'description': ''})
    other = client(app, herd, 'other_coach', team='other')
    other.post('/theory/add_section', data={'name': 'Throwing', 'description': ''})
    c.post('/theory/add_section', data={'name': 'Throwing', 'description': ''})
    slugs = sorted(s.slug for s in TheorySection.query.filter_by(team_organization_id=herd['team']))
    assert slugs == ['defence', 'defence-2', 'throwing']
    assert c.get('/theory/section/defence-2').status_code == 200


def test_videos(app, herd):
    c = client(app, herd, 'coach')
    c.post(f'/theory/edit_topic/{herd["force"]}', data=topic_form(
        herd, name='Force', action='save',
        video_url=['https://youtu.be/dQw4w9WgXcQ?t=1m5s', '', 'https://vimeo.com/76979871'],
        video_title=['Marking', '', '']))
    videos = TheoryVideo.query.filter_by(topic_id=herd['force']).order_by(TheoryVideo.order).all()
    assert [(v.title, v.order) for v in videos] == [('Marking', 1), ('Video', 2)]
    page = text(c.get(f'/theory/topic/{herd["force"]}'))
    assert 'src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=65"' in page
    assert 'src="https://player.vimeo.com/video/76979871"' in page


@pytest.mark.parametrize('url, embed', [
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'),
    ('https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ&t=30', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=30'),
    ('https://youtube.com/shorts/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'),
    ('https://www.youtube.com/embed/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'),
    ('https://vimeo.com/123456/abcdef12', 'https://player.vimeo.com/video/123456?h=abcdef12'),
    ('https://player.vimeo.com/video/123456', 'https://player.vimeo.com/video/123456'),
    ('https://example.com/watch?v=dQw4w9WgXcQ', None),
    ('javascript:alert(1)', None),
    ('', None),
])
def test_video_embed_url(url, embed):
    assert video_embed_url(url) == embed


def test_preview_is_cleaned(app, herd):
    r = client(app, herd, 'coach').post('/theory/preview', data={'content': '## Hi\n\n<script>alert(1)</script>**b**'})
    html = r.get_json()['html']
    assert '<h2>Hi</h2>' in html and '<strong>b</strong>' in html and '<script' not in html


def test_reorder_topics_and_sections(app, herd):
    c = client(app, herd, 'coach')
    c.post(f'/theory/topic/{herd["cup"]}/move', data={'direction': 'up'})
    order = [t.name for t in TheoryTopic.query.filter_by(section_id=herd['section']).order_by(TheoryTopic.order)]
    assert order == ['Cup', 'Force', 'Secret plan']
    c.post(f'/theory/topic/{herd["cup"]}/move', data={'direction': 'up'})  # already first: no change
    c.post('/theory/add_section', data={'name': 'Offence', 'description': ''})
    offence = TheorySection.query.filter_by(name='Offence', team_organization_id=herd['team']).one()
    assert offence.order == 2
    c.post(f'/theory/section/{offence.id}/move', data={'direction': 'up'})
    assert [s.name for s in TheorySection.query.filter_by(team_organization_id=herd['team'])
            .order_by(TheorySection.order)] == ['Offence', 'Defence']


def test_deleting_a_section_takes_its_topics_and_reads(app, herd):
    db.session.add(TheoryRead(user_id=herd['player'], topic_id=herd['force'], team_organization_id=herd['team']))
    db.session.add(TheoryAssignment(topic_id=herd['force'], team_organization_id=herd['team']))
    db.session.commit()
    client(app, herd, 'coach').post(f'/theory/delete_section/{herd["section"]}')
    assert TheoryTopic.query.filter_by(team_organization_id=herd['team']).count() == 0
    assert TheoryRead.query.count() == 0 and TheoryAssignment.query.count() == 0
    assert fresh(TheoryTopic, herd['other_topic']) is not None


# ── Photos ────────────────────────────────────────────────────────────────

def test_photo_upload_is_resized_turned_upright_and_kept_to_the_team(app, herd):
    c = client(app, herd, 'coach')
    r = c.post('/theory/images', data={'image': (photo(exif_rotate=True), 'IMG_0001.jpg')},
               content_type='multipart/form-data')
    assert r.status_code == 200, text(r)
    url = r.get_json()['url']
    image = TheoryImage.query.one()
    # 3000x2000 on its side -> upright 2000x3000 -> fits in 1600
    assert (image.width, image.height) == (1067, 1600) and image.mime_type == 'image/webp'
    served = c.get(url)
    assert served.status_code == 200 and served.headers['Content-Type'] == 'image/webp'
    assert Image.open(io.BytesIO(served.data)).size == (1067, 1600)
    assert 'private' in served.headers['Cache-Control']
    assert c.get(url, headers={'If-None-Match': served.headers['ETag'].strip('"')}).status_code == 304
    # Players can see it; another team can't
    assert client(app, herd, 'player').get(url).status_code == 200
    assert client(app, herd, 'other_coach', team='other').get(url).status_code == 404
    # It can be the cover photo
    r = c.post(f'/theory/edit_topic/{herd["force"]}', data=topic_form(herd, name='Force', image_url=url, action='save'))
    assert r.status_code == 302 and fresh(TheoryTopic, herd['force']).image_url == url


def test_photo_upload_rejects_other_files(app, herd):
    c = client(app, herd, 'coach')
    r = c.post('/theory/images', data={'image': (io.BytesIO(b'not a photo'), 'x.jpg')}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'photo' in r.get_json()['error']
    r = c.post('/theory/images', data={}, content_type='multipart/form-data')
    assert r.status_code == 400
    # PNGs with transparency stay transparent
    r = c.post('/theory/images', data={'image': (photo((40, 40), 'PNG'), 'a.png')}, content_type='multipart/form-data')
    assert r.status_code == 200
    assert TheoryImage.query.count() == 1


def test_cover_photo_link_must_be_a_web_address(app, herd):
    r = client(app, herd, 'coach').post(f'/theory/edit_topic/{herd["force"]}',
                                        data=topic_form(herd, name='Force', image_url='javascript:alert(1)'))
    assert r.status_code == 200 and 'https://' in text(r)
    assert fresh(TheoryTopic, herd['force']).image_url is None


# ── Reading ───────────────────────────────────────────────────────────────

def test_mark_as_read_and_progress(app, herd):
    p = client(app, herd, 'player')
    assert '0 of 2 read' in text(p.get('/theory/section/defence'))
    r = p.post(f'/theory/topic/{herd["force"]}/read', data={'read': '1'})
    # On to the next topic
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/theory/topic/{herd["cup"]}')
    assert TheoryRead.query.filter_by(user_id=herd['player']).count() == 1
    # Twice is still once
    r = p.post(f'/theory/topic/{herd["force"]}/read', data={'read': '1'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.get_json() == {'read': True} and TheoryRead.query.count() == 1
    hub_page = text(p.get('/theory/'))
    assert "You've read <strong>1</strong> of 2 topics" in hub_page
    assert 'Continue reading' in hub_page and f'/theory/topic/{herd["cup"]}' in hub_page
    assert '1/2 read' in hub_page
    # Un-mark
    p.post(f'/theory/topic/{herd["force"]}/read', data={'read': '0'})
    assert TheoryRead.query.count() == 0


def test_continue_reading_wraps_to_the_first_unread(app, herd):
    db.session.add(TheoryRead(user_id=herd['player'], topic_id=herd['cup'], team_organization_id=herd['team']))
    db.session.commit()
    topics = hub.ordered_topics(herd['team'])
    nxt = hub.continue_reading(herd['player'], herd['team'], topics, hub.read_ids(herd['player'], herd['team']))
    assert nxt.id == herd['force']


def test_search(app, herd):
    topic = fresh(TheoryTopic, herd['cup'])
    topic.content = 'The **cup** traps the handler. ![photo](https://x/y.png)'
    topic.tags = [TheoryTag(name='Zone', team_organization_id=herd['team'])]
    db.session.commit()
    p = client(app, herd, 'player')
    page = text(p.get('/theory/?q=handler'))
    assert '1 result' in page and 'traps the handler' in page and 'y.png' not in page
    assert '1 result' in text(p.get('/theory/?q=zone'))
    page = text(p.get('/theory/?tag=Zone'))
    assert '1 result' in page and 'tagged <strong>Zone</strong>' in page
    assert 'Nothing matches' in text(p.get('/theory/?q=zzzz'))
    assert 'Their zone' not in text(p.get('/theory/?q=zone'))


def test_assigned_reading(app, herd):
    c = client(app, herd, 'coach')
    r = c.post(f'/theory/topic/{herd["cup"]}/readers', data={'due_date': '2026-11-07', 'note': 'Before Saturday'})
    assert r.status_code == 302
    assignment = TheoryAssignment.query.one()
    assert assignment.due_date == date(2026, 11, 7) and assignment.assigned_by == herd['coach']

    welcomed(herd['player'])
    p = client(app, herd, 'player')
    page = text(p.get('/theory/'))
    assert 'Assigned to you' in page and 'Read by Sat 7 Nov' in page and 'Before Saturday' in page
    home = text(p.get('/'))
    assert 'Assigned reading · read by Sat 7 Nov' in home and 'To read' in home

    p.post(f'/theory/topic/{herd["cup"]}/read', data={'read': '1'})
    assert 'Assigned reading' not in text(p.get('/'))

    readers = text(c.get(f'/theory/topic/{herd["cup"]}/readers'))
    assert '1 of' in readers and 'player' in readers and 'Not yet' in readers
    assert '1 of 4 read' in text(c.get('/theory/'))  # coach, captain and two players

    c.post(f'/theory/topic/{herd["cup"]}/unassign')
    assert TheoryAssignment.query.count() == 0


def test_drafts_stay_off_the_dashboard(app, herd):
    welcomed(herd['player'])
    home = text(client(app, herd, 'player').get('/'))
    assert 'Secret plan' not in home and ('Force' in home or 'Cup' in home)


def test_discord_announces_published_topics_by_name(app, herd, monkeypatch):
    from app.discord import events, notify
    sent = []
    monkeypatch.setattr(notify, 'post', lambda team_id, payload: sent.append(payload) or True)
    assert events.announce('TheoryTopic', herd['force'])
    assert 'New theory: Force' in json.dumps(sent[0])


def test_old_style_rows_without_order_still_list(app, herd):
    for t in TheoryTopic.query.filter_by(section_id=herd['section']):
        t.order = None
    db.session.commit()
    page = text(client(app, herd, 'player').get('/theory/section/defence'))
    assert page.index('Force') < page.index('Cup')


def test_image_data_is_base64(app, herd):
    c = client(app, herd, 'coach')
    c.post('/theory/images', data={'image': (photo((10, 10)), 'a.jpg')}, content_type='multipart/form-data')
    assert base64.b64decode(TheoryImage.query.one().data)[:4] == b'RIFF'
