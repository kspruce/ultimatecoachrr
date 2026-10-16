from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_
from app import db
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.game_player import GamePlayer
from app.models.event import Pull, Event
from app.forms.point import PointForm
from app.models.throws import Throw
from app.models.stats import PlayerPointStats
from app.utils.utils import admin_required
from app.utils.team_filter import get_current_team_id

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

    return render_template('point/game_points.html', game=game, points=points)


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
# Gender Ratio Pattern
# ---------------------------------------
def determine_gender_ratio(point_number):
    if point_number == 1:
        return '4-3'
    pattern_position = ((point_number - 1) % 4) + 1
    return '4-3' if pattern_position in [1, 2] else '3-4'


# ---------------------------------------
# Game Roster
# ---------------------------------------
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


# ---------------------------------------
# Line & Position Logic
# ---------------------------------------
def determine_line_and_position(game, previous_point):
    """Whether the next point starts on O or D, and why.

    After a goal the scoring team pulls, so we start on D after we score
    and on O after they score. The first point of the second half goes
    the other way from the first point of the game. Returns
    (line_type, starting_position, reason); line_type is None when there
    is nothing to go on and the form defaults should stand.
    """
    if not previous_point:
        return None, None, None

    def as_line(position):
        return ('O-line', 'offense') if position == 'offense' else ('D-line', 'defense')

    # First point after halftime: flip the side we started the game on.
    if game.halftime_our_score is not None and game.halftime_their_score is not None \
            and previous_point.point_outcome \
            and previous_point.our_score_after == game.halftime_our_score \
            and previous_point.their_score_after == game.halftime_their_score:
        first_point = Point.query.filter_by(
            game_id=game.id,
            team_organization_id=get_current_team_id()
        ).order_by(Point.point_number).first()
        if first_point and first_point.starting_position in ('offense', 'defense'):
            flipped = 'defense' if first_point.starting_position == 'offense' else 'offense'
            line, position = as_line(flipped)
            return line, position, (
                f'Second half: we started the game on '
                f'{"O" if first_point.starting_position == "offense" else "D"}, '
                f'so we start this half on {"O" if flipped == "offense" else "D"}.'
            )

    if previous_point.point_outcome == 'scored':
        return 'D-line', 'defense', f'We scored point {previous_point.point_number}, so we pull.'
    if previous_point.point_outcome == 'conceded':
        return 'O-line', 'offense', f'They scored point {previous_point.point_number}, so we receive.'

    # Previous point not finished yet: carry its line over rather than guess.
    line, position = as_line(previous_point.starting_position)
    return line, position, (
        f'Point {previous_point.point_number} has no result yet, so this '
        f'follows its line. Finish it to set O/D automatically.'
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

    team = game.team_organization
    division = team.division

    form = PointForm()

    all_players = get_game_roster(game)
    line_reason = None

    last_point = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).order_by(Point.point_number.desc()).first()

    # ------------------------
    # GET Defaults
    # ------------------------
    if request.method == 'GET':

        next_point_number = 1 if not last_point else last_point.point_number + 1

        form.point_number.data = next_point_number
        form.our_score_before.data = game.our_score
        form.their_score_before.data = game.their_score

        if division == "mixed":
            form.gender_ratio.data = determine_gender_ratio(next_point_number)
        else:
            form.gender_ratio.data = None

        line_type, position, line_reason = determine_line_and_position(game, last_point)
        if line_type:
            form.our_line_type.data = line_type
            form.starting_position.data = position

    # ------------------------
    # Process Players on POST
    # ------------------------
    if request.method == 'POST':

        selected_players_str = request.form.get('players', '')

        if selected_players_str:
            try:
                form.players.data = [
                    int(pid) for pid in selected_players_str.split(',') if pid
                ]
            except ValueError:
                form.players.data = []
        else:
            form.players.data = []

    # ------------------------
    # FORM VALIDATION
    # ------------------------
    if form.validate_on_submit():

        roster_ids = {p.id for p in all_players}
        if len(form.players.data) != 7 or not set(form.players.data) <= roster_ids:
            flash('You must select exactly 7 players from this game\'s roster.', 'danger')
            return render_template(
                'point/point_form.html',
                form=form,
                game=game,
                division=division,
                all_players=all_players
            )

        # ------------------------
        # Mixed Ratio Enforcement
        # ------------------------
        majority = None

        if division == "mixed":

            male_count = 0
            female_count = 0

            for player_id in form.players.data:
                player = Player.query.filter_by(
                    id=player_id,
                    team_organization_id=get_current_team_id()
                ).first()

                if player:
                    if player.gender == "male":
                        male_count += 1
                    elif player.gender == "female":
                        female_count += 1

            required_male, required_female = map(
                int,
                form.gender_ratio.data.split('-')
            )

            if male_count != required_male or female_count != required_female:
                flash(
                    f'Selected players do not match required gender ratio '
                    f'({required_male}-{required_female}).',
                    'danger'
                )
                return render_template(
                    'point/point_form.html',
                    form=form,
                    game=game,
                    division=division,
                    all_players=all_players
                )

            # Calculate Majority
            majority = "male" if male_count > female_count else "female"

        # ------------------------
        # Create Point
        # ------------------------
        point = Point(
            game_id=game_id,
            point_number=form.point_number.data,
            our_line_type=form.our_line_type.data,
            our_score_before=form.our_score_before.data,
            their_score_before=form.their_score_before.data,
            starting_position=form.starting_position.data,
            gender_ratio=form.gender_ratio.data if division == "mixed" else None,
            majority_gender=majority,
            force_direction=form.force_direction.data,
            point_outcome=form.point_outcome.data or None,
            duration=form.duration.data,
            timestamp_in_video=form.timestamp_in_video.data,
            team_organization_id=get_current_team_id()
        )

        # Use current game score as source of truth
        current_our_score = game.our_score or 0
        current_their_score = game.their_score or 0

        point.our_score_before = current_our_score
        point.their_score_before = current_their_score

        # A point left as "determined from events" doesn't move the score
        # until it's finished (stat.finish_point sets it from the last event).
        point.our_score_after = current_our_score + (form.point_outcome.data == 'scored')
        point.their_score_after = current_their_score + (form.point_outcome.data == 'conceded')

        db.session.add(point)
        db.session.commit()

        for player_id in form.players.data:
            lineup = LineUp(
                point_id=point.id,
                player_id=player_id,
                team_organization_id=get_current_team_id()
            )
            db.session.add(lineup)

        game.our_score = point.our_score_after
        game.their_score = point.their_score_after

        db.session.commit()

        flash(f'Point {point.point_number} has been added!', 'success')
        return redirect(url_for('stat.record_events', point_id=point.id))

    return render_template(
        'point/point_form.html',
        form=form,
        game=game,
        division=division,
        all_players=all_players,
        line_reason=line_reason
    )

                           
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

    team = game.team_organization
    division = team.division

    form = PointForm(obj=point)

    all_players = get_game_roster(game, include_ids=[lu.player_id for lu in point.lineups])

    # ------------------------
    # Preselect Players (GET)
    # ------------------------
    if request.method == 'GET':
        form.players.data = [lineup.player_id for lineup in point.lineups]

    # ------------------------
    # Handle POST Selection
    # ------------------------
    if request.method == 'POST':

        selected_players_str = request.form.get('players', '')

        if selected_players_str:
            try:
                form.players.data = [
                    int(pid) for pid in selected_players_str.split(',') if pid
                ]
            except ValueError:
                form.players.data = []
        else:
            form.players.data = [lineup.player_id for lineup in point.lineups]

    # ------------------------
    # VALIDATION
    # ------------------------
    if form.validate_on_submit():

        roster_ids = {p.id for p in all_players}
        if len(form.players.data) != 7 or not set(form.players.data) <= roster_ids:
            flash('You must select exactly 7 players from this game\'s roster.', 'danger')
            return render_template(
                'point/point_form.html',
                form=form,
                game=game,
                point=point,
                division=division,
                all_players=all_players
            )

        majority = None

        if division == "mixed":

            male_count = 0
            female_count = 0

            for player_id in form.players.data:
                player = Player.query.filter_by(
                    id=player_id,
                    team_organization_id=get_current_team_id()
                ).first()

                if player:
                    if player.gender == "male":
                        male_count += 1
                    elif player.gender == "female":
                        female_count += 1

            required_male, required_female = map(
                int,
                form.gender_ratio.data.split('-')
            )

            if male_count != required_male or female_count != required_female:
                flash(
                    f'Selected players do not match required gender ratio '
                    f'({required_male}-{required_female}).',
                    'danger'
                )
                return render_template(
                    'point/point_form.html',
                    form=form,
                    game=game,
                    point=point,
                    division=division,
                    all_players=all_players
                )

            majority = "male" if male_count > female_count else "female"
            point.majority_gender = majority
        else:
            point.majority_gender = None
            point.gender_ratio = None

        point.point_number = form.point_number.data
        point.our_line_type = form.our_line_type.data
        point.starting_position = form.starting_position.data
        point.point_outcome = form.point_outcome.data or None
        point.duration = form.duration.data
        point.timestamp_in_video = form.timestamp_in_video.data
        point.force_direction = form.force_direction.data

        if division == "mixed":
            point.gender_ratio = form.gender_ratio.data

        our_before = form.our_score_before.data or 0
        their_before = form.their_score_before.data or 0
        point.our_score_after = our_before + (form.point_outcome.data == 'scored')
        point.their_score_after = their_before + (form.point_outcome.data == 'conceded')

        LineUp.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).delete()

        for player_id in form.players.data:
            lineup = LineUp(
                point_id=point.id,
                player_id=player_id,
                team_organization_id=get_current_team_id()
            )
            db.session.add(lineup)

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

        db.session.delete(point)
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

