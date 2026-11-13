"""The main menu, grouped so it stays short: Training split into Plan /
Sessions / Squad with one Availability link for everyone, Strategy and Theory
merged into Playbook, Stats and Clips under Analysis, and the player's own inbox (My
Feedback, My Questions) in the account menu."""
import re

import pytest

from app import db
from tests import stats_data
from tests.test_teams import make_user

PAGE = '/team/'  # any page with the menu (Home sends new users to the welcome)


@pytest.fixture
def club(app, team):
    coach = make_user(team, 'navcoach', 'coach')
    player_user = make_user(team, 'navplayer', 'player')
    player = stats_data.build_players(team, 1)[0]
    player.user_id = player_user.id
    db.session.commit()
    return {'coach': stats_data.Client(app, coach.id, team.id),
            'player': stats_data.Client(app, player_user.id, team.id)}


def main_menu(html):
    return html[html.index('uc-nav-links'):html.index('uc-nav-right')]


def account_menu(html):
    return html[html.index('uc-user-menu'):html.index('uc-logout-row')]


def test_coach_menu_is_grouped(app, club):
    html = club['coach'].get(PAGE).get_data(as_text=True)
    menu = main_menu(html)
    for heading in ('>Plan<', '>Sessions<', '>Squad<'):
        assert heading in menu, heading
    # One Availability link (the squad grid), one Feedback link (the hub)
    assert 'href="/sessions/availability/grid"' in menu and 'Availability' in menu
    assert 'href="/feedback/"' in menu
    for old in ("Who's Coming", 'Who&#39;s Coming', 'My Availability', 'Player Feedback', 'My Feedback',
                'Game Stats', '> Strategy'):
        assert old not in menu, old
    # Theory sits in Playbook, Clips in Stats: no single-link top-level items
    assert re.search(r'Tactics\s*</a>\s*<ul class="dropdown-menu">', menu)
    assert '> Team &amp; Games' in menu and '> Tactics' in menu and '> Analysis' in menu
    assert menu.index('Tactics') < menu.index('href="/theory/"') < menu.index('Analysis') < menu.index('href="/clips/"')
    assert 'uc-on-tabbar' in menu  # Home is hidden from the phone menu


def test_player_menu_and_account_inbox(app, club):
    html = club['player'].get(PAGE).get_data(as_text=True)
    menu = main_menu(html)
    assert 'href="/sessions/availability"' in menu and 'href="/feedback/"' not in menu
    assert 'Leadership Hub' not in menu and '/sessions/schedules' not in menu
    inbox = account_menu(html)
    assert 'For you' in inbox and 'href="/feedback/mine"' in inbox and 'My Feedback' in inbox
    assert 'uc-user-dot' not in html  # nothing new yet
