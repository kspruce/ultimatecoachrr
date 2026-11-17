"""Club seasons that run across new year (October to September): changing a
season's dates moves everything dated in it into it, makes room among the
other seasons, and new seasons keep the same shape."""
from datetime import date, timedelta

import pytest

from app import db
from app.models.game import Game
from app.models.onboarding import UserOnboarding
from app.models.season import Season, SeasonRoster
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.utils import season as seasons
from tests import stats_data

OCT_4 = date(2027, 10, 4)


@pytest.fixture
def club(app):
    """A club whose 2027 season is the default calendar year, with a season
    plan's sessions every week from October 2027 to May 2028 (so the ones
    from January went into a 2028 season made for them)."""
    team = stats_data.build_team()
    admin = stats_data.build_admin(team, superadmin=False)
    db.session.add(UserOnboarding(user_id=admin.id, welcomed_role='admin', completed_steps=[]))
    db.session.add(Season(team_organization_id=team.id, year=2027, start_date=date(2027, 1, 1),
                          end_date=date(2027, 12, 31), is_current=True))
    db.session.flush()
    players = stats_data.build_players(team, 2)  # join the current (2027) roster
    for week in range(34):
        db.session.add(SessionPlan(title=f'Week {week + 1}', date=OCT_4 + timedelta(weeks=week),
                                   team_organization_id=team.id))
    tour = Tournament(name='Spring open', start_date=date(2028, 4, 1), team_organization_id=team.id)
    db.session.add(tour)
    db.session.flush()
    db.session.add(Game(opponent='Rivals', date=date(2028, 4, 1), our_score=15, their_score=9,
                        team_organization_id=team.id, tournament=tour))
    db.session.commit()
    return {'team': team, 'admin': admin, 'players': players,
            'client': stats_data.Client(app, admin.id, team.id)}


def by_year(team):
    db.session.expire_all()
    return {s.year: s for s in Season.query.filter_by(team_organization_id=team.id)}


def sessions_in(season):
    return SessionPlan.query.filter_by(season_id=season.id).count()


def test_before_the_change_the_plan_is_split_across_two_seasons(club):
    s = by_year(club['team'])
    assert set(s) == {2027, 2028}
    assert sessions_in(s[2027]) == 13 and sessions_in(s[2028]) == 21
    assert s[2027].name == '2027'


def test_matching_the_playing_season_brings_everything_together(club):
    team, client = club['team'], club['client']
    season = by_year(team)[2027]
    r = client.post(f'/team/seasons/{season.id}/edit',
                    data={'start_date': '2027-09-01', 'end_date': '2028-08-31'})
    assert r.status_code == 302

    s = by_year(team)
    assert set(s) == {2027}  # the 2028 season made for the January sessions had nothing left
    assert s[2027].name == '2027/28' and s[2027].is_current
    assert sessions_in(s[2027]) == 34
    tour = Tournament.query.one()
    assert tour.season_id == s[2027].id and tour.season == '2027/28'
    assert Game.query.one().season_id == s[2027].id
    # The roster is untouched
    assert SeasonRoster.query.filter_by(season_id=s[2027].id).count() == 2


def test_the_message_says_what_moved(club):
    team = club['team']
    season = by_year(team)[2027]
    report = seasons.change_dates(season, date(2027, 9, 1), date(2028, 8, 31))
    assert report['moved'] == {'games': 1, 'tournaments': 1, 'sessions': 21}
    assert report['removed'] == ['2028'] and report['trimmed'] == []


def test_a_season_with_a_roster_is_shortened_not_removed(club):
    team = club['team']
    s = by_year(team)
    db.session.add(SeasonRoster(team_organization_id=team.id, season_id=s[2028].id,
                                player_id=club['players'][0].id))
    db.session.commit()
    report = seasons.change_dates(s[2027], date(2027, 9, 1), date(2028, 8, 31))
    db.session.commit()
    s = by_year(team)
    assert report['trimmed'] == ['2028'] and report['removed'] == []
    assert s[2028].start_date == date(2028, 9, 1) and s[2028].end_date == date(2028, 12, 31)
    assert sessions_in(s[2027]) == 34 and sessions_in(s[2028]) == 0


def test_dates_that_swallow_the_current_season_are_refused(club):
    team, client = club['team'], club['client']
    s = by_year(team)
    r = client.post(f'/team/seasons/{s[2028].id}/edit',
                    data={'start_date': '2026-06-01', 'end_date': '2028-12-31'})
    assert r.status_code == 302
    s = by_year(team)
    assert s[2028].start_date == date(2028, 1, 1)  # unchanged
    assert s[2027].start_date == date(2027, 1, 1)
    with pytest.raises(seasons.SeasonDatesError):
        seasons.change_dates(s[2028], date(2026, 6, 1), date(2028, 12, 31))


def test_start_after_end_is_refused(club):
    season = by_year(club['team'])[2027]
    with pytest.raises(seasons.SeasonDatesError):
        seasons.change_dates(season, date(2028, 1, 1), date(2027, 1, 1))


def test_later_seasons_keep_the_same_shape(club):
    team = club['team']
    seasons.change_dates(by_year(team)[2027], date(2027, 9, 1), date(2028, 8, 31))
    db.session.commit()

    # A session dated after the season ends makes a September-to-August season
    db.session.add(SessionPlan(title='Next year', date=date(2028, 10, 5), team_organization_id=team.id))
    db.session.commit()
    s = by_year(team)
    assert s[2028].start_date == date(2028, 9, 1) and s[2028].end_date == date(2029, 8, 31)
    assert s[2028].name == '2028/29'
    assert SessionPlan.query.filter_by(title='Next year').one().season_id == s[2028].id

    # And Start new season offers the same shape
    html = club['client'].get('/team/seasons/').get_data(as_text=True)
    assert 'Start 2028/29 season' in html
    html = club['client'].get('/team/seasons/new?year=2029').get_data(as_text=True)
    assert 'Start the 2029/30 season' in html and 'value="2029-09-01"' in html


def test_shaped_dates_avoid_other_seasons():
    a = Season(year=2027, start_date=date(2027, 9, 1), end_date=date(2028, 8, 31), is_current=True)
    assert seasons.shaped_dates(2028, [a]) == (date(2028, 9, 1), date(2029, 8, 31))
    # A calendar-year club stays calendar-year
    b = Season(year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_current=True)
    assert seasons.shaped_dates(2027, [b]) == (date(2027, 1, 1), date(2027, 12, 31))
    # Trimmed where it would overlap
    c = Season(year=2027, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), is_current=True)
    d = Season(year=2028, start_date=date(2028, 1, 1), end_date=date(2028, 3, 31))
    assert seasons.shaped_dates(2029, [c, d])[0] == date(2029, 1, 1)
    assert Season.default_dates(2028, like=Season(start_date=date(2024, 2, 29)))[0] == date(2028, 2, 29)
    assert Season.default_dates(2027, like=Season(start_date=date(2024, 2, 29)))[0] == date(2027, 2, 28)


def test_the_sessions_list_shows_the_whole_playing_season(club):
    team, client = club['team'], club['client']
    seasons.change_dates(by_year(team)[2027], date(2027, 9, 1), date(2028, 8, 31))
    db.session.commit()
    html = client.get('/sessions/?show=all').get_data(as_text=True)
    assert 'All dates <span>34</span>' in html


def test_new_seasons_follow_the_latest_not_the_current(app):
    """Still in a calendar-year season, with next season already set to run
    September to August: the season after that is shaped like next season."""
    team = stats_data.build_team()
    db.session.add_all([
        Season(team_organization_id=team.id, year=2026, start_date=date(2026, 1, 1),
               end_date=date(2026, 12, 31), is_current=True),
        Season(team_organization_id=team.id, year=2027, start_date=date(2027, 9, 1),
               end_date=date(2028, 8, 31))])
    db.session.commit()
    db.session.add(SessionPlan(title='Later', date=date(2028, 10, 1), team_organization_id=team.id))
    db.session.commit()
    made = Season.query.filter_by(team_organization_id=team.id, year=2028).one()
    assert (made.start_date, made.end_date) == (date(2028, 9, 1), date(2029, 8, 31))
