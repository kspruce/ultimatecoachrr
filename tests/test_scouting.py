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
                                (f'/scouting/{rid}', f'/scouting/delete/{rid}')):
            html = page(c, listing)
            form = re.search(r'<form action="' + re.escape(action) + r'" method="post">\s*'
                             r'<input type="hidden" name="csrf_token" value="([^"]+)"', html)
            assert form, action
            assert c.post(action, data={'csrf_token': form.group(1)}).status_code == 302, action
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    db.session.expire_all()
    assert db.session.get(ScoutingReport, rid) is None


# ── Matchups ─────────────────────────────────────────────────────────────

from app.models.scouting import can_mark, matchup_reasons, suggest_matchups  # noqa: E402


def _opp(id, name, roles=None, key=False, gender=None, position=None, matched=None):
    return OpponentPlayer(id=id, name=name, threat_roles=roles, is_key_threat=key, gender=gender,
                          position=position, matched_player_id=matched)


def _ours(id, name, roles=None, gender=None):
    return Player(id=id, name=name, defensive_roles=roles, gender=gender)


def test_suggestions_answer_each_threat_with_the_right_defender():
    hucker = _opp(1, 'Hucker', 'hucker', key=True)
    deep = _opp(2, 'Deep', 'deep_threat', key=True)
    handler = _opp(3, 'Handler', 'main_handler', key=True)
    ours = [_ours(10, 'Wall', 'handler_d'), _ours(11, 'Stopper', 'huck_stopper'), _ours(12, 'Back', 'deep_d')]
    suggested = suggest_matchups([hucker, deep, handler], ours)
    assert {o: d.name for o, (d, _) in suggested.items()} == {1: 'Stopper', 2: 'Back', 3: 'Wall'}
    assert suggested[1][1] == [('Hucker', 'Huck stopper')]


def test_suggestions_use_each_defender_once_and_skip_taken_ones():
    a = _opp(1, 'A', 'hucker', key=True)
    b = _opp(2, 'B', 'hucker', key=True)
    c = _opp(3, 'C', 'hucker', key=True, matched=11)  # already has a marker
    ours = [_ours(10, 'One', 'huck_stopper'), _ours(11, 'Two', 'huck_stopper')]
    suggested = suggest_matchups([a, b, c], ours)
    assert list(suggested) == [1] and suggested[1][0].name == 'One'  # Two is taken by C


def test_mixed_matchups_keep_to_gender_match():
    her = _opp(1, 'Her', 'deep_threat', key=True, gender='female')
    him = _ours(10, 'Him', 'deep_d', gender='male')
    also = _ours(11, 'Also', 'deep_d', gender='female')
    assert not can_mark(her, him) and can_mark(her, also)
    assert suggest_matchups([her], [him, also])[1][0].name == 'Also'
    assert suggest_matchups([her], [him]) == {}
    him.gender_match = 'female'  # plays as a woman-matching player
    assert can_mark(her, him)


def test_position_stands_in_for_missing_threat_types():
    handler = _opp(1, 'H', key=True, position='handler')
    assert matchup_reasons(handler, _ours(10, 'W', 'handler_d')) == [('Main handler', 'Handler defender')]


def test_matchup_board_suggests_and_coach_applies(scout):
    c, rid = scout['coach'], scout['report']
    ours = [db.session.get(Player, i) for i in scout['ours']]
    ours[0].defensive_roles, ours[1].defensive_roles = 'handler_d', 'huck_stopper,deep_d'
    hucker = OpponentPlayer(scouting_report_id=rid, name='Hucker', threat_roles='hucker', is_key_threat=True,
                            team_organization_id=scout['herd'])
    handler = OpponentPlayer(scouting_report_id=rid, name='Handler', threat_roles='main_handler', is_key_threat=True,
                             team_organization_id=scout['herd'])
    bench = OpponentPlayer(scouting_report_id=rid, name='Bench', team_organization_id=scout['herd'])
    db.session.add_all([hucker, handler, bench])
    db.session.commit()
    html = page(c, f'/scouting/{rid}/matchups')
    assert 'Use all suggestions' in html and f'value="{hucker.id}:{ours[1].id}"' in html
    assert 'Other players (1)' in html  # the unrated, untyped player is out of the way

    assert c.post(f'/scouting/{rid}/matchups', data={'use': f'{hucker.id}:{ours[1].id}'}).status_code == 302
    db.session.expire_all()
    assert db.session.get(OpponentPlayer, hucker.id).matched_player_id == ours[1].id

    c.post(f'/scouting/{rid}/matchups', data={'use_all': '1'})
    db.session.expire_all()
    assert db.session.get(OpponentPlayer, handler.id).matched_player_id == ours[0].id

    # The dropdowns set (or clear) a marker; another team's player is ignored
    outsider = stats_data.build_players(db.session.get(TeamOrganization, scout['other']), 1)[0]
    c.post(f'/scouting/{rid}/matchups', data={f'match-{hucker.id}': 0, f'match-{bench.id}': outsider.id,
                                              f'match-{handler.id}': ours[0].id})
    db.session.expire_all()
    assert db.session.get(OpponentPlayer, hucker.id).matched_player_id is None
    assert db.session.get(OpponentPlayer, bench.id).matched_player_id is None

    card = page(c, f'/scouting/{rid}/card')
    assert 'Matchups' in card and 'Handler defender' in card and 'No marker yet:</strong> Hucker' in card
    detail = page(c, f'/scouting/{rid}')
    assert 'Handler defender vs main handler' in detail and 'No one on Hucker yet' in detail


def test_players_see_the_board_but_cannot_change_it(scout):
    rid = scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Star', is_key_threat=True, team_organization_id=scout['herd'])
    db.session.add(p)
    db.session.commit()
    html = page(scout['player'], f'/scouting/{rid}/matchups')
    assert 'Star' in html and 'Save matchups' not in html and '<select' not in html
    scout['player'].post(f'/scouting/{rid}/matchups', data={f'match-{p.id}': scout['ours'][0]})
    assert db.session.get(OpponentPlayer, p.id).matched_player_id is None
    assert scout['player'].get('/scouting/defenders').status_code == 302


def test_coach_sets_our_defenders_strengths(scout):
    first, second = scout['ours'][:2]
    page(scout['coach'], '/scouting/defenders')
    r = scout['coach'].post(f"/scouting/defenders?report={scout['report']}",
                            data={f'roles-{first}': ['deep_d', 'hassler', 'nonsense'], f'roles-{second}': []})
    assert r.headers['Location'].endswith(f"/scouting/{scout['report']}/matchups")
    db.session.expire_all()
    assert db.session.get(Player, first).defensive_roles == 'deep_d,hassler'
    assert db.session.get(Player, second).defensive_roles is None


def test_threat_types_are_set_on_the_player_form(scout):
    rid = scout['report']
    r = scout['coach'].post(f'/scouting/{rid}/add_player', data={
        'name': 'Bomber', 'threat_roles': ['hucker', 'break_thrower'], 'matched_player_id': 0})
    assert r.status_code == 302
    p = OpponentPlayer.query.filter_by(name='Bomber').one()
    assert p.threat_role_list == ['hucker', 'break_thrower'] and p.on_matchup_board
    r = scout['coach'].post(f'/scouting/edit_player/{p.id}?back=matchups',
                            data={'name': 'Bomber', 'matched_player_id': 0})
    assert r.headers['Location'].endswith(f'/scouting/{rid}/matchups')
    db.session.expire_all()
    assert db.session.get(OpponentPlayer, p.id).threat_roles is None


# ── Phone helpers: quick notes, look toggles, the offline card ───────────

AJAX = {'X-Requested-With': 'XMLHttpRequest'}


def test_quick_notes_land_in_the_right_place(scout):
    c, rid = scout['coach'], scout['report']
    p = OpponentPlayer(scouting_report_id=rid, name='Star', team_organization_id=scout['herd'])
    db.session.add(p)
    db.session.commit()
    r = c.post(f'/scouting/{rid}/note', data={'text': 'Zone   downwind', 'section': 'defense', 'time': '14:05'}, headers=AJAX)
    assert r.status_code == 200 and r.get_json() == {'success': True, 'message': 'Added to Defence.'}
    c.post(f'/scouting/{rid}/note', data={'text': 'Tired legs', 'section': 'weakness', 'time': '14:06'}, headers=AJAX)
    c.post(f'/scouting/{rid}/note', data={'text': 'Breaks the mark inside', 'section': f'player:{p.id}'}, headers=AJAX)
    r = c.post(f'/scouting/{rid}/note', data={'text': '  ', 'section': 'note'}, headers=AJAX)
    assert r.status_code == 400
    r = c.post(f'/scouting/{rid}/note', data={'text': 'x', 'section': f"player:{scout['secret_player']}"}, headers=AJAX)
    assert r.status_code == 400  # not a player on this report
    db.session.expire_all()
    report = db.session.get(ScoutingReport, rid)
    assert report.defense_strategy == '[14:05] Zone downwind'
    assert report.weaknesses.endswith('\nTired legs')  # a list line, no time stamp
    assert db.session.get(OpponentPlayer, p.id).notes == 'Breaks the mark inside'
    # Without JavaScript it's an ordinary form that comes back to the report
    r = c.post(f'/scouting/{rid}/note', data={'text': 'Plain', 'section': 'note'})
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/scouting/{rid}')


def test_looks_toggle_on_and_off(scout):
    c, rid = scout['coach'], scout['report']
    assert c.post(f'/scouting/{rid}/tag', data={'tag': 'zone'}, headers=AJAX).get_json()['on'] is True
    assert c.post(f'/scouting/{rid}/tag', data={'tag': 'vertical'}, headers=AJAX).get_json()['on'] is False
    assert c.post(f'/scouting/{rid}/tag', data={'tag': 'bogus'}, headers=AJAX).status_code == 400
    db.session.expire_all()
    report = db.session.get(ScoutingReport, rid)
    assert report.defense_tags == 'zone' and report.offense_tags is None


def test_players_cannot_add_notes_or_looks(scout):
    rid = scout['report']
    scout['player'].post(f'/scouting/{rid}/note', data={'text': 'x', 'section': 'note'}, headers=AJAX)
    scout['player'].post(f'/scouting/{rid}/tag', data={'tag': 'zone'}, headers=AJAX)
    report = db.session.get(ScoutingReport, rid)
    assert report.notes is None and report.defense_tags is None


def test_report_page_has_the_phone_tools(scout):
    html = page(scout['coach'], f"/scouting/{scout['report']}")
    assert 'id="quickNote"' in html and 'class="phone-bar' in html and 'class="section-bar' in html
    assert '1–0</strong> all time' in html
    assert 'id="quickNote"' not in page(scout['player'], f"/scouting/{scout['report']}")


def test_game_card_works_offline(scout):
    html = page(scout['coach'], f"/scouting/{scout['report']}/card")
    assert 'data-offline-card' in html and 'data-wake-lock' in html and 'data-rendered-at=' in html
    r = scout['coach'].get('/scouting/sw.js')
    assert r.status_code == 200 and r.mimetype == 'application/javascript'
    assert r.headers['Cache-Control'] == 'no-cache' and b'scouting-cards-' in r.data


def test_list_shows_removable_filter_chips(scout):
    html = page(scout['coach'], '/scouting/?q=bad&tag=vertical')
    assert 'Remove filter: &#34;bad&#34;' in html and 'Remove filter: Vertical stack' in html
    assert 'href="/scouting/?tag=vertical"' in html  # dropping the search keeps the look
