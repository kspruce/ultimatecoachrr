"""Team isolation: users only see and change their own team's data, and only
superadmins can switch between teams (e.g. Thundering Herd and Herd 2028)."""
import pytest

from app import db
from app.models.feedback import PlayerFeedback
from app.models.fitness import FitnessMetric
from app.models.player import Player
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.models.user import User
from tests import stats_data


def make_user(team, username, role='coach', superadmin=False):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=role == 'admin', is_superadmin=superadmin,
                team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def two_teams(app):
    herd = stats_data.build_team('Thundering Herd', 'herd')
    herd28 = stats_data.build_team('Herd 2028', 'herd-2028')
    herd_player = stats_data.build_players(herd, 2)[0]
    other_player = stats_data.build_players(herd28, 2)[0]
    session_plan = SessionPlan(id=1, title='Herd session', team_organization_id=herd.id)
    tournament = Tournament(name='Herd tour', team_organization_id=herd.id)
    db.session.add_all([session_plan, tournament])
    db.session.commit()
    users = {
        'super': make_user(herd, 'kit', role='admin', superadmin=True).id,
        'herd_admin': make_user(herd, 'herdadmin', role='admin').id,
        'other_admin': make_user(herd28, 'otheradmin', role='admin').id,
        'other_coach': make_user(herd28, 'othercoach', role='coach').id,
        'herd_player_user': make_user(herd, 'playeruser', role='player').id,
    }
    fb = PlayerFeedback(player_id=herd_player.id, coach_id=users['herd_admin'],
                        content='Private note', context_tag='General')
    metric = FitnessMetric(name='Sprint', unit='s', team_organization_id=herd.id)
    db.session.add_all([fb, metric])
    db.session.commit()
    return {
        'herd': herd.id, 'herd28': herd28.id,
        'herd_player': herd_player.id, 'other_player': other_player.id,
        'feedback': fb.id, 'tournament': tournament.id, 'metric': metric.id,
        **users,
    }


def client_for(app, user_id, team_id=None):
    c = stats_data.Client(app, user_id, team_id)
    if team_id is None:
        with app.app_context():
            with c.client.session_transaction() as s:
                s.pop('current_team_id', None)
    return c


def current_team(app, client):
    with app.app_context():
        with client.client.session_transaction() as s:
            return s.get('current_team_id')


def test_superadmin_defaults_to_own_team_and_can_switch(app, two_teams):
    c = client_for(app, two_teams['super'])
    page = c.get('/teams/').get_data(as_text=True)
    assert 'Thundering Herd' in page and 'Herd 2028' in page
    assert current_team(app, c) == two_teams['herd']
    c.get(f"/teams/switch/{two_teams['herd28']}")
    assert current_team(app, c) == two_teams['herd28']


def test_superadmin_falls_back_when_saved_team_is_gone(app, two_teams):
    c = client_for(app, two_teams['super'], team_id=9999)
    c.get('/teams/')
    assert current_team(app, c) == two_teams['herd']


def test_team_admin_cannot_switch_or_see_other_teams(app, two_teams):
    c = client_for(app, two_teams['other_admin'], team_id=two_teams['herd'])
    page = c.get('/teams/').get_data(as_text=True)
    assert 'Herd 2028' in page and 'Thundering Herd' not in page
    c.get(f"/teams/switch/{two_teams['herd']}")
    with app.test_request_context():
        from flask_login import login_user
        from app.utils.team_filter import get_current_team_id
        login_user(db.session.get(User, two_teams['other_admin']))
        # Even with Herd's id in the session, a team admin works on their own team.
        from flask import session
        session['current_team_id'] = two_teams['herd']
        assert get_current_team_id() == two_teams['herd28']
    assert c.get(f"/teams/edit/{two_teams['herd']}").status_code == 302
    assert c.get('/teams/add').status_code == 302


def test_coach_cannot_read_or_change_another_teams_feedback(app, two_teams):
    c = client_for(app, two_teams['other_coach'])
    assert c.get(f"/players/{two_teams['herd_player']}/feedback").status_code == 404
    assert c.post(f"/feedback/{two_teams['feedback']}/delete").status_code == 404
    assert db.session.get(PlayerFeedback, two_teams['feedback']) is not None
    assert c.get('/sessions/1/feedback/quick').status_code == 404


def test_link_player_only_offers_your_own_unlinked_players(app, two_teams):
    c = client_for(app, two_teams['herd_player_user'])
    c.post('/auth/link_player', data={'player_id': two_teams['other_player']})
    assert db.session.get(Player, two_teams['other_player']).user_id is None
    c.post('/auth/link_player', data={'player_id': two_teams['herd_player']})
    db.session.expire_all()
    assert db.session.get(Player, two_teams['herd_player']).user_id == two_teams['herd_player_user']


def test_tournament_bulk_update_needs_coach_and_same_team(app, two_teams):
    player_client = client_for(app, two_teams['herd_player_user'])
    assert player_client.post(f"/tournaments/{two_teams['tournament']}/bulk-update").status_code in (302, 403)
    other = client_for(app, two_teams['other_admin'])
    assert other.post(f"/tournaments/{two_teams['tournament']}/bulk-update").status_code == 404


def test_fitness_page_is_limited_to_its_team(app, two_teams):
    other = client_for(app, two_teams['other_admin'])
    assert other.get(f"/fitness/player/{two_teams['herd_player']}").status_code == 404
    herd = client_for(app, two_teams['herd_admin'])
    assert herd.get(f"/fitness/player/{two_teams['herd_player']}").status_code == 200


def test_deleting_a_team_removes_its_data_and_nothing_else(app):
    """Run on Postgres too (TEST_DATABASE_URL): SQLite doesn't enforce FKs."""
    import json
    import os
    from sqlalchemy import func, select
    from app.models.team_organization import TeamOrganization
    from app.utils.season_import import import_season

    keep = stats_data.build_team('Thundering Herd', 'herd')
    keep_admin = stats_data.build_admin(keep, 'kit')
    stats_data.record_season(app, keep, keep_admin, stats_data.build_players(keep),
                             games_per_tournament=1, points_per_game=3)
    gone = stats_data.build_team('Herd 2028', 'herd-2028')
    gone_admin = stats_data.build_admin(gone, 'other', superadmin=False)
    gone_players = stats_data.build_players(gone)
    stats_data.record_season(app, gone, gone_admin, gone_players, seed=3,
                             games_per_tournament=1, points_per_game=3)
    fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
    with open(os.path.join(fixtures, 'sample_season.json')) as f:
        season = json.load(f)
    for team in (keep, gone):
        import_season(season, os.path.join(fixtures, 'season_images'), team.id)
    db.session.add(PlayerFeedback(player_id=gone_players[0].id, coach_id=gone_admin.id,
                                  content='x', context_tag='General'))
    db.session.commit()
    keep_id, gone_id = keep.id, gone.id

    def counts(team_id):
        out = {}
        for table in db.metadata.sorted_tables:
            if 'team_organization_id' in table.c:
                n = db.session.execute(select(func.count()).select_from(table)
                                       .where(table.c.team_organization_id == team_id)).scalar()
                if n:
                    out[table.name] = n
        return out

    before_keep = counts(keep_id)
    assert counts(gone_id)

    c = stats_data.Client(app, keep_admin.id, keep_id)
    r = c.post(f'/teams/delete/{gone_id}', data={'confirm_name': 'Herd 2028'})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(TeamOrganization, gone_id) is None
    assert counts(gone_id) == {}
    assert counts(keep_id) == before_keep
    assert PlayerFeedback.query.count() == 0
