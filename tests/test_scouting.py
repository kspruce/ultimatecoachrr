"""Scouting: reports, opponent players, clips, the game card, links to games,
who may change what, and that nothing reaches another team."""
import re
from datetime import date

import pytest

from app import db
from app.models.game import Game
from app.models.onboarding import UserOnboarding
from app.models.player import Player
from app.models.team_organization import TeamOrganization
from app.models.scouting import (OpponentPlayer, ScoutingClip, ScoutingReport, extract_youtube_id,
                                 format_time, opponent_key, parse_moments, parse_time)
from app.models.tournament import Tournament
from app.models.user import User
from app.routes.scouting import parse_roster
from tests import stats_data


def make_user(team_id, username, role):
    user = User(username=username, email=f'{username}@example.com', role=role, team_organization_id=team_id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    return user


@pytest.fixture
def scout(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    ours = stats_data.build_players(herd, 3)
    tour = Tournament(name='Nationals', team_organization_id=herd.id)
    db.session.add(tour)
    db.session.flush()
    past = Game(opponent='Bad Skid', date=date(2026, 5, 1), our_score=13, their_score=9,
                tournament_id=tour.id, team_organization_id=herd.id)
    undated = Game(opponent='bad  skid', team_organization_id=herd.id)  # no date, odd spacing
    report = ScoutingReport(team_name='Bad Skid', date=date(2026, 4, 1), weaknesses='Slow to set the zone\nWeak backhand side',
                            offense_tags='vertical', team_organization_id=herd.id)
    secret = ScoutingReport(team_name='Secret Rivals', team_organization_id=other.id)
    db.session.add_all([past, undated, report, secret])
    db.session.flush()
    secret_player = OpponentPlayer(scouting_report_id=secret.id, name='Hidden', team_organization_id=other.id)
    secret_clip = ScoutingClip(scouting_report_id=secret.id, title='Hidden clip', team_organization_id=other.id,
                               youtube_link='https://www.youtube.com/watch?v=abcdefghijk')
    db.session.add_all([secret_player, secret_clip])
    coach = make_user(herd.id, 'coach', 'coach')
    player = make_user(herd.id, 'player', 'player')
    db.session.commit()
    return {
        'app': app, 'herd': herd.id, 'other': other.id, 'ours': [p.id for p in ours],
        'tour': tour.id, 'past': past.id, 'undated': undated.id, 'report': report.id,
        'secret': secret.id, 'secret_player': secret_player.id, 'secret_clip': secret_clip.id,
        'coach': stats_data.Client(app, coach.id, herd.id),
        'player': stats_data.Client(app, player.id, herd.id),
    }


def page(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


# ── Helpers ──────────────────────────────────────────────────────────────

def test_times_read_as_minutes_and_seconds():
    assert parse_time('90') == 90
    assert parse_time('1:30') == 90
    assert parse_time('1:01:30') == 3690
    for bad in ('1:75', 'abc', '1:2:3:4', ''):
        with pytest.raises(ValueError):
            parse_time(bad)
    assert format_time(90) == '1:30'
    assert format_time(3690) == '1:01:30'
    assert format_time(None) == ''


def test_moments_are_read_line_by_line():
    assert parse_moments('1:23 Huck\n\n2:00-2:10 Zone look\n') == [
        {'start': 83, 'end': None, 'label': 'Huck'},
        {'start': 120, 'end': 130, 'label': 'Zone look'},
    ]
    with pytest.raises(ValueError):
        parse_moments('no time here')
    with pytest.raises(ValueError):
        parse_moments('2:00-1:00 backwards')


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ&t=30',
    'https://youtu.be/dQw4w9WgXcQ?t=95',
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://youtube.com/shorts/dQw4w9WgXcQ',
    'https://www.youtube.com/live/dQw4w9WgXcQ?si=x',
])
def test_youtube_links_of_every_shape(url):
    assert extract_youtube_id(url) == 'dQw4w9WgXcQ'


def test_non_youtube_links_have_no_video():
    assert extract_youtube_id('https://vimeo.com/123456') is None
    assert extract_youtube_id(None) is None


def test_embed_urls_are_always_well_formed():
    clip = ScoutingClip(youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    assert clip.youtube_embed_url == 'https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0'
    clip.start_time, clip.end_time = 30, 45
    assert clip.youtube_embed_url == 'https://www.youtube.com/embed/dQw4w9WgXcQ?start=30&end=45&rel=0'
    assert clip.embed_url_for(10, autoplay=True) == 'https://www.youtube.com/embed/dQw4w9WgXcQ?start=10&autoplay=1&rel=0'
    assert clip.thumbnail_url == 'https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg'


def test_roster_lines():
    assert parse_roster('7 Jane Doe handler\n#12 Sam Lee (cutter)\n3. Alex Kim\nRiley\n\n  ') == [
        {'jersey_number': '7', 'name': 'Jane Doe', 'position': 'handler'},
        {'jersey_number': '12', 'name': 'Sam Lee', 'position': 'cutter'},
        {'jersey_number': '3', 'name': 'Alex Kim', 'position': None},
        {'jersey_number': None, 'name': 'Riley', 'position': None},
    ]


def test_opponent_names_match_loosely():
    assert opponent_key('  Bad   SKID ') == opponent_key('bad skid')


def test_threat_levels():
    p = OpponentPlayer(name='A', throwing_ability=5, cutting_ability=4)
    assert p.threat_level == 'elite'
    assert OpponentPlayer(name='B').threat_level is None
    key = OpponentPlayer(name='C', is_key_threat=True, throwing_ability=2)
    assert sorted([p, key], key=lambda x: x.sort_key)[0] is key


# ── Reports ──────────────────────────────────────────────────────────────

def test_report_list_shows_a_summary_of_each_report(scout):
    html = page(scout['coach'], '/scouting/')
    assert 'Slow to set the zone' in html            # the first weakness
    assert 'Vertical stack' in html                  # its tags
    assert 'Head-to-head' in html
    assert 'History &amp; head-to-head' in page(scout['coach'], '/scouting/?group=opponent')
    assert 'Secret Rivals' not in html


def test_report_form_lists_games_without_a_date(scout):
    html = page(scout['coach'], '/scouting/add')
    assert 'vs bad  skid (No date)' in html
    assert 'Nationals' in html


def test_coach_writes_a_report_with_tags_and_a_game_plan(scout):
    r = scout['coach'].post('/scouting/add', data={
        'team_name': 'Ring of Fire', 'date': '2026-07-01', 'tournament_id': scout['tour'], 'game_id': 0,
        'offense_tags': ['horizontal', 'hucks_early'], 'defense_tags': ['zone'],
        'game_plan': 'Force flick', 'o_line_plan': 'Starts: A, B', 'weaknesses': 'Tired legs',
    })
    assert r.status_code == 302
    report = ScoutingReport.query.filter_by(team_name='Ring of Fire').one()
    assert report.offense_tag_list == ['horizontal', 'hucks_early']
    assert report.defense_tags == 'zone'
    assert report.tournament_id == scout['tour'] and report.game_id is None
    html = page(scout['coach'], f'/scouting/{report.id}')
    assert 'Force flick' in html and 'Horizontal stack' in html and 'Zone' in html

    r = scout['coach'].post(f'/scouting/edit/{report.id}', data={
        'team_name': 'Ring of Fire', 'tournament_id': 0, 'game_id': scout['past'], 'defense_tags': []})
    assert r.status_code == 302
    db.session.expire_all()
    report = db.session.get(ScoutingReport, report.id)
    assert report.defense_tags is None and report.tournament_id is None and report.game_id == scout['past']


def test_report_cannot_use_another_teams_tournament(scout):
    other_tour = Tournament(name='Other tour', team_organization_id=scout['other'])
    db.session.add(other_tour)
    db.session.commit()
    r = scout['coach'].post('/scouting/add', data={'team_name': 'X', 'tournament_id': other_tour.id, 'game_id': 0})
    assert r.status_code == 200 and 'Not a valid choice' in r.get_data(as_text=True)
    assert ScoutingReport.query.filter_by(team_name='X').count() == 0


def test_new_report_from_a_game_is_filled_in(scout):
    html = page(scout['coach'], f"/scouting/add?game_id={scout['past']}")
    assert 'value="Bad Skid"' in html
    assert 'value="2026-05-01"' in html
    assert 'Start from that report' in html  # we scouted them before


def test_deleting_a_report_goes_back_to_the_list(scout):
    r = scout['coach'].post(f"/scouting/delete/{scout['report']}")
    assert r.status_code == 302 and r.headers['Location'].endswith('/scouting/')
    assert db.session.get(ScoutingReport, scout['report']) is None


def test_copy_starts_a_new_report_with_the_players_but_not_the_clips(scout):
    db.session.add_all([
        OpponentPlayer(scouting_report_id=scout['report'], name='Star', is_key_threat=True,
                       throwing_ability=5, matched_player_id=scout['ours'][0], team_organization_id=scout['herd']),
        ScoutingClip(scouting_report_id=scout['report'], title='Old clip', team_organization_id=scout['herd'],
                     youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
    ])
    db.session.commit()
    r = scout['coach'].post(f"/scouting/{scout['report']}/copy", data={'game_id': scout['undated']})
    assert r.status_code == 302
    new = ScoutingReport.query.filter(ScoutingReport.id != scout['report'],
                                      ScoutingReport.team_organization_id == scout['herd']).one()
    assert new.team_name == 'Bad Skid' and new.game_id == scout['undated']
    assert new.weaknesses == 'Slow to set the zone\nWeak backhand side'
    copied = new.players.one()
    assert copied.name == 'Star' and copied.is_key_threat and copied.matched_player_id == scout['ours'][0]
    assert new.clips.count() == 0


def test_list_filters_and_groups(scout):
    db.session.add_all([
        ScoutingReport(team_name='Ring of Fire', date=date(2026, 8, 1), defense_tags='zone',
                       tournament_id=scout['tour'], team_organization_id=scout['herd']),
        ScoutingReport(team_name='Undated Opp', team_organization_id=scout['herd']),
    ])
    db.session.commit()
    c = scout['coach']
    html = page(c, '/scouting/?q=ring')
    assert 'Ring of Fire' in html and 'Slow to set the zone' not in html
    html = page(c, '/scouting/?tag=zone')
    assert 'Ring of Fire' in html and 'Undated Opp' not in html
    html = page(c, f"/scouting/?tournament_id={scout['tour']}")
    assert 'Ring of Fire' in html and 'Undated Opp' not in html
    html = page(c, '/scouting/?date_from=2026-07-01')
    assert 'Ring of Fire' in html and 'Bad Skid' not in html
    html = page(c, '/scouting/?group=tournament')
    assert 'No tournament' in html and 'Nationals' in html
    html = page(c, '/scouting/')
    # Dated reports newest first, undated ones last
    assert html.index('Ring of Fire') < html.index('Bad Skid') < html.index('Undated Opp')
    html = page(c, '/scouting/?q=nobody')
    assert 'No reports match these filters' in html


def test_opponent_page_has_the_head_to_head(scout):
    html = page(scout['player'], '/scouting/opponent?name=BAD%20SKID')
    assert '1–0' in html            # one win, the undated unplayed game doesn't count
    assert 'Not played' in html


# ── Players ──────────────────────────────────────────────────────────────

def test_coach_adds_a_rated_key_threat_with_a_matchup(scout):
    rid = scout['report']
    r = scout['coach'].post(f'/scouting/{rid}/add_player', data={
        'name': 'Speedy', 'jersey_number': '7', 'position': 'cutter', 'cutting_ability': '5',
        'athletic_ability': '4', 'throwing_ability': '', 'is_key_threat': 'y',
        'matched_player_id': scout['ours'][1]})
    assert r.status_code == 302
    p = OpponentPlayer.query.filter_by(name='Speedy').one()
    assert (p.cutting_ability, p.athletic_ability, p.throwing_ability) == (5, 4, None)
    assert p.is_key_threat and p.matched_player_id == scout['ours'][1]
    html = page(scout['coach'], f'/scouting/{rid}/card')
    assert 'Speedy' in html and 'Herd Player 02' in html and 'Key threat' in html

    form = page(scout['coach'], f'/scouting/edit_player/{p.id}')
    assert re.search(r'id="cutting_ability-5"[^>]*checked', form)
    assert not re.search(r'id="throwing_ability-\d"[^>]*checked', form)


def test_matchups_only_offer_our_own_players(scout):
    outsider = stats_data.build_players(db.session.get(TeamOrganization, scout['other']), 1)[0]
    r = scout['coach'].post(f"/scouting/{scout['report']}/add_player",
                            data={'name': 'X', 'matched_player_id': outsider.id})
    assert r.status_code == 200
    assert OpponentPlayer.query.filter_by(name='X').count() == 0


def test_pasting_a_roster_adds_every_player(scout):
    rid = scout['report']
    r = scout['coach'].post(f'/scouting/{rid}/add_players', data={'roster': '7 Jane handler\n12 Sam (cutter)\nRiley'})
    assert r.status_code == 302
    assert sorted(p.name for p in db.session.get(ScoutingReport, rid).players) == ['Jane', 'Riley', 'Sam']
    r = scout['coach'].post(f'/scouting/{rid}/add_players', data={'roster': '   \n'})
    assert r.status_code == 200


def test_deleting_a_player_keeps_their_clips(scout):
    rid = scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Gone', team_organization_id=scout['herd'])
    db.session.add(p)
    db.session.flush()
    clip = ScoutingClip(scouting_report_id=rid, title='Of Gone', opponent_player_id=p.id,
                        youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ', team_organization_id=scout['herd'])
    db.session.add(clip)
    db.session.commit()
    assert scout['coach'].post(f'/scouting/delete_player/{p.id}').status_code == 302
    db.session.expire_all()
    clip = db.session.get(ScoutingClip, clip.id)
    assert clip is not None and clip.opponent_player_id is None


def test_deleting_one_of_our_players_clears_their_matchup(scout):
    admin = stats_data.build_admin(db.session.get(TeamOrganization, scout['herd']), 'boss', superadmin=False)
    db.session.add(UserOnboarding(user_id=admin.id, welcomed_role='admin', completed_steps=[]))
    p = OpponentPlayer(scouting_report_id=scout['report'], name='Marked', matched_player_id=scout['ours'][2],
                       team_organization_id=scout['herd'])
    db.session.add(p)
    db.session.commit()
    c = stats_data.Client(scout['app'], admin.id, scout['herd'])
    c.post(f"/team/delete_player/{scout['ours'][2]}")
    db.session.expire_all()
    assert db.session.get(Player, scout['ours'][2]) is None
    assert db.session.get(OpponentPlayer, p.id).matched_player_id is None


# ── Clips ────────────────────────────────────────────────────────────────

def test_clip_times_are_typed_as_minutes_and_seconds(scout):
    rid = scout['report']
    r = scout['coach'].post(f'/scouting/{rid}/add_clip', data={
        'title': 'Zone look', 'youtube_link': 'https://youtu.be/dQw4w9WgXcQ?t=95', 'start_time': '1:35',
        'end_time': '2:05', 'moments': '4:10 Again\n5:00-5:20 And again', 'opponent_player_id': 0})
    assert r.status_code == 302
    clip = ScoutingClip.query.filter_by(title='Zone look').one()
    assert (clip.start_time, clip.end_time) == (95, 125)
    assert clip.youtube_link == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    assert len(clip.moment_list) == 2
    html = page(scout['coach'], f'/scouting/{rid}/clips')
    assert 'embed/dQw4w9WgXcQ?start=95&amp;end=125&amp;autoplay=1' in html
    assert 'embed/dQw4w9WgXcQ?start=300&amp;end=320&amp;autoplay=1' in html
    assert '5:00–5:20 And again' in html
    form = page(scout['coach'], f'/scouting/edit_clip/{clip.id}')
    assert 'value="1:35"' in form and 'value="2:05"' in form


@pytest.mark.parametrize('data, error', [
    ({'youtube_link': 'https://vimeo.com/1234'}, 'not a YouTube video link'),
    ({'start_time': '2:00', 'end_time': '1:00'}, 'end must be after the start'),
    ({'start_time': '1:75'}, 'minutes:seconds'),
    ({'moments': 'whenever they huck'}, 'Start each line with a time'),
])
def test_clip_mistakes_are_explained(scout, data, error):
    form = {'title': 'T', 'youtube_link': 'https://youtu.be/dQw4w9WgXcQ', 'opponent_player_id': 0, **data}
    r = scout['coach'].post(f"/scouting/{scout['report']}/add_clip", data=form)
    assert r.status_code == 200 and error in r.get_data(as_text=True)
    assert ScoutingClip.query.filter_by(title='T').count() == 0


def test_clips_can_be_filtered_to_one_player(scout):
    rid = scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Star', team_organization_id=scout['herd'])
    db.session.add(p)
    db.session.flush()
    db.session.add_all([
        ScoutingClip(scouting_report_id=rid, title='Star huck', opponent_player_id=p.id, team_organization_id=scout['herd'],
                     youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
        ScoutingClip(scouting_report_id=rid, title='Team zone', team_organization_id=scout['herd'],
                     youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
    ])
    db.session.commit()
    html = page(scout['player'], f'/scouting/{rid}/clips?player={p.id}')
    assert 'Star huck' in html and 'Team zone' not in html
    assert '1 clip' in page(scout['player'], f'/scouting/{rid}/players')


# ── Games ────────────────────────────────────────────────────────────────

def test_game_page_offers_the_report_on_that_opponent(scout):
    html = page(scout['coach'], f"/games/{scout['undated']}")
    assert 'You scouted Bad Skid' in html and 'Link to this game' in html
    r = scout['coach'].post(f"/scouting/{scout['report']}/link_game",
                            data={'game_id': scout['undated'], 'next': f"/games/{scout['undated']}"})
    assert r.status_code == 302 and r.headers['Location'].endswith(f"/games/{scout['undated']}")
    assert db.session.get(ScoutingReport, scout['report']).game_id == scout['undated']
    html = page(scout['coach'], f"/games/{scout['undated']}")
    assert 'Game card' in html and 'Link to this game' not in html


def test_game_page_offers_to_scout_a_new_opponent(scout):
    game = Game(opponent='Brand New', team_organization_id=scout['herd'])
    db.session.add(game)
    db.session.commit()
    assert f'/scouting/add?game_id={game.id}' in page(scout['coach'], f'/games/{game.id}')


def test_game_day_links_to_the_game_card(scout):
    html = page(scout['coach'], f"/gameday/game/{scout['past']}")
    assert f"/scouting/{scout['report']}/card" in html


def test_linking_only_returns_to_this_site(scout):
    for evil in ('//evil.example/x', 'https://evil.example/', '/\\evil.example'):
        r = scout['coach'].post(f"/scouting/{scout['report']}/link_game", data={'game_id': 0, 'next': evil})
        assert r.headers['Location'].endswith(f"/scouting/{scout['report']}"), evil


def test_cannot_link_another_teams_game(scout):
    other_game = Game(opponent='Bad Skid', team_organization_id=scout['other'])
    db.session.add(other_game)
    db.session.commit()
    r = scout['coach'].post(f"/scouting/{scout['report']}/link_game", data={'game_id': other_game.id})
    assert r.status_code == 404
    assert db.session.get(ScoutingReport, scout['report']).game_id is None


# ── Who can do what ──────────────────────────────────────────────────────

def test_players_can_read_everything_but_change_nothing(scout):
    c, rid = scout['player'], scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Star', team_organization_id=scout['herd'])
    clip = ScoutingClip(scouting_report_id=rid, title='Clip', team_organization_id=scout['herd'],
                        youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    db.session.add_all([p, clip])
    db.session.commit()
    for url in ('/scouting/', f'/scouting/{rid}', f'/scouting/{rid}/players', f'/scouting/{rid}/clips',
                f'/scouting/{rid}/card', f'/scouting/view_clip/{clip.id}', '/scouting/opponent?name=Bad+Skid'):
        html = page(c, url)
        assert '/scouting/edit' not in html and '/scouting/delete' not in html, url
    for url in ('/scouting/add', f'/scouting/edit/{rid}', f'/scouting/{rid}/add_player', f'/scouting/{rid}/add_clip'):
        assert c.get(url).status_code == 302, url
    c.post(f'/scouting/delete/{rid}')
    c.post(f'/scouting/delete_player/{p.id}')
    c.post(f'/scouting/delete_clip/{clip.id}')
    c.post(f'/scouting/{rid}/copy')
    c.post(f'/scouting/edit/{rid}', data={'team_name': 'Renamed', 'tournament_id': 0, 'game_id': 0})
    db.session.expire_all()
    assert ScoutingReport.query.filter_by(team_organization_id=scout['herd']).count() == 1
    assert db.session.get(ScoutingReport, rid).team_name == 'Bad Skid'
    assert db.session.get(OpponentPlayer, p.id) and db.session.get(ScoutingClip, clip.id)


def test_coaches_see_the_edit_controls(scout):
    html = page(scout['coach'], f"/scouting/{scout['report']}")
    assert f"/scouting/edit/{scout['report']}" in html and f"/scouting/delete/{scout['report']}" in html


def test_another_teams_scouting_is_out_of_reach(scout):
    c, sid = scout['coach'], scout['secret']
    for url in (f'/scouting/{sid}', f'/scouting/{sid}/card', f'/scouting/{sid}/players', f'/scouting/{sid}/clips',
                f'/scouting/edit/{sid}', f"/scouting/edit_player/{scout['secret_player']}",
                f"/scouting/edit_clip/{scout['secret_clip']}", f"/scouting/view_clip/{scout['secret_clip']}"):
        assert c.get(url).status_code == 404, url
    for url in (f'/scouting/delete/{sid}', f'/scouting/{sid}/copy', f"/scouting/delete_player/{scout['secret_player']}",
                f"/scouting/delete_clip/{scout['secret_clip']}"):
        assert c.post(url).status_code == 404, url
    r = c.get('/scouting/opponent?name=Secret+Rivals')  # nothing on them for this team
    assert r.status_code == 302 and r.headers['Location'].endswith('/scouting/')


def test_delete_buttons_carry_the_form_token(scout, app):
    """With CSRF on, as in production, the delete buttons on each page work."""
    rid = scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Star', team_organization_id=scout['herd'])
    clip = ScoutingClip(scouting_report_id=rid, title='Clip', team_organization_id=scout['herd'],
                        youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    db.session.add_all([p, clip])
    db.session.commit()
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        c = scout['coach']
        for listing, action in ((f'/scouting/{rid}/players', f'/scouting/delete_player/{p.id}'),
                                (f'/scouting/{rid}/clips', f'/scouting/delete_clip/{clip.id}'),
                                ('/scouting/', f'/scouting/delete/{rid}')):
            html = page(c, listing)
            form = re.search(r'<form action="' + re.escape(action) + r'" method="post">\s*'
                             r'<input type="hidden" name="csrf_token" value="([^"]+)"', html)
            assert form, action
            assert c.post(action, data={'csrf_token': form.group(1)}).status_code == 302, action
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    db.session.expire_all()
    assert db.session.get(ScoutingReport, rid) is None
