"""The opt-in numbers on a tournament's squad table (app/utils/selection.py)."""
from datetime import date, timedelta

import pytest

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.onboarding import UserOnboarding
from app.models.session import Attendance, SessionPlan
from app.models.team_settings import TeamSettings
from app.models.tournament import Tournament
from app.models.user import User
from app.utils.season import ensure_seasons
from tests import stats_data

TODAY = date.today()


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    players = stats_data.build_players(team, 3)
    ensure_seasons(team.id)
    coach = User(username='coach', email='coach@example.com', role='coach', team_organization_id=team.id)
    coach.set_password('x')
    db.session.add(coach)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=coach.id, welcomed_role='coach', completed_steps=[]))
    tournament = Tournament(name='Nationals', start_date=TODAY + timedelta(days=9), team_organization_id=team.id)
    sessions = [SessionPlan(title=f'Training {i}', date=TODAY - timedelta(days=7 * (i + 1)),
                            team_organization_id=team.id) for i in range(4)]
    game = Game(opponent='Chevron', date=TODAY - timedelta(days=3), our_score=15, their_score=10,
                team_organization_id=team.id)
    db.session.add_all([tournament, game] + sessions)
    db.session.flush()
    # Player 1 came to three of four (once late); player 2 to one; player 3 has no marks
    marks = [(0, 0, 'present'), (1, 0, 'late'), (2, 0, 'present'), (3, 0, 'absent'),
             (0, 1, 'present'), (1, 1, 'absent'), (2, 1, 'excused'), (3, 1, 'absent')]
    for s, p, status in marks:
        db.session.add(Attendance(session_id=sessions[s].id, player_id=players[p].id, status=status,
                                  team_organization_id=team.id))
    db.session.add(GamePlayer(game_id=game.id, player_id=players[0].id))
    db.session.commit()
    return {'team': team.id, 'tournament': tournament.id, 'players': [p.id for p in players],
            'coach': stats_data.Client(app, coach.id, team.id)}


def _squad_tab(club):
    r = club['coach'].get(f'/tournaments/{club["tournament"]}?tab=squad')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_numbers_are_off_until_the_team_turns_them_on(club):
    page = _squad_tab(club)
    assert 'data-attendance' not in page and 'Turn it on in team settings' in page

    r = club['coach'].post('/team/settings/features', data={'selection_stats_enabled': 'on'})
    assert r.status_code == 302
    assert TeamSettings.query.filter_by(team_id=club['team']).one().selection_stats_enabled
    page = _squad_tab(club)
    assert 'data-attendance="75"' in page and 'data-attendance="25"' in page
    assert 'Hide these numbers' in page


def test_numbers_for_each_player(club):
    import re
    settings = TeamSettings.query.filter_by(team_id=club['team']).first() or TeamSettings(team_id=club['team'])
    settings.selection_stats_enabled = True
    db.session.add(settings)
    db.session.commit()
    page = _squad_tab(club)
    rows = {int(m.group(1)): m.group(2) for m in re.finditer(
        r'data-player-id="(\d+)"[^>]*?(data-attendance="[^>]*)>', page, re.S)}
    first, second, third = club['players']
    assert 'data-attendance="75" data-games="1"' in rows[first]
    assert 'data-attendance="25" data-games="0"' in rows[second]
    # Whole-club sessions count against someone who was never marked
    assert 'data-attendance="0" data-games="0"' in rows[third]
    # Nobody has enough recorded points for a rating
    assert all('data-per="-999"' in row for row in rows.values())
