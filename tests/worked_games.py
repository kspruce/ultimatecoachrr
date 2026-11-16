"""Tiny games, recorded play by play through the same endpoints as the stat
taker (/stats/record, /stats/finish_point), for tests whose answers can be
worked out on paper. See tests/test_stats_worked.py.

A play is (event, who, x, y):
- event: catch, goal, throwaway, drop, stall, block, forced_turnover,
  unforced_turnover, callahan, scored_on;
- who: a player letter ('A'...'G'), 'opp' (the other team) or '?' (one of
  ours, not identified);
- x, y: metres, attacking the right-hand endzone (x 0-100 upfield, y 0-37
  across; the attacking endzone starts at 82).
"""
from datetime import date

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.point import LineUp, Point
from app.models.tournament import Tournament
from tests import stats_data

LETTERS = 'ABCDEFG'
DEFENCE = {'block', 'forced_turnover', 'unforced_turnover', 'callahan', 'scored_on'}


class WorkedGame:
    """One team, seven players (A-G, A-C-E-G women) and a game to add
    points to."""

    def __init__(self, app, opponent='Opponent A', game_date=date(2027, 5, 1)):
        self.app = app
        self.team = stats_data.build_team()
        self.admin = stats_data.build_admin(self.team)
        self.players = {}
        for i, letter in enumerate(LETTERS):
            p = Player(name=f'Player {letter}', jersey_number=i + 1,
                       gender='female' if i % 2 == 0 else 'male', active=True,
                       team_organization_id=self.team.id)
            db.session.add(p)
            self.players[letter] = p
        db.session.commit()
        self.ids = {k: p.id for k, p in self.players.items()}
        self.client = stats_data.Client(app, self.admin.id, self.team.id)
        self.tournament = Tournament(name='Worked Tour', season='2027', start_date=game_date,
                                     team_organization_id=self.team.id)
        db.session.add(self.tournament)
        db.session.commit()
        self.game_id = self.new_game(opponent, game_date)

    def new_game(self, opponent, game_date):
        game = Game(tournament_id=self.tournament.id, opponent=opponent, date=game_date,
                    team_organization_id=self.team.id)
        db.session.add(game)
        db.session.commit()
        self.game_id = game.id
        self.score = (0, 0)
        self.number = 0
        return game.id

    def point(self, start, plays, line=LETTERS, force='forehand', finish=True):
        """Add the next point: start is 'O' or 'D'. Returns its id. A point
        whose plays end without a goal is left without a result (the cap or
        the end of a half), unless finish is True and it has one."""
        self.number += 1
        ours, theirs = self.score
        point = Point(game_id=self.game_id, point_number=self.number,
                      our_line_type='O-line' if start == 'O' else 'D-line',
                      starting_position='offense' if start == 'O' else 'defense',
                      our_score_before=ours, their_score_before=theirs,
                      gender_ratio='4F3M', force_direction=force,
                      team_organization_id=self.team.id)
        db.session.add(point)
        db.session.commit()
        point_id = point.id
        db.session.add_all([LineUp(point_id=point_id, player_id=self.ids[k],
                                   team_organization_id=self.team.id) for k in line])
        db.session.commit()
        for event, who, x, y in plays:
            payload = {'event_type': event, 'field_position_x': x, 'field_position_y': y,
                       'is_offensive': event not in DEFENCE}
            if who == 'opp':
                payload['is_opponent'] = True
            elif who == '?':
                payload['is_unknown_player'] = True
            else:
                payload['player_id'] = self.ids[who]
            r = self.client.post(f'/stats/record/{point_id}', json=payload)
            assert r.status_code == 201, r.get_data(as_text=True)
        if finish and plays and plays[-1][0] in ('goal', 'callahan', 'scored_on'):
            r = self.client.post(f'/stats/finish_point/{point_id}')
            assert r.status_code == 200, r.get_data(as_text=True)
        db.session.expire_all()
        point = db.session.get(Point, point_id)
        if point.point_outcome:
            self.score = (point.our_score_after, point.their_score_after)
        return point_id

    def game(self, game_id=None):
        return db.session.get(Game, game_id or self.game_id)

    def games(self):
        return Game.query.filter_by(team_organization_id=self.team.id).order_by(Game.id).all()

    def context(self):
        """A request context signed in as the team's admin (for calling the
        app/stats functions directly)."""
        from flask_login import login_user
        from app.models.user import User
        ctx = self.app.test_request_context()
        ctx.push()
        login_user(db.session.get(User, self.admin.id))
        return ctx
