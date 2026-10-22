from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.event import Pull, Event
from app.forms.point import PointForm
from app.models.throws import Throw
from app.stats.throwing import is_break_throw
from app.models.stats import PlayerPointStats
from app.utils.utils import admin_required, stat_taker_required
from app.utils.team_filter import get_current_team_id
from app.utils.point_flow import (
    abba_ratio, determine_line_and_position, get_game_roster, line_type_for,
    next_point_to_analyse, suggested_line, sync_game_score,
)

bp = Blueprint('point', __name__, url_prefix='/points')


# ---------------------------------------
# Helper function to get current team ID
# ---------------------------------------


# ---------------------------------------
# View Game Points
# ---------------------------------------
@bp.route('/game/<int:game_id>')
@login_required
def game_points(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    points = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).order_by(Point.point_number).all()

    return render_template('point/game_points.html', game=game, points=points,
                           next_to_analyse=next_point_to_analyse(game))


# ---------------------------------------
# Player Stats Helper
# ---------------------------------------
def get_player_stats(game_id):

    points = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).all()

    point_ids = [p.id for p in points]

    if not point_ids:
        return []

    player_stats = {}

    players = db.session.query(Player)\
        .join(LineUp)\
        .join(Point)\
        .filter(
            Point.game_id == game_id,
            Point.team_organization_id == get_current_team_id(),
            LineUp.team_organization_id == get_current_team_id(),
            Player.team_organization_id == get_current_team_id()
        )\
        .distinct().all()

    for player in players:

        events = Event.query\
            .filter(
                Event.point_id.in_(point_ids),
                Event.player_id == player.id,
                Event.team_organization_id == get_current_team_id()
            )\
            .order_by(Event.id)\
            .all()

        stats = {
            'completions': 0,
            'throwaways': 0,
            'drops': 0,
            'catches': 0,
            'goals': 0,
            'assists': 0,
            'blocks': 0,
            'hockey_assists': 0,
            'throws': 0
        }

        for event in events:
            if event.event_type == 'goal':
                stats['goals'] += 1
            elif event.event_type == 'assist':
                stats['assists'] += 1
                stats['completions'] += 1
                stats['throws'] += 1
            elif event.event_type == 'hockey_assist':
                stats['hockey_assists'] += 1
                stats['completions'] += 1
                stats['throws'] += 1
            elif event.event_type == 'block':
                stats['blocks'] += 1
            elif event.event_type == 'catch':
                stats['catches'] += 1
            elif event.event_type == 'throwaway':
                stats['throwaways'] += 1
                stats['throws'] += 1
            elif event.event_type == 'drop':
                stats['drops'] += 1
                stats['throws'] += 1

        for i in range(len(events) - 1):
            current_event = events[i]
            next_event = events[i + 1]

            if (current_event.event_type == 'regular' and
                current_event.field_position_x is not None and
                current_event.field_position_y is not None and
                next_event.field_position_x is not None and
                next_event.field_position_y is not None):

                stats['completions'] += 1
                stats['throws'] += 1

        plus_minus = (
            stats['goals'] +
            stats['assists'] +
            stats['blocks'] -
            stats['throwaways'] -
            stats['drops']
        )

        points_played = LineUp.query\
            .join(Point)\
            .filter(
                Point.game_id == game_id,
                LineUp.player_id == player.id,
                Point.team_organization_id == get_current_team_id(),
                LineUp.team_organization_id == get_current_team_id()
            ).count()

        completion_rate = 0
        if stats['throws'] > 0:
            completion_rate = round((stats['completions'] / stats['throws']) * 100, 1)

        player_stats[player.id] = {
            'player_id': player.id,
            'player_name': player.name,
            'jersey_number': player.jersey_number,
            'points_played': points_played,
            'plus_minus': plus_minus,
            'completion_rate': completion_rate,
            'completions': stats['completions'],
            'throws': stats['throws'],
            'throwaways': stats['throwaways'],
            'drops': stats['drops'],
            'goals': stats['goals'],
            'assists': stats['assists'],
            'blocks': stats['blocks'],
            'hockey_assists': stats['hockey_assists']
        }

    return sorted(
        player_stats.values(),
        key=lambda x: (x['points_played'], x['plus_minus']),
        reverse=True
    )


# ---------------------------------------
# Team Completion Rate
# ---------------------------------------
def calculate_completion_rate(game_id):

    points = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).all()

    point_ids = [p.id for p in points]

    if not point_ids:
        return 0

    events = Event.query\
        .filter(
            Event.point_id.in_(point_ids),
            Event.team_organization_id == get_current_team_id()
        )\
        .order_by(Event.id)\
        .all()

    completions = 0
    throwaways = 0

    for i in range(len(events) - 1):
        current_event = events[i]
        next_event = events[i + 1]

        if (current_event.field_position_x is not None and
            current_event.field_position_y is not None and
            next_event.field_position_x is not None and
            next_event.field_position_y is not None):
            completions += 1

        if current_event.event_type == 'throwaway':
            throwaways += 1

    if completions + throwaways == 0:
        return 0

    return round((completions / (completions + throwaways)) * 100, 1)


# ---------------------------------------
# Line Selection Helpers
# ---------------------------------------
def _posted_player_ids():
    raw = request.form.get('players', '')
    try:
        return [int(pid) for pid in raw.split(',') if pid]
    except ValueError:
        return []


def _check_line(player_ids, roster, division, gender_ratio):
    """Return (error, majority_gender) for a chosen line."""
    by_id = {p.id: p for p in roster}
    if len(player_ids) != 7 or len(set(player_ids)) != 7 or not set(player_ids) <= set(by_id):
        return 'You must select exactly 7 players from this game\'s roster.', None
    if division != 'mixed':
        return None, None

    genders = [by_id[pid].gender for pid in player_ids]
    male_count, female_count = genders.count('male'), genders.count('female')
    required_male, required_female = map(int, (gender_ratio or '4-3').split('-'))
    if male_count != required_male or female_count != required_female:
        return (f'Selected players do not match required gender ratio '
                f'({required_male}-{required_female}).'), None
    return None, 'male' if male_count > female_count else 'female'


def _halftime_now(game):
    """Halftime has been called at the current score."""
    return (
        game.halftime_our_score is not None
        and game.halftime_our_score == (game.our_score or 0)
        and game.halftime_their_score == (game.their_score or 0)
    )


# ---------------------------------------
# ADD POINT (Division Aware)
# ---------------------------------------
@bp.route('/add/<int:game_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_point(game_id):

    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    division = game.team_organization.division
    form = PointForm()
    all_players = get_game_roster(game)

    last_point = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).order_by(Point.point_number.desc()).first()

    position, line_reason = determine_line_and_position(game, last_point)
    roster_ids = {p.id for p in all_players}
    # Whoever played our last point on each side, to pre-select.
    suggestions = {
        side: dict(zip(('players', 'from_point'), suggested_line(game, side, roster_ids)))
        for side in ('offense', 'defense')
    }

    if request.method == 'GET':
        next_point_number = 1 if not last_point else last_point.point_number + 1
        form.point_number.data = next_point_number
        form.gender_ratio.data = abba_ratio(game, next_point_number) if division == 'mixed' else None
        if position:
            form.starting_position.data = position
        if last_point and last_point.force_direction:
            form.force_direction.data = last_point.force_direction
        form.players.data = suggestions[form.starting_position.data or 'offense']['players']
    else:
        form.players.data = _posted_player_ids()

    if form.validate_on_submit():
        gender_ratio = form.gender_ratio.data if division == 'mixed' else None
        error, majority = _check_line(form.players.data, all_players, division, gender_ratio)
        if error:
            flash(error, 'danger')
        else:
            # The outcome comes from the events (stat.finish_point), so a
            # new point starts open and doesn't move the score yet.
            our_score, their_score = game.our_score or 0, game.their_score or 0
            point = Point(
                game_id=game_id,
                point_number=form.point_number.data,
                our_line_type=line_type_for(form.starting_position.data),
                starting_position=form.starting_position.data,
                our_score_before=our_score,
                their_score_before=their_score,
                our_score_after=our_score,
                their_score_after=their_score,
                gender_ratio=gender_ratio,
                majority_gender=majority,
                force_direction=form.force_direction.data,
                point_outcome=None,
                duration=form.duration.data,
                timestamp_in_video=form.timestamp_in_video.data,
                team_organization_id=get_current_team_id()
            )
            db.session.add(point)
            db.session.flush()

            for player_id in form.players.data:
                db.session.add(LineUp(
                    point_id=point.id,
                    player_id=player_id,
                    team_organization_id=get_current_team_id()
                ))
            db.session.commit()

            return redirect(url_for('stat.record_events', point_id=point.id))

    return render_template(
        'point/point_form.html',
        form=form,
        game=game,
        division=division,
        all_players=all_players,
        line_reason=line_reason,
        suggestions=suggestions if request.method == 'GET' else None,
        halftime_now=_halftime_now(game),
        can_call_halftime=bool(last_point and last_point.point_outcome),
    )


# ---------------------------------------
# HALFTIME
# ---------------------------------------
@bp.route('/halftime/<int:game_id>', methods=['POST'])
@login_required
@admin_required
def toggle_halftime(game_id):
    """Call halftime at the current score, or take it back."""
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    if _halftime_now(game):
        game.halftime_our_score = game.halftime_their_score = None
        flash('Halftime removed.', 'info')
    else:
        game.halftime_our_score = game.our_score or 0
        game.halftime_their_score = game.their_score or 0
        flash(f'Halftime at {game.halftime_our_score}-{game.halftime_their_score}.', 'success')
    db.session.commit()
    return redirect(url_for('point.add_point', game_id=game_id))


@bp.route('/edit/<int:point_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_point(point_id):

    point = Point.query.filter_by(
        id=point_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    game = Game.query.filter_by(
        id=point.game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    division = game.team_organization.division
    form = PointForm(obj=point)
    current_line = [lineup.player_id for lineup in point.lineups]
    all_players = get_game_roster(game, include_ids=current_line)

    if request.method == 'GET':
        form.players.data = current_line
    else:
        form.players.data = _posted_player_ids() or current_line

    if form.validate_on_submit():
        gender_ratio = form.gender_ratio.data if division == 'mixed' else None
        error, majority = _check_line(form.players.data, all_players, division, gender_ratio)
        if error:
            flash(error, 'danger')
        else:
            point.point_number = form.point_number.data
            point.starting_position = form.starting_position.data
            point.our_line_type = line_type_for(form.starting_position.data)
            point.point_outcome = form.point_outcome.data or None
            point.duration = form.duration.data
            point.timestamp_in_video = form.timestamp_in_video.data
            if point.force_direction != form.force_direction.data:
                point.force_direction = form.force_direction.data
                # Open/break depends on the force, so re-mark this point's throws.
                for throw in point.throws:
                    throw.break_throw = is_break_throw(throw.x_start, throw.y_start, throw.x_end,
                                                       throw.y_end, point.force_direction)
            point.gender_ratio = gender_ratio
            point.majority_gender = majority

            our_before = point.our_score_before or 0
            their_before = point.their_score_before or 0
            point.our_score_after = our_before + (point.point_outcome == 'scored')
            point.their_score_after = their_before + (point.point_outcome == 'conceded')

            LineUp.query.filter_by(
                point_id=point.id,
                team_organization_id=get_current_team_id()
            ).delete()
            for player_id in form.players.data:
                db.session.add(LineUp(
                    point_id=point.id,
                    player_id=player_id,
                    team_organization_id=get_current_team_id()
                ))

            sync_game_score(game)
            db.session.commit()

            flash(f'Point {point.point_number} has been updated!', 'success')
            return redirect(url_for('point.game_points', game_id=point.game_id))

    return render_template(
        'point/point_form.html',
        form=form,
        game=game,
        point=point,
        division=division,
        all_players=all_players
    )


@bp.route('/delete/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def delete_point(point_id):

    point = Point.query.filter_by(
        id=point_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    game_id = point.game_id
    point_number = point.point_number

    try:
        event_ids = [event.id for event in Event.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).all()]

        if event_ids:
            Throw.query.filter(
                Throw.throwing_event_id.in_(event_ids),
                Throw.team_organization_id == get_current_team_id()
            ).delete(synchronize_session=False)

        PlayerPointStats.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).delete()

        LineUp.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).delete()

        Event.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).delete()

        Pull.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).delete()

        game = point.game
        db.session.delete(point)
        db.session.flush()
        sync_game_score(game)
        db.session.commit()

        flash(f'Point {point_number} has been deleted!', 'success')
        return redirect(url_for('point.game_points', game_id=game_id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting point: {str(e)}', 'danger')
        return redirect(url_for('point.game_points', game_id=game_id))

@bp.route('/<int:point_id>')
@login_required
def point_detail(point_id):

    point = Point.query.filter_by(
        id=point_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    game = Game.query.filter_by(
        id=point.game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    division = game.team_organization.division

    events = Event.query.filter_by(
        point_id=point_id,
        team_organization_id=get_current_team_id()
    ).order_by(Event.timestamp).all()

    reordered_events = []
    goal_events = []
    assist_events = []
    hockey_assist_events = []
    other_events = []

    for event in events:
        if event.event_type == 'goal':
            goal_events.append(event)
        elif event.event_type == 'assist':
            assist_events.append(event)
        elif event.event_type == 'hockey_assist':
            hockey_assist_events.append(event)
        else:
            other_events.append(event)

    reordered_events.extend(other_events)
    reordered_events.extend(hockey_assist_events)
    reordered_events.extend(assist_events)
    reordered_events.extend(goal_events)

    lineups = LineUp.query.filter_by(
        point_id=point_id,
        team_organization_id=get_current_team_id()
    ).all()

    events_data = []
    for event in reordered_events:
        events_data.append({
            'id': event.id,
            'event_type': event.event_type,
            'timestamp': event.timestamp,
            'field_position_x': event.field_position_x,
            'field_position_y': event.field_position_y,
            'player_id': event.player_id,
            'player_name': event.player.name if event.player else None,
            'receiver_id': event.receiver_id,
            'receiver_name': event.receiver.name if event.receiver else None,
            'is_offensive': event.is_offensive
        })

    return render_template(
        'point/point_detail.html',
        point=point,
        game=game,
        division=division,
        events=reordered_events,
        events_data=events_data,
        lineups=lineups
    )
    
@bp.route('/fix_lineups/<int:point_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def fix_lineups(point_id):

    point = Point.query.filter_by(
        id=point_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    game = Game.query.filter_by(
        id=point.game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    division = game.team_organization.division

    if request.method == 'POST':

        player_ids = request.form.getlist('players')

        if len(player_ids) != 7:
            flash(f'You must select exactly 7 players. You selected {len(player_ids)}.', 'danger')
            return redirect(url_for('point.fix_lineups', point_id=point_id))

        LineUp.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).delete()

        for player_id in player_ids:

            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=get_current_team_id()
            ).first()

            if player:
                lineup = LineUp(
                    point_id=point_id,
                    player_id=player_id,
                    team_organization_id=get_current_team_id()
                )
                db.session.add(lineup)

        db.session.commit()

        flash('Lineups have been updated!', 'success')
        return redirect(url_for('point.point_detail', point_id=point_id))

    all_players = get_game_roster(game, include_ids=[lu.player_id for lu in point.lineups])

    return render_template(
        'point/fix_lineups.html',
        point=point,
        game=game,
        division=division,
        all_players=all_players
    )

