"""Seasons: a new season starts without losing anything, pages show the
current season unless another is picked, every season stays editable, and
squads keep separate rosters inside one club."""
from datetime import date

import pytest

from app import db
from app.models.game import Game
from app.models.onboarding import UserOnboarding
from app.models.player import Player
from app.models.point import LineUp, Point
from app.models.season import Season, SeasonRoster, Squad
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.utils.season import ensure_seasons
from tests import stats_data

THIS_YEAR = date.today().year
LAST_YEAR = THIS_YEAR - 1


def _game(team, day, opponent, players, ours=15, theirs=10, tournament=None):
    game = Game(opponent=opponent, date=day, our_score=ours, their_score=theirs,
                team_organization_id=team.id, tournament=tournament)
    db.session.add(game)
    db.session.flush()
    point = Point(game_id=game.id, point_number=1, our_line_type='O-line', starting_position='offense',
                  point_outcome='scored', team_organization_id=team.id)
    db.session.add(point)
    db.session.flush()
    for p in players:
        db.session.add(LineUp(point_id=point.id, player_id=p.id, team_organization_id=team.id))
    return game


@pytest.fixture
def club(app):
    """Two years of games: last year everyone but the newcomer played, this
    year one veteran has already stopped turning up."""
    team = stats_data.build_team()
    admin = stats_data.build_admin(team, superadmin=False)
    db.session.add(UserOnboarding(user_id=admin.id, welcomed_role='admin', completed_steps=[]))
    players = stats_data.build_players(team, 4)
    veteran, regular, other, newcomer = players
    old_tour = Tournament(name='Old open', start_date=date(LAST_YEAR, 6, 1), season=str(LAST_YEAR),
                          team_organization_id=team.id)
    db.session.add(old_tour)
    _game(team, date(LAST_YEAR, 6, 1), 'Old rivals', [veteran, regular, other], tournament=old_tour)
    _game(team, date(LAST_YEAR, 7, 1), 'Old friends', [veteran, regular], ours=8, theirs=15)
    _game(team, date(THIS_YEAR, 3, 1), 'New rivals', [regular, other, newcomer])
    db.session.add(SessionPlan(title='Old session', date=date(LAST_YEAR, 5, 1), team_organization_id=team.id))
    db.session.commit()
    client = stats_data.Client(app, admin.id, team.id)
    return {'team': team, 'admin': admin, 'client': client, 'veteran': veteran, 'regular': regular,
            'other': other, 'newcomer': newcomer}


def _seasons(team):
    db.session.expire_all()  # requests run in their own sessions
    return {s.year: s for s in Season.query.filter_by(team_organization_id=team.id)}


def _roster(season):
    return {r.player.name: r for r in season.roster}


def test_first_visit_sets_up_a_season_per_year_from_existing_data(club):
    team = club['team']
    assert club['client'].get('/').status_code == 200

    seasons = _seasons(team)
    assert set(seasons) == {LAST_YEAR, THIS_YEAR}
    assert seasons[THIS_YEAR].is_current and not seasons[LAST_YEAR].is_current
    # Every game, tournament and session is in its season
    assert {g.opponent: g.season.year for g in Game.query} == {
        'Old rivals': LAST_YEAR, 'Old friends': LAST_YEAR, 'New rivals': THIS_YEAR}
    assert Tournament.query.one().season_id == seasons[LAST_YEAR].id
    assert SessionPlan.query.one().season_id == seasons[LAST_YEAR].id
    # Rosters come from who played; everyone active is on the current one
    assert set(_roster(seasons[LAST_YEAR])) == {club['veteran'].name, club['regular'].name, club['other'].name}
    assert set(_roster(seasons[THIS_YEAR])) == {p.name for p in Player.query}
    # Running it again changes nothing
    assert ensure_seasons(team.id) is False


def test_pages_show_the_current_season_unless_another_is_picked(club):
    client = club['client']
    page = client.get('/games/').get_data(as_text=True)
    assert 'New rivals' in page and 'Old rivals' not in page

    # ?season= for one page, the switcher for every page after
    page = client.get(f'/games/?season={LAST_YEAR}').get_data(as_text=True)
    assert 'Old rivals' in page and 'New rivals' not in page
    assert client.get(f'/team/seasons/view?season={LAST_YEAR}&next=/games/').headers['Location'].endswith('/games/')
    page = client.get('/games/').get_data(as_text=True)
    assert 'Old rivals' in page and 'New rivals' not in page
    assert f'Back to {THIS_YEAR}' in page  # the past-season banner

    client.get('/team/seasons/view?season=all')
    page = client.get('/games/').get_data(as_text=True)
    assert 'Old rivals' in page and 'New rivals' in page


def test_season_switcher_only_goes_back_to_this_site(club):
    r = club['client'].get('/team/seasons/view?season=all&next=https://evil.example/x')
    assert r.status_code == 302 and 'evil.example' not in r.headers['Location']


def test_stats_and_homepage_count_this_season_only(club):
    client = club['client']
    home = client.get('/').get_data(as_text=True)
    assert f'Season {THIS_YEAR}' in home
    assert 'Old friends' not in client.get('/stats/team').get_data(as_text=True)
    csv = client.get('/stats/team/export.csv')
    assert f'team_season_stats_{THIS_YEAR}' in csv.headers['Content-Disposition']
    assert club['veteran'].name not in csv.get_data(as_text=True)  # didn't play this season

    client.get('/team/seasons/view?season=all')
    csv = client.get('/stats/team/export.csv').get_data(as_text=True)
    assert club['veteran'].name in csv


def test_starting_a_new_season_keeps_everything_and_updates_the_roster(club):
    team, client = club['team'], club['client']
    client.get('/')  # set the seasons up
    squad = Squad(team_organization_id=team.id, name='1s')
    db.session.add(squad)
    db.session.commit()
    keep = [club['regular'], club['newcomer']]
    data = {'year': THIS_YEAR + 1, 'start_date': f'{THIS_YEAR + 1}-02-01', 'end_date': f'{THIS_YEAR + 1}-11-30',
            'player_id': [str(p.id) for p in keep],
            f'jersey_{club["regular"].id}': '77', f'squad_{club["regular"].id}': str(squad.id)}
    r = client.post('/team/seasons/new', data=data)
    assert r.status_code == 302

    seasons = _seasons(team)
    new, old = seasons[THIS_YEAR + 1], seasons[THIS_YEAR]
    assert new.is_current and not old.is_current
    assert (new.start_date, new.end_date) == (date(THIS_YEAR + 1, 2, 1), date(THIS_YEAR + 1, 11, 30))
    assert set(_roster(new)) == {p.name for p in keep}
    assert _roster(new)[club['regular'].name].jersey_number == 77
    assert _roster(new)[club['regular'].name].squad_id == squad.id
    # Last season's roster stays, with the leavers marked as left
    old_roster = _roster(old)
    assert old_roster[club['other'].name].status == 'left'
    assert old_roster[club['regular'].name].status == 'active'
    # Nothing deleted: games, people and accounts are all still there
    assert Game.query.count() == 3 and Player.query.count() == 4
    # Players who left are no longer active (so pickers skip them) but keep their history
    active = {p.name for p in Player.query.filter_by(active=True)}
    assert active == {p.name for p in keep}
    assert club['regular'].name in active and db.session.get(Player, club['regular'].id).jersey_number == 77

    # The roster page now shows the new season; the old one is a pick away
    page = client.get('/team/').get_data(as_text=True)
    assert club['newcomer'].name in page and club['other'].name not in page
    page = client.get(f'/team/?season={THIS_YEAR}').get_data(as_text=True)
    assert club['other'].name in page
    # A player who left can still see their past seasons on their page
    page = client.get(f'/team/player/{club["other"].id}').get_data(as_text=True)
    assert str(LAST_YEAR) in page and str(THIS_YEAR) in page


def test_new_games_go_into_the_season_their_date_is_in(club):
    team = club['team']
    club['client'].get('/')
    seasons = _seasons(team)
    undated = Game(opponent='Undated', team_organization_id=team.id)
    old = Game(opponent='Late entry', date=date(LAST_YEAR, 9, 1), team_organization_id=team.id)
    future = Game(opponent='Far future', date=date(THIS_YEAR + 3, 5, 1), team_organization_id=team.id)
    db.session.add_all([undated, old, future])
    db.session.commit()
    assert undated.season_id == seasons[THIS_YEAR].id  # no date: the current season
    assert old.season_id == seasons[LAST_YEAR].id
    assert future.season.year == THIS_YEAR + 3 and not future.season.is_current

    # Changing the date moves it; picking a season by hand sticks
    old.date = date(THIS_YEAR, 4, 1)
    db.session.commit()
    assert old.season_id == seasons[THIS_YEAR].id
    old.season_id = seasons[LAST_YEAR].id
    db.session.commit()
    assert old.season_id == seasons[LAST_YEAR].id


def test_a_tournaments_games_follow_its_season_and_squad(club):
    team, client = club['team'], club['client']
    client.get('/')
    squad = Squad(team_organization_id=team.id, name='2s')
    db.session.add(squad)
    db.session.commit()
    tour = Tournament.query.one()
    r = client.post(f'/tournaments/edit/{tour.id}', data={
        'name': tour.name, 'start_date': f'{LAST_YEAR}-06-01', 'season': str(THIS_YEAR), 'squad_id': str(squad.id)})
    assert r.status_code == 302
    db.session.expire_all()
    tour = Tournament.query.one()
    assert tour.season_obj.year == THIS_YEAR and tour.season == str(THIS_YEAR)
    assert {(g.season.year, g.squad_id) for g in tour.games} == {(THIS_YEAR, squad.id)}


def test_past_seasons_stay_editable(club):
    team, client = club['team'], club['client']
    client.get('/')
    old = _seasons(team)[LAST_YEAR]
    row = _roster(old)[club['veteran'].name]
    r = client.post(f'/team/seasons/{old.id}/roster', data={
        f'jersey_{row.id}': '9', f'status_{row.id}': 'injured', f'position_{row.id}': 'cutter',
        'add_player_id': [str(club['newcomer'].id)]})
    assert r.status_code == 302
    roster = _roster(_seasons(team)[LAST_YEAR])
    assert roster[club['veteran'].name].jersey_number == 9 and roster[club['veteran'].name].status == 'injured'
    assert club['newcomer'].name in roster
    # Editing last season leaves this season (and who's active) alone
    db.session.expire_all()
    assert db.session.get(Player, club['veteran'].id).jersey_number == 1
    assert db.session.get(Player, club['veteran'].id).active

    r = client.post(f'/team/seasons/{old.id}/edit', data={'start_date': f'{LAST_YEAR}-03-01',
                                                         'end_date': f'{LAST_YEAR}-10-31'})
    assert r.status_code == 302 and _seasons(team)[LAST_YEAR].start_date == date(LAST_YEAR, 3, 1)


def test_marking_someone_left_on_the_current_roster_makes_them_inactive(club):
    team, client = club['team'], club['client']
    client.get('/')
    current = _seasons(team)[THIS_YEAR]
    row = _roster(current)[club['veteran'].name]
    client.post(f'/team/seasons/{current.id}/roster', data={f'status_{row.id}': 'left'})
    db.session.expire_all()
    veteran = db.session.get(Player, club['veteran'].id)
    assert not veteran.active and _roster(_seasons(team)[THIS_YEAR])[veteran.name].left_date


def test_seasons_with_data_cannot_be_deleted(club):
    team, client = club['team'], club['client']
    client.get('/')
    old = _seasons(team)[LAST_YEAR]
    client.post(f'/team/seasons/{old.id}/delete')
    assert LAST_YEAR in _seasons(team)
    client.post('/team/seasons/add', data={'year': '2001'})
    empty = _seasons(team)[2001]
    client.post(f'/team/seasons/{empty.id}/delete')
    assert 2001 not in _seasons(team)


def test_squads_keep_separate_rosters_and_stats(club):
    team, client = club['team'], club['client']
    client.get('/')
    client.post('/team/seasons/squads/add', data={'name': '1s'})
    client.post('/team/seasons/squads/add', data={'name': '2s'})
    ones, twos = Squad.query.order_by(Squad.sort_order).all()
    current = _seasons(team)[THIS_YEAR]
    rows = _roster(current)
    data = {f'squad_{rows[club["regular"].name].id}': str(ones.id),
            f'squad_{rows[club["newcomer"].name].id}': str(twos.id)}
    client.post(f'/team/seasons/{current.id}/roster', data=data)
    game = Game.query.filter_by(opponent='New rivals').one()
    game.squad_id = ones.id
    db.session.commit()

    client.get(f'/team/seasons/view?squad={twos.id}')
    page = client.get('/team/').get_data(as_text=True)
    assert club['newcomer'].name in page and club['regular'].name not in page
    assert 'New rivals' not in client.get('/games/').get_data(as_text=True)
    client.get(f'/team/seasons/view?squad={ones.id}')
    assert 'New rivals' in client.get('/games/').get_data(as_text=True)

    # Deleting a squad keeps its players and games
    client.post(f'/team/seasons/squads/{ones.id}/delete')
    assert Game.query.filter_by(opponent='New rivals').one().squad_id is None
    assert SeasonRoster.query.filter_by(player_id=club['regular'].id, season_id=current.id).one().squad_id is None


def test_one_club_cannot_touch_another_clubs_seasons(app, club):
    club['client'].get('/')
    other = stats_data.build_team('Other club', 'other')
    other_admin = stats_data.build_admin(other, 'otheradmin', superadmin=False)
    other_client = stats_data.Client(app, other_admin.id, other.id)
    season = _seasons(club['team'])[LAST_YEAR]
    assert other_client.get(f'/team/seasons/{season.id}/roster').status_code == 404
    assert other_client.post(f'/team/seasons/{season.id}/current').status_code == 404
    assert _seasons(club['team'])[THIS_YEAR].is_current


def test_players_cannot_manage_seasons(app, club):
    user = stats_data.build_admin(club['team'], 'justaplayer', superadmin=False)
    user.role, user.is_admin_flag = 'player', False
    db.session.commit()
    player_client = stats_data.Client(app, user.id, club['team'].id)
    assert player_client.get('/team/seasons/').status_code == 302
    r = player_client.post('/team/seasons/new', data={'year': THIS_YEAR + 1})
    assert r.status_code == 302 and THIS_YEAR + 1 not in _seasons(club['team'])
    # ...but they can still switch which season they're looking at
    assert player_client.get(f'/team/seasons/view?season={LAST_YEAR}').status_code == 302


def test_players_added_any_way_join_the_current_roster(club):
    team, client = club['team'], club['client']
    client.get('/')
    db.session.add(Player(name='Imported Player', jersey_number=30, active=True, team_organization_id=team.id))
    db.session.commit()
    client.post('/team/add_player', data={'name': 'Form Player', 'jersey_number': '31', 'active': 'y',
                                          'position': '', 'gender_match': '', 'line_preference': ''})
    roster = _roster(_seasons(team)[THIS_YEAR])
    assert roster['Imported Player'].jersey_number == 30
    assert SeasonRoster.query.join(Player).filter(Player.name == 'Form Player').count() == 1
    # ...so the next roster save doesn't switch them off
    current = _seasons(team)[THIS_YEAR]
    client.post(f'/team/seasons/{current.id}/roster', data={})
    db.session.expire_all()
    assert Player.query.filter_by(name='Imported Player').one().active
    assert Player.query.filter_by(name='Form Player').one().active
