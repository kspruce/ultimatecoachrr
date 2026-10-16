"""Builds a realistic, deterministic stats dataset by recording games through
the same endpoints the stat-taker screen uses (/stats/record, finish_point,
record_cutting_skill). Used by the stats tests and for before/after
comparisons when refactoring the stats code."""
import random
from datetime import date, timedelta

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point, LineUp
from app.models.team_organization import TeamOrganization
from app.models.tournament import Tournament
from app.models.user import User

FIELD_LENGTH = 100.0
FIELD_WIDTH = 37.0


def _login(client, user_id, team_id):
    with client.session_transaction() as s:
        s['_user_id'] = str(user_id)
        s['_fresh'] = True
        s['current_team_id'] = team_id


def build_team(name='Thundering Herd', slug='herd'):
    team = TeamOrganization(name=name, slug=slug, division='mixed')
    db.session.add(team)
    db.session.commit()
    return team


def build_admin(team, username='admin', superadmin=True):
    user = User(username=username, email=f'{username}@example.com', role='admin',
                is_admin_flag=True, is_superadmin=superadmin, team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.commit()
    return user


def build_players(team, count=16):
    players = []
    for i in range(count):
        gender = 'female' if i % 2 == 0 else 'male'
        players.append(Player(
            name=f'{team.slug.title()} Player {i + 1:02d}', jersey_number=i + 1,
            gender=gender, position='handler' if i % 3 == 0 else 'cutter',
            active=True, team_organization_id=team.id))
    db.session.add_all(players)
    db.session.commit()
    return players


class Client:
    """Test client that runs each request in its own app context, as in
    production (the app's teardown_request discards the DB session)."""

    def __init__(self, app, user_id, team_id):
        self.app = app
        self.client = app.test_client()
        with app.app_context():
            _login(self.client, user_id, team_id)

    def get(self, url, **kw):
        with self.app.app_context():
            return self.client.get(url, **kw)

    def post(self, url, **kw):
        with self.app.app_context():
            return self.client.post(url, **kw)

    def put(self, url, **kw):
        with self.app.app_context():
            return self.client.put(url, **kw)


def _play_point(client, rng, point_id, line_type, line):
    """Post a plausible sequence of events for one point."""
    def post(player_id, event_type, x, y, **extra):
        payload = {'player_id': player_id, 'event_type': event_type,
                   'field_position_x': round(x, 1), 'field_position_y': round(y, 1),
                   'is_offensive': extra.pop('is_offensive', True), **extra}
        r = client.post(f'/stats/record/{point_id}', json=payload)
        assert r.status_code == 201, r.get_data(as_text=True)

    on_offence = line_type == 'O-line'
    x, y = 20.0, FIELD_WIDTH / 2
    if not on_offence:
        if rng.random() < 0.45:
            post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
            return
        post(rng.choice(line), rng.choice(['block', 'block', 'forced_turnover']),
             rng.uniform(30, 80), rng.uniform(3, 34), is_offensive=False)
        if rng.random() < 0.08:
            post(rng.choice(line), 'callahan', 95, rng.uniform(5, 30), is_offensive=False)
            return
    holder = rng.choice(line)
    post(holder, 'catch', x, y)
    for _ in range(rng.randint(2, 9)):
        receiver = rng.choice([p for p in line if p != holder])
        x = min(FIELD_LENGTH - 1, x + rng.uniform(-8, 22))
        y = max(1, min(FIELD_WIDTH - 1, y + rng.uniform(-14, 14)))
        roll = rng.random()
        if roll < 0.10:
            post(holder, 'throwaway', x, y)
            # They work it back and score, or we get it back and score.
            if rng.random() < 0.5:
                post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
                return
            post(rng.choice(line), 'block', x, y, is_offensive=False)
            holder = rng.choice(line)
            post(holder, 'catch', x, y)
            continue
        if roll < 0.15:
            post(receiver, 'drop', x, y)
            post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
            return
        post(receiver, 'catch', x, y)
        holder = receiver
    scorer = rng.choice([p for p in line if p != holder])
    post(scorer, 'goal', rng.uniform(90, 99), rng.uniform(3, 34))
    if rng.random() < 0.5:
        client.post(f'/stats/record_cutting_skill/{point_id}', json={
            'player_id': scorer, 'cutting_type': rng.choice(['open_deep', 'open_under',
                                                             'break_deep', 'break_under']),
            'outcome': rng.choice(['open_thrown_to', 'guarded_thrown_to', 'open_looked_off']),
            'field_position_x': 80, 'field_position_y': 18})


def record_season(app, team, admin, players, seed=7, games_per_tournament=3,
                  points_per_game=11):
    """Two tournaments in the 2026 season, recorded through the stat endpoints.
    Returns a logged-in Client."""
    rng = random.Random(seed)
    team_id, slug = team.id, team.slug
    women = [p.id for p in players if p.gender == 'female']
    men = [p.id for p in players if p.gender == 'male']
    client = Client(app, admin.id, team_id)

    start = date(2026, 5, 2)
    for t_index, t_name in enumerate(['Tour 1', 'Tour 2']):
        t_start = start + timedelta(days=28 * t_index)
        tournament = Tournament(name=f'{slug} {t_name}', season='2026', start_date=t_start,
                                team_organization_id=team_id)
        db.session.add(tournament)
        db.session.commit()
        tournament_id = tournament.id
        for g in range(games_per_tournament):
            game = Game(tournament_id=tournament_id, opponent=f'Opponent {chr(65 + g)}',
                        date=t_start + timedelta(days=g // 2), team_organization_id=team_id)
            db.session.add(game)
            db.session.commit()
            game_id = game.id
            ours = theirs = 0
            for n in range(1, points_per_game + 1):
                line_type = 'O-line' if n % 2 == 1 else 'D-line'
                four_women = n % 4 < 2
                point = Point(game_id=game_id, point_number=n, our_line_type=line_type,
                              our_score_before=ours, their_score_before=theirs,
                              starting_position='offense' if line_type == 'O-line' else 'defense',
                              point_outcome='scored', gender_ratio='4F3M' if four_women else '3F4M',
                              majority_gender='female' if four_women else 'male',
                              team_organization_id=team_id)
                db.session.add(point)
                db.session.commit()
                point_id = point.id
                n_women = 4 if four_women else 3
                line = rng.sample(women, n_women) + rng.sample(men, 7 - n_women)
                db.session.add_all([LineUp(point_id=point_id, player_id=pid,
                                           team_organization_id=team_id) for pid in line])
                db.session.commit()
                _play_point(client, rng, point_id, line_type, line)
                r = client.post(f'/stats/finish_point/{point_id}')
                assert r.status_code == 200, r.get_data(as_text=True)
                db.session.expire_all()
                point = db.session.get(Point, point_id)
                ours, theirs = point.our_score_after, point.their_score_after
    return client
