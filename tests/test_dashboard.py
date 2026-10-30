"""The home page: what's next, what needs the player's answer, the coach's
"Needs attention" list, and the season, all from app/utils/dashboard.py."""
from datetime import date, time, timedelta

import pytest

from app import db
from app.models.clip import Clip
from app.models.clip_playlist import ClipPlaylist, ClipPlaylistItem
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.onboarding import UserOnboarding
from app.models.session import Attendance, SessionPlan, SessionRSVP
from app.models.theory import TheorySection, TheoryTopic
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.user import User
from app.utils.season import ensure_seasons
from tests import stats_data

TODAY = date.today()


def _user(team, username, role, player=None):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=role == 'admin', team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    if player is not None:
        player.user_id = user.id
    db.session.commit()
    return user


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    players = stats_data.build_players(team, 4)
    ensure_seasons(team.id)
    coach = _user(team, 'coach', 'coach')
    player_user = _user(team, 'sam', 'player', players[0])
    tournament = Tournament(name='Nationals', start_date=TODAY + timedelta(days=9),
                            end_date=TODAY + timedelta(days=10), location='Bristol',
                            rsvp_deadline=TODAY + timedelta(days=5), team_organization_id=team.id)
    session = SessionPlan(title='Zone offence', date=TODAY + timedelta(days=2), start_time=time(19, 30),
                          location='Sportpark', team_organization_id=team.id)
    db.session.add_all([tournament, session])
    db.session.commit()
    return {
        'app': app, 'team': team.id, 'tournament': tournament.id, 'session': session.id,
        'players': [p.id for p in players],
        'coach': stats_data.Client(app, coach.id, team.id),
        'player': stats_data.Client(app, player_user.id, team.id),
    }


def _page(client):
    r = client.get('/')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_player_sees_what_needs_their_answer(club):
    page = _page(club['player'])
    assert '2 things need you' in page
    assert f'data-row="session-{club["session"]}"' in page and f'data-row="tournament-{club["tournament"]}"' in page
    # The session card has the big buttons, the list has chips for both
    assert page.count(f'data-type="session" data-id="{club["session"]}"') == 2
    assert 'Reply by' in page or 'reply by' in page


def test_answering_on_the_home_page_saves_and_clears_it(club):
    c = club['player']
    r = c.post('/api/rsvp', json={'type': 'session', 'id': club['session'], 'status': 'attending'})
    assert r.get_json()['success']
    assert SessionRSVP.query.filter_by(session_id=club['session'], player_id=club['players'][0]).one().status == 'attending'
    page = _page(c)
    assert '1 thing needs you' in page
    assert f'class="ev needs" data-row="session-{club["session"]}"' not in page


def test_picked_player_sees_their_games(club):
    t = db.session.get(Tournament, club['tournament'])
    pid = club['players'][0]
    db.session.add(TournamentRSVP(tournament_id=t.id, player_id=pid, status='attending', selection='picked',
                                  team_organization_id=club['team']))
    game = Game(opponent='Clapham', date=t.start_date, start_time=time(9, 0), field='Field 3',
                tournament_id=t.id, our_score=0, their_score=0, team_organization_id=club['team'])
    db.session.add(game)
    db.session.flush()
    db.session.add(GamePlayer(game_id=game.id, player_id=pid, team_organization_id=club['team']))
    db.session.commit()

    # Not until the coach publishes the squad
    assert "You're picked" not in _page(club['player'])
    t = db.session.get(Tournament, club['tournament'])
    t.selection_published = True
    db.session.commit()
    page = _page(club['player'])
    assert "You're picked" in page and '09:00' in page and 'Field 3' in page and 'Clapham' in page


def test_coach_gets_needs_attention(club):
    t = db.session.get(Tournament, club['tournament'])
    game = Game(opponent='Hucks', date=t.start_date, tournament_id=t.id, our_score=0, their_score=0,
                team_organization_id=club['team'])
    db.session.add(game)
    db.session.commit()
    page = _page(club['coach'])
    assert 'Needs attention' in page and 'To read &amp; watch' not in page
    assert "4 haven&#39;t replied for Nationals" in page
    assert f'/tournaments/{t.id}/nudge' in page
    assert 'Squad for Nationals not published' in page
    assert '1 game at Nationals has no players' in page
    assert f'/sessions/{club["session"]}/nudge' in page


def test_coach_sees_everything_is_done(club):
    db.session.delete(db.session.get(Tournament, club['tournament']))
    db.session.delete(db.session.get(SessionPlan, club['session']))
    db.session.commit()
    # Everyone has an account, so there's no sign-up to chase either
    from app.models.player import Player
    from app.models.team_organization import TeamOrganization
    team = db.session.get(TeamOrganization, club['team'])
    for i, pid in enumerate(club['players'][1:]):
        _user(team, f'p{i}', 'player', db.session.get(Player, pid))
    page = _page(club['coach'])
    assert "You're all caught up" in page and 'needs you' not in page


def test_to_read_and_watch_lists_new_theory_and_playlists(club):
    section = TheorySection(name='Defence', slug='defence', team_organization_id=club['team'])
    db.session.add(section)
    db.session.flush()
    db.session.add(TheoryTopic(section_id=section.id, name='Zone: the cup', team_organization_id=club['team']))
    clip = Clip(title='Their zone', team_organization_id=club['team'])
    playlist = ClipPlaylist(title='Hammers film', team_organization_id=club['team'])
    db.session.add_all([clip, playlist])
    db.session.flush()
    db.session.add(ClipPlaylistItem(playlist_id=playlist.id, clip_id=clip.id, team_organization_id=club['team']))
    db.session.commit()
    page = _page(club['player'])
    assert 'Zone: the cup' in page and 'Hammers film' in page and 'Playlist · 1 clip' in page
    # Another team's topic never shows
    other = stats_data.build_team('Other', 'other')
    other_section = TheorySection(name='Secret', slug='secret', team_organization_id=other.id)
    db.session.add(other_section)
    db.session.flush()
    db.session.add(TheoryTopic(section_id=other_section.id, name='Their playbook', team_organization_id=other.id))
    db.session.commit()
    assert 'Their playbook' not in _page(club['player'])


def test_my_numbers_and_season(club):
    pid = club['players'][0]
    past = SessionPlan(title='Last week', date=TODAY - timedelta(days=7), team_organization_id=club['team'])
    missed = SessionPlan(title='Two weeks ago', date=TODAY - timedelta(days=14), team_organization_id=club['team'])
    db.session.add_all([past, missed])
    db.session.flush()
    db.session.add_all([
        Attendance(session_id=past.id, player_id=pid, status='present', team_organization_id=club['team']),
        Attendance(session_id=missed.id, player_id=club['players'][1], status='present', team_organization_id=club['team']),
    ])
    game = Game(opponent='Freespeed', date=TODAY - timedelta(days=3), our_score=15, their_score=11,
                team_organization_id=club['team'])
    db.session.add(game)
    db.session.flush()
    db.session.add(GamePlayer(game_id=game.id, player_id=pid, team_organization_id=club['team']))
    db.session.commit()
    ensure_seasons(club['team'])
    page = _page(club['player'])
    assert '50%' in page  # one of the two sessions where attendance was taken
    assert '1</b><span>Game played' in page
    assert 'W 15–11' in page and '1–0' in page


def test_other_teams_events_stay_off_the_page(club):
    other = stats_data.build_team('Other', 'other')
    db.session.add(Tournament(name='Their Cup', start_date=TODAY + timedelta(days=3), team_organization_id=other.id))
    db.session.add(SessionPlan(title='Their practice', date=TODAY + timedelta(days=1), team_organization_id=other.id))
    db.session.commit()
    for c in (club['player'], club['coach']):
        page = _page(c)
        assert 'Their Cup' not in page and 'Their practice' not in page


def test_other_squads_open_sessions_are_offered_not_asked(club):
    from app.models.schedule import TrainingSchedule
    from app.models.season import SeasonRoster, Squad
    team_id = club['team']
    ones, twos = Squad(name='1s', team_organization_id=team_id), Squad(name='2s', team_organization_id=team_id)
    db.session.add_all([ones, twos])
    db.session.flush()
    SeasonRoster.query.filter_by(player_id=club['players'][0]).update({'squad_id': ones.id})
    schedule = TrainingSchedule(name='2s Tuesdays', weekday=1, start_date=TODAY, others_welcome=True,
                                team_organization_id=team_id)
    db.session.add(schedule)
    db.session.flush()
    schedule.squads.append(twos)
    open_session = SessionPlan(title='2s open training', date=TODAY + timedelta(days=3), schedule_id=schedule.id,
                               team_organization_id=team_id)
    db.session.add(open_session)
    db.session.flush()
    open_session.squads.append(twos)
    db.session.delete(db.session.get(SessionPlan, club['session']))
    db.session.commit()
    page = _page(club['player'])
    assert '2s open training' in page and f'data-type="session" data-id="{open_session.id}"' in page
    assert f'class="ev needs" data-row="session-{open_session.id}"' not in page
    assert '1 thing needs you' in page  # just the tournament
