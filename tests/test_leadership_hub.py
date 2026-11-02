"""Leadership hub: leaders share ideas, articles and footage, reply, pin, build
the meeting agenda, and get unread markers; posts can go to a private
Discord channel (never the team one); players, stat takers and other teams
never see any of it."""
from datetime import datetime, timedelta

from app import db
from app.models.clip import Clip
from app.models.leadership import LeadershipComment, LeadershipPost, LeadershipRead
from app.models.team_settings import TeamSettings
from app.utils.leadership import ago, clean_url, render_text, start_from
from tests import stats_data
from tests.test_discord import WEBHOOK, discord_calls  # noqa: F401
from tests.test_season_plan import NAV_PAGE, client, herd  # noqa: F401
from tests.test_teams import make_user

YOUTUBE = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def enable(team_id, on=True):
    TeamSettings.query.filter_by(team_id=team_id).one().leadership_handbook_enabled = on
    db.session.commit()


def share(c, **data):
    form = {'kind': 'idea', 'title': 'Try a zone', 'body': 'Thoughts?'}
    form.update(data)
    return c.post('/leadership/new', data=form)


def only_post():
    db.session.expire_all()  # the requests ran in their own sessions
    return LeadershipPost.query.one()


# ── Helpers ────────────────────────────────────────────────────────────────

def test_clean_url_and_start_times():
    assert clean_url('example.com/a') == 'https://example.com/a'
    assert clean_url('javascript:alert(1)') is None and clean_url('ftp://x.com') is None
    assert clean_url('') is None and clean_url('not a link') is None
    assert start_from('1:30') == 90 and start_from('nope') is None
    assert start_from('', YOUTUBE + '&t=1m5s') == 65


def test_render_text_escapes_and_links_times_only_with_a_video():
    html = str(render_text('<b>hi</b> see https://ex.com/a. at 3:42 or 1:02:03', seekable=True))
    assert '&lt;b&gt;hi&lt;/b&gt;' in html
    assert '<a href="https://ex.com/a" target="_blank" rel="noopener noreferrer">https://ex.com/a</a>.' in html
    assert 'data-seconds="222">3:42</a>' in html and 'data-seconds="3723">1:02:03</a>' in html
    assert 'lh-ts' not in str(render_text('at 3:42'))
    assert 'lh-ts' not in str(render_text('https://ex.com/v?t=3:42', seekable=True))  # not inside links


def test_ago():
    now = datetime(2026, 11, 2, 12)
    assert ago(now - timedelta(seconds=5), now) == 'just now'
    assert ago(now - timedelta(minutes=5), now) == '5 min ago'
    assert ago(now - timedelta(days=1, hours=1), now) == 'yesterday'
    assert ago(datetime(2026, 3, 2), now) == '2 Mar'


# ── Who sees it ────────────────────────────────────────────────────────────

URLS = ('/leadership/', '/leadership/new', '/leadership/agenda')


def test_off_hides_the_nav_and_every_route_is_404(app, herd):
    c = client(app, herd, 'captain')
    assert '/leadership/' not in c.get(NAV_PAGE).get_data(as_text=True)
    for url in URLS:
        assert c.get(url).status_code == 404, url


def test_players_and_stat_takers_never_see_it(app, herd):
    from app.models.team_organization import TeamOrganization
    enable(herd['team'])
    share(client(app, herd, 'coach'))
    post_id = only_post().id
    team = db.session.get(TeamOrganization, herd['team'])
    stat = make_user(team, 'stats', role='stat_taker')
    for c in (client(app, herd, 'player'), stats_data.Client(app, stat.id, herd['team'])):
        assert '/leadership/' not in c.get(NAV_PAGE).get_data(as_text=True)
        for url in URLS + (f'/leadership/{post_id}', f'/leadership/{post_id}/edit'):
            assert c.get(url).status_code == 404, url
        assert c.post(f'/leadership/{post_id}/comment', data={'body': 'hi'}).status_code == 404
        assert share(c).status_code == 404
    assert LeadershipComment.query.count() == 0 and LeadershipPost.query.count() == 1


def test_other_teams_cant_reach_posts(app, herd):
    enable(herd['team'])
    share(client(app, herd, 'coach'), title='Secret plan')
    post_id = only_post().id
    other = stats_data.build_team('Other', 'other-team')
    db.session.add(TeamSettings(team_id=other.id, leadership_handbook_enabled=True))
    db.session.commit()
    coach = make_user(other, 'othercoach', role='coach')
    c = stats_data.Client(app, coach.id, other.id)
    assert 'Secret plan' not in c.get('/leadership/').get_data(as_text=True)
    assert c.get(f'/leadership/{post_id}').status_code == 404
    assert c.post(f'/leadership/{post_id}/comment', data={'body': 'x'}).status_code == 404
    assert c.post(f'/leadership/{post_id}/set', data={'what': 'pinned'}).status_code == 404
    assert c.post(f'/leadership/{post_id}/delete').status_code == 404


# ── Using it ───────────────────────────────────────────────────────────────

def test_leaders_share_reply_and_see_unread(app, herd):
    enable(herd['team'])
    coach, captain = client(app, herd, 'coach'), client(app, herd, 'captain')
    nav = coach.get(NAV_PAGE).get_data(as_text=True)
    assert 'href="/leadership/"' in nav and 'Leadership Hub' in nav

    r = share(coach, kind='article', title='Leading through a losing streak',
              url='https://example.com/streak', body='Worth 5 minutes.', on_agenda='on')
    post = only_post()
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/leadership/{post.id}')
    assert (post.kind, post.url, post.on_agenda, post.author_id) == ('article', 'https://example.com/streak', True,
                                                                     herd['coach'])

    # the author has read it; the captain hasn't
    assert 'New</span>' not in coach.get('/leadership/').get_data(as_text=True)
    feed = captain.get('/leadership/').get_data(as_text=True)
    assert 'Leading through a losing streak' in feed and 'New</span>' in feed and 'example.com' in feed
    assert 'bg-success ms-1">1<' in captain.get(NAV_PAGE).get_data(as_text=True)

    page = captain.get(f'/leadership/{post.id}').get_data(as_text=True)
    assert 'Worth 5 minutes.' in page and 'href="https://example.com/streak"' in page
    assert 'New</span>' not in captain.get('/leadership/').get_data(as_text=True)

    r = captain.post(f'/leadership/{post.id}/comment', data={'body': 'Agree, bring it to the meeting'})
    reply = LeadershipComment.query.one()
    assert r.headers['Location'].endswith(f'/leadership/{post.id}#c{reply.id}')
    feed = coach.get('/leadership/').get_data(as_text=True)
    assert 'New</span>' in feed  # the reply is news to the coach
    assert 'Agree, bring it' in coach.get(f'/leadership/{post.id}').get_data(as_text=True)
    assert captain.post(f'/leadership/{post.id}/comment', data={'body': '  '}).status_code == 302
    assert LeadershipComment.query.count() == 1

    # the agenda, and clearing it
    assert 'Leading through a losing streak' in coach.get('/leadership/agenda').get_data(as_text=True)
    coach.post('/leadership/agenda', data={'action': 'clear'})
    assert only_post().on_agenda is False
    assert 'Nothing on the agenda' in coach.get('/leadership/agenda').get_data(as_text=True)


def test_footage_plays_in_the_page_and_times_jump_it(app, herd):
    enable(herd['team'])
    c = client(app, herd, 'coach')
    share(c, kind='idea', title='Their force', url=YOUTUBE, start='1:30', body='Watch the mark at 2:10')
    post = only_post()
    assert (post.kind, post.start_seconds) == ('footage', 90)  # a video link is footage
    page = c.get(f'/leadership/{post.id}').get_data(as_text=True)
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?start=90"' in page
    assert 'data-seconds="130">2:10</a>' in page

    r = share(c, title='Bad', url='javascript:alert(1)')
    assert r.status_code == 200 and "doesn&#39;t look right" in r.get_data(as_text=True)
    assert share(c, title='Bad', start='soon').status_code == 200
    assert share(c, title=' ').status_code == 200
    assert LeadershipPost.query.count() == 1


def test_discuss_a_team_clip(app, herd):
    enable(herd['team'])
    clip = Clip(title='Zone O breakdown', youtube_link=YOUTUBE, start_time=40, end_time=70,
                team_organization_id=herd['team'])
    other_team = stats_data.build_team('Other', 'other-team')
    foreign = Clip(title='Not ours', youtube_link=YOUTUBE, team_organization_id=other_team.id)
    db.session.add_all([clip, foreign])
    db.session.commit()
    c = client(app, herd, 'coach')
    assert f'/leadership/new?clip={clip.id}' in c.get(f'/clips/{clip.id}').get_data(as_text=True)
    form = c.get(f'/leadership/new?clip={clip.id}').get_data(as_text=True)
    assert 'value="Zone O breakdown"' in form and f'name="clip_id" value="{clip.id}"' in form

    share(c, title='Zone O breakdown', clip_id=str(clip.id))
    post = only_post()
    assert (post.kind, post.clip_id) == ('footage', clip.id)
    assert 'embed/dQw4w9WgXcQ?start=40&amp;end=70' in c.get(f'/leadership/{post.id}').get_data(as_text=True)

    share(c, title='Theirs', clip_id=str(foreign.id))  # another team's clip isn't attached
    assert LeadershipPost.query.filter_by(title='Theirs').one().clip_id is None


def test_pin_status_edit_and_delete_rights(app, herd):
    enable(herd['team'])
    coach, captain = client(app, herd, 'coach'), client(app, herd, 'captain')
    share(captain, title='Older')
    share(coach, title='Newer')
    newer_id = LeadershipPost.query.filter_by(title='Newer').one().id
    older_id = LeadershipPost.query.filter_by(title='Older').one().id

    feed = coach.get('/leadership/').get_data(as_text=True)
    assert feed.index('Newer') < feed.index('Older')
    coach.post(f'/leadership/{older_id}/set', data={'what': 'pinned'})
    feed = coach.get('/leadership/').get_data(as_text=True)
    assert feed.index('Older') < feed.index('Newer')

    coach.post(f'/leadership/{older_id}/set', data={'what': 'status', 'status': 'archived'})
    assert 'Older' not in coach.get('/leadership/').get_data(as_text=True)
    assert 'Older' in coach.get('/leadership/?status=archived').get_data(as_text=True)
    assert coach.post(f'/leadership/{older_id}/set', data={'what': 'nope'}).status_code == 400

    # a coach can't edit or delete the captain's post; the captain (a team admin) can do both to the coach's
    assert coach.get(f'/leadership/{older_id}/edit').status_code == 403
    assert coach.post(f'/leadership/{older_id}/delete').status_code == 403
    r = captain.post(f'/leadership/{newer_id}/edit', data={'kind': 'question', 'title': 'Newer?', 'body': ''})
    db.session.expire_all()
    assert r.status_code == 302 and db.session.get(LeadershipPost, newer_id).kind == 'question'
    coach.post(f'/leadership/{newer_id}/comment', data={'body': 'mine'})
    captain.get(f'/leadership/{newer_id}')
    assert captain.post(f'/leadership/{newer_id}/delete').status_code == 302
    db.session.expire_all()
    assert db.session.get(LeadershipPost, newer_id) is None
    assert LeadershipComment.query.count() == 0 and LeadershipRead.query.filter_by(post_id=newer_id).count() == 0


def test_search(app, herd):
    enable(herd['team'])
    c = client(app, herd, 'coach')
    share(c, title='Zone defence', body='cup')
    share(c, title='Pull plays', body='')
    c.post(f'/leadership/{LeadershipPost.query.filter_by(title="Pull plays").one().id}/comment',
           data={'body': 'hang time matters'})
    assert 'Pull plays' in c.get('/leadership/?q=hang').get_data(as_text=True)
    assert 'Zone defence' not in c.get('/leadership/?q=hang').get_data(as_text=True)
    assert 'Nothing matches' in c.get('/leadership/?q=zzzz').get_data(as_text=True)


def test_handbook_sits_in_the_hub(app, herd):
    enable(herd['team'])
    c = client(app, herd, 'coach')
    page = c.get('/handbook/').get_data(as_text=True)
    assert 'href="/leadership/"' in page and 'href="/leadership/agenda"' in page
    assert 'href="/handbook/"' in c.get('/leadership/').get_data(as_text=True)


# ── Discord ────────────────────────────────────────────────────────────────

def test_posts_go_only_to_the_private_leaders_channel(app, herd, discord_calls):
    enable(herd['team'])
    settings = TeamSettings.query.filter_by(team_id=herd['team']).one()
    settings.discord_enabled = True
    settings.discord_webhook_url = WEBHOOK  # the team channel
    db.session.commit()
    c = client(app, herd, 'captain')  # Discord settings are for team admins

    share(c, title='Nothing configured')
    assert discord_calls == []  # no leaders channel: nothing goes anywhere

    leaders_hook = 'https://discord.com/api/webhooks/2/leaders'
    r = c.post('/discord/settings', data={'action': 'leaders', 'leaders_webhook_url': WEBHOOK})
    db.session.expire_all()
    assert r.status_code == 302 and settings.discord_leaders_webhook_url is None  # not the team channel
    c.post('/discord/settings', data={'action': 'leaders', 'leaders_webhook_url': leaders_hook})
    db.session.expire_all()
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().discord_leaders_webhook_url == leaders_hook
    assert [url for _, url, _ in discord_calls] == [leaders_hook]  # the hello message
    del discord_calls[:]

    share(c, title='Watch this', url=YOUTUBE)
    post = LeadershipPost.query.filter_by(title='Watch this').one()
    c.post(f'/leadership/{post.id}/comment', data={'body': 'Great cut at 0:42'})
    assert [url for _, url, _ in discord_calls] == [leaders_hook, leaders_hook]
    first = discord_calls[0][2]['json']['embeds'][0]
    assert 'Watch this' in first['title'] and f'/leadership/{post.id}' in first['url']
    assert 'Great cut' in discord_calls[1][2]['json']['embeds'][0]['description']

    c.post('/discord/settings', data={'action': 'leaders', 'leaders_webhook_url': ''})
    del discord_calls[:]
    share(c, title='Quiet again')
    assert discord_calls == []
