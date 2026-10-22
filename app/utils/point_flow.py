"""Point-to-point logic shared by Positional Analysis setup and recording:
who can play, the ABBA ratio, O/D, the line to suggest and the score."""
from sqlalchemy import or_

from app import db
from app.models.event import Event
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.models.point import Point
from app.utils.team_filter import get_current_team_id

RATIOS = ('4-3', '3-4')


def _points(game):
    return Point.query.filter_by(
        game_id=game.id,
        team_organization_id=get_current_team_id()
    )


def get_game_roster(game, include_ids=()):
    """Players assigned to the game, by jersey number.

    Falls back to the full active roster when nobody is assigned (games
    created before auto-assign), as the gameday screen does. include_ids
    keeps players already on a point's line listed when editing it, even
    if they have since been taken off the game.
    """
    team_id = get_current_team_id()
    players = (
        Player.query
        .join(GamePlayer, GamePlayer.player_id == Player.id)
        .filter(
            GamePlayer.game_id == game.id,
            # Bulk assignment used to save rows without a team id; the game
            # is already this team's, so those rows count too.
            or_(GamePlayer.team_organization_id == team_id,
                GamePlayer.team_organization_id.is_(None)),
            Player.team_organization_id == team_id,
        )
        .all()
    )
    if not players:
        players = Player.query.filter_by(
            active=True,
            team_organization_id=team_id
        ).all()

    listed = {p.id for p in players}
    missing = [pid for pid in include_ids if pid not in listed]
    if missing:
        players += Player.query.filter(
            Player.id.in_(missing),
            Player.team_organization_id == team_id
        ).all()

    return sorted(players, key=lambda p: (p.jersey_number is None, p.jersey_number or 0, p.name))


def abba_ratio(game, point_number):
    """The mixed ratio for a point under ABBA: the first point's ratio (A)
    on points 1, 4, 5, 8, 9…, the other one (B) on 2, 3, 6, 7…. A is
    whatever the game's first point was played at, 4-3 if none yet."""
    first = _points(game).order_by(Point.point_number).first()
    a = first.gender_ratio if first and first.gender_ratio in RATIOS else '4-3'
    b = '3-4' if a == '4-3' else '4-3'
    return a if (point_number - 1) % 4 in (0, 3) else b


def is_second_half_start(game, previous_point):
    """True when halftime was called right after previous_point."""
    return (
        previous_point is not None
        and game.halftime_our_score is not None
        and game.halftime_their_score is not None
        and bool(previous_point.point_outcome)
        and previous_point.our_score_after == game.halftime_our_score
        and previous_point.their_score_after == game.halftime_their_score
    )


def determine_line_and_position(game, previous_point):
    """Whether the next point starts on O or D, and why.

    After a goal the scoring team pulls, so we start on D after we score
    and on O after they score. The first point of the second half goes
    the other way from the first point of the game. Returns
    (starting_position, reason); starting_position is None when there is
    nothing to go on and the form defaults should stand.
    """
    if not previous_point:
        return None, None

    def short(position):
        return 'O' if position == 'offense' else 'D'

    if is_second_half_start(game, previous_point):
        first_point = _points(game).order_by(Point.point_number).first()
        if first_point and first_point.starting_position in ('offense', 'defense'):
            flipped = 'defense' if first_point.starting_position == 'offense' else 'offense'
            return flipped, (
                f'Second half: we started the game on {short(first_point.starting_position)}, '
                f'so we start this half on {short(flipped)}.'
            )

    if previous_point.point_outcome == 'scored':
        return 'defense', f'We scored point {previous_point.point_number}, so we pull.'
    if previous_point.point_outcome == 'conceded':
        return 'offense', f'They scored point {previous_point.point_number}, so we receive.'

    # Previous point not finished yet: carry its side over rather than guess.
    return previous_point.starting_position, (
        f'Point {previous_point.point_number} has no result yet, so this '
        f'follows its line. Finish it to set O/D automatically.'
    )


def line_type_for(position):
    return 'O-line' if position == 'offense' else 'D-line'


def suggested_line(game, position, roster_ids):
    """The seven who played our last point on the same side (O or D),
    limited to players still on the game's roster."""
    last_same_side = _points(game).filter_by(
        starting_position=position
    ).order_by(Point.point_number.desc()).first()
    if not last_same_side:
        return [], None
    line = [lu.player_id for lu in last_same_side.lineups if lu.player_id in roster_ids]
    return line, last_same_side.point_number


def next_point_to_analyse(game, after_number=0):
    """The first point after after_number with no events recorded, such as
    a point taken live on Game Day that hasn't been analysed yet."""
    has_events = db.session.query(Event.id).filter(Event.point_id == Point.id).exists()
    return _points(game).filter(
        Point.point_number > after_number,
        ~has_events
    ).order_by(Point.point_number).first()


def analysis_progress(game):
    """How many of the game's points have full stats, how many only the
    Game Day record, and the next one to analyse."""
    has_events = db.session.query(Event.id).filter(Event.point_id == Point.id).exists()
    total = _points(game).count()
    waiting = _points(game).filter(~has_events).count()
    return {'total': total, 'analysed': total - waiting, 'waiting': waiting,
            'next': next_point_to_analyse(game) if waiting else None}


def sync_game_score(game):
    """Re-chain every point's before/after score in point order and set the
    game score from the result, so finishing or undoing an earlier point
    (e.g. analysing a Game Day game from footage) never rewinds the
    scoreboard, and correcting an earlier point's result carries through
    to the later points and the game."""
    points = _points(game).order_by(Point.point_number).all()
    if not points:
        return
    # Start from the first point's score: analysis may begin mid-game.
    ours, theirs = points[0].our_score_before or 0, points[0].their_score_before or 0
    for point in points:
        if point.point_outcome == 'scored':
            delta = (1, 0)
        elif point.point_outcome == 'conceded':
            delta = (0, 1)
        elif point.point_outcome is None:
            delta = (0, 0)  # in progress
        else:  # older outcome values: keep whatever the point recorded
            delta = ((point.our_score_after or 0) - (point.our_score_before or 0),
                     (point.their_score_after or 0) - (point.their_score_before or 0))
        point.our_score_before, point.their_score_before = ours, theirs
        ours, theirs = ours + delta[0], theirs + delta[1]
        point.our_score_after, point.their_score_after = ours, theirs
    game.our_score, game.their_score = ours, theirs
