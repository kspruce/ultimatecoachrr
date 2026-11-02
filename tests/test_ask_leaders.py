"""Ask the leaders: players ask about a clip, play, theory topic, drill or
session (or anything); the question lands in the Leadership hub; leaders
reply to the player or add leaders-only notes; the player follows their
questions under My Questions and on their profile."""
from app import db
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.models.leadership import LeadershipComment, LeadershipPost
from app.models.player import Player
from app.models.playbook import Play
from app.models.session import SessionPlan
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from app.models.user import User
from tests import stats_data
from tests.test_discord import discord_calls  # noqa: F401
from tests.test_leadership_hub import YOUTUBE, enable
from tests.test_season_plan import NAV_PAGE, client, herd  # noqa: F401
from tests.test_teams import make_user


def things(team_id):
    """One of everything a question can be about, plus things players can't see."""
    section = TheorySection(name='Defence', slug='defence', order=1, team_organization_id=team_id)
    db.session.add(section)
    db.session.flush()
    rows = {
        'clip': Clip(title='Zone O breakdown', youtube_link=YOUTUBE, start_time=40, team_organization_id=team_id),
        'hidden_clip': Clip(title='Hidden', youtube_link=YOUTUBE, is_hidden=True, team_organization_id=team_id),
        'play': Play(name='Side stack', type='offense', team_organization_id=team_id),
        'draft_play': Play(name='Secret play', type='offense', status='draft', team_organization_id=team_id),
        'topic': TheoryTopic(section_id=section.id, name='The force', content='x', order=1, published=True,
                             team_organization_id=team_id),
        'draft_topic': TheoryTopic(section_id=section.id, name='Draft topic', content='x', order=2, published=False,
                                   team_organization_id=team_id),
        'drill': SavedDrill(title='3-person weave', team_organization_id=team_id),
        'session': SessionPlan(title='Tuesday training', team_organization_id=team_id),
    }
    db.session.add_all(rows.values())
    db.session.commit()
    return {k: v.id for k, v in rows.items()}


def ask(c, about=None, **data):
    form = {'body': 'Where should I stand?'}
    if about:
        form['about'] = about
    form.update(data)
    return c.post('/questions/ask', data=form)


def latest():
    db.session.expire_all()
    return LeadershipPost.query.order_by(LeadershipPost.id.desc()).first()


def test_off_means_no_buttons_and_no_pages(app, herd):
    ids = things(herd['team'])
    c = client(app, herd, 'player')
    assert 'Ask the leaders' not in c.get(f"/playbook/plays/{ids['play']}").get_data(as_text=True)
    for url in ('/questions/', '/questions/ask'):
        assert c.get(url).status_code == 404, url
    assert ask(c).status_code == 404


def test_the_button_is_on_every_kind_of_page(app, herd):
    ids = things(herd['team'])
    enable(herd['team'])
    player, coach = client(app, herd, 'player'), client(app, herd, 'coach')
    pages = {'clip': f"/clips/{ids['clip']}", 'play': f"/playbook/plays/{ids['play']}",
             'topic': f"/theory/topic/{ids['topic']}", 'drill': f"/sessions/drills/{ids['drill']}",
             'session': f"/sessions/{ids['session']}/detail"}
    for kind, url in pages.items():
        page = player.get(url).get_data(as_text=True)
        assert f'/questions/ask?about={kind}:{ids[kind]}' in page and 'Ask the leaders' in page, kind
        page = coach.get(url).get_data(as_text=True)
        assert f'/leadership/new?about={kind}:{ids[kind]}' in page and 'Discuss with leaders' in page, kind


def test_a_player_asks_and_leaders_answer(app, herd, discord_calls):
    ids = things(herd['team'])
    enable(herd['team'])
    db.session.get(User, herd['player']).discord_id = '555'
    app.config.update(DISCORD_BOT_TOKEN='t', DISCORD_CLIENT_ID='1', DISCORD_CLIENT_SECRET='s', DISCORD_PUBLIC_KEY='k')
    db.session.commit()
    player, coach, captain = client(app, herd, 'player'), client(app, herd, 'coach'), client(app, herd, 'captain')

    form = player.get(f"/questions/ask?about=play:{ids['play']}").get_data(as_text=True)
    assert 'value="About Side stack"' in form and f'value="play:{ids["play"]}"' in form
    r = ask(player, f"play:{ids['play']}", title='About Side stack', body='Do I cut first or second?')
    post = latest()
    assert r.headers['Location'].endswith(f'/questions/{post.id}')
    assert (post.from_player, post.kind, post.subject_type, post.subject_id, post.author_id) == \
        (True, 'question', 'play', ids['play'], herd['player'])
    assert post.player_status == 'waiting'

    # leaders see it in the hub, flagged as waiting
    feed = coach.get('/leadership/').get_data(as_text=True)
    assert 'Asked by player' in feed and '1 player question waiting for a reply' in feed
    assert 'About Side stack' in coach.get('/leadership/?who=players').get_data(as_text=True)
    page = coach.get(f'/leadership/{post.id}').get_data(as_text=True)
    assert 'player asked the leaders' in page and 'Reply to player' in page and 'Leaders-only note' in page
    assert f'href="/playbook/plays/{ids["play"]}"' in page

    # a leaders-only note: the player doesn't see it, and isn't told
    del discord_calls[:]
    captain.post(f'/leadership/{post.id}/comment', data={'body': 'They keep cutting late', 'visibility': 'leaders'})
    assert LeadershipComment.query.one().leaders_only is True
    assert 'They keep cutting late' not in player.get(f'/questions/{post.id}').get_data(as_text=True)
    assert latest().player_status == 'waiting' and discord_calls == []

    # a reply to the player: they see it, get a Discord message and a badge
    coach.post(f'/leadership/{post.id}/comment', data={'body': 'Second, after the 3 clears.', 'visibility': 'asker'})
    assert any('/users/@me/channels' in url or '/channels/' in url for _, url, _ in discord_calls)
    assert latest().player_status == 'answered'
    nav = player.get(NAV_PAGE).get_data(as_text=True)
    assert 'My Questions' in nav and 'bg-success ms-1">1<' in nav
    mine = player.get('/questions/').get_data(as_text=True)
    assert 'About Side stack' in mine and 'New answer' in mine and 'Answered' in mine
    page = player.get(f'/questions/{post.id}').get_data(as_text=True)
    assert 'Second, after the 3 clears.' in page and 'They keep cutting late' not in page
    assert 'New answer' not in player.get('/questions/').get_data(as_text=True)

    # the player follows up: leaders see it as new, and a closed question re-opens
    coach.post(f'/leadership/{post.id}/set', data={'what': 'status', 'status': 'actioned'})
    assert latest().player_status == 'closed'
    player.post(f'/questions/{post.id}/reply', data={'body': 'Thanks! And on the break side?'})
    assert latest().status == 'open'
    assert 'New</span>' in coach.get('/leadership/').get_data(as_text=True)
    assert 'Thanks! And on the break side?' in coach.get(f'/leadership/{post.id}').get_data(as_text=True)


def test_the_profile_lists_my_questions(app, herd):
    enable(herd['team'])
    user = db.session.get(User, herd['player'])
    player_row = Player(name='Pat Player', team_organization_id=herd['team'], user_id=user.id)
    db.session.add(player_row)
    db.session.commit()
    c = client(app, herd, 'player')
    ask(c, title='Zone question', body='When do we switch?')
    page = c.get(f'/team/player/{player_row.id}').get_data(as_text=True)
    assert 'My Questions' in page and 'Zone question' in page and 'Waiting for a reply' in page


def test_players_cant_ask_about_what_they_cant_see(app, herd):
    ids = things(herd['team'])
    enable(herd['team'])
    other = stats_data.build_team('Other', 'other-team')
    theirs = Play(name='Their play', type='offense', team_organization_id=other.id)
    db.session.add(theirs)
    db.session.commit()
    c = client(app, herd, 'player')
    for about in (f"play:{ids['draft_play']}", f"topic:{ids['draft_topic']}", f"clip:{ids['hidden_clip']}",
                  f'play:{theirs.id}', 'nonsense:1'):
        assert 'name="about"' not in c.get(f'/questions/ask?about={about}').get_data(as_text=True), about
        ask(c, about, title='Q')
        post = latest()
        assert (post.subject_type, post.subject_id) == (None, None), about
        assert 'Secret play' not in c.get(f'/questions/{post.id}').get_data(as_text=True)


def test_questions_are_private_to_the_asker_and_leaders(app, herd):
    enable(herd['team'])
    from app.models.team_organization import TeamOrganization
    team = db.session.get(TeamOrganization, herd['team'])
    other_player = make_user(team, 'other_player', role='player')
    stat = make_user(team, 'stats', role='stat_taker')
    ask(client(app, herd, 'player'), title='Private worry', body='I feel off the pace')
    post = latest()
    for user in (other_player, stat):
        c = stats_data.Client(app, user.id, herd['team'])
        assert c.get(f'/questions/{post.id}').status_code == 404
        assert c.post(f'/questions/{post.id}/reply', data={'body': 'x'}).status_code == 404
        assert c.post(f'/questions/{post.id}/delete').status_code == 404
        assert 'Private worry' not in c.get('/questions/').get_data(as_text=True)
        assert c.get(f'/leadership/{post.id}').status_code == 404
    guest = make_user(team, 'guest', role='guest')
    assert stats_data.Client(app, guest.id, herd['team']).get('/questions/ask').status_code == 404


def test_a_player_can_take_back_an_unanswered_question(app, herd):
    enable(herd['team'])
    player, coach = client(app, herd, 'player'), client(app, herd, 'coach')
    ask(player, title='Oops')
    post_id = latest().id
    assert player.post(f'/questions/{post_id}/delete').status_code == 302
    assert latest() is None

    ask(player, title='Keep me')
    post_id = latest().id
    coach.post(f'/leadership/{post_id}/comment', data={'body': 'Answer', 'visibility': 'asker'})
    player.post(f'/questions/{post_id}/delete')
    assert latest().id == post_id


def test_leaders_pressing_ask_go_to_the_hub(app, herd):
    ids = things(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'coach')
    r = c.get(f"/questions/ask?about=topic:{ids['topic']}")
    assert r.status_code == 302 and '/leadership/new?about=topic' in r.headers['Location']
    form = c.get(f"/leadership/new?about=topic:{ids['topic']}").get_data(as_text=True)
    assert 'value="The force"' in form and 'Theory:' in form
    c.post('/leadership/new', data={'kind': 'idea', 'title': 'The force', 'about': f"topic:{ids['topic']}"})
    post = latest()
    assert (post.from_player, post.subject_type, post.subject_id) == (False, 'topic', ids['topic'])
    assert c.get('/questions/').status_code == 302  # leaders' "my questions" is the hub


def test_new_questions_go_to_the_leaders_channel(app, herd, discord_calls):
    enable(herd['team'])
    hook = 'https://discord.com/api/webhooks/2/leaders'
    settings = TeamSettings.query.filter_by(team_id=herd['team']).one()
    settings.discord_enabled, settings.discord_leaders_webhook_url = True, hook
    db.session.commit()
    ask(client(app, herd, 'player'), title='Pull question')
    assert [url for _, url, _ in discord_calls] == [hook]
    assert 'asked the leaders' in discord_calls[0][2]['json']['embeds'][0]['title']
