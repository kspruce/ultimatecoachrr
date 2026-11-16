from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.event import Pull, Event
from app.forms.point import PointForm
from app.models.throws import Throw
from app.stats.point_replay import build_point_replay, outcome_label
from app.stats.throw_rebuild import rebuild_point_throws
from app.models.clip import Clip
from app.routes.clip.helpers import sees_hidden_clips
from app.utils.clip_video import youtube_embed_url
from app.models.stats import PlayerPointStats
from app.utils.utils import admin_required, stat_taker_required
from app.utils.team_filter import get_current_team_id
from app.utils.point_flow import (
    abba_ratio, determine_line_and_position, get_game_roster, line_type_for,
    analysis_progress, suggested_line, sync_game_score,
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

    progress = analysis_progress(game)
    return render_template('point/game_points.html', game=game, points=points,
                           next_to_analyse=progress['next'], progress=progress)


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
            point.force_direction = form.force_direction.data
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
            # Open/break follows the force, possession who started on O
            rebuild_point_throws(point)
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
    team_id = get_current_team_id()
    point = Point.query.filter_by(id=point_id, team_organization_id=team_id).first_or_404()
    game = Game.query.filter_by(id=point.game_id, team_organization_id=team_id).first_or_404()

    # In the order they were recorded: the replay follows the disc
    events = Event.query.filter_by(point_id=point_id, team_organization_id=team_id) \
        .order_by(Event.id).all()
    replay = build_point_replay(point, events)

    # Kit-number order, no number last
    lineups = sorted(
        (lu for lu in LineUp.query.filter_by(point_id=point_id, team_organization_id=team_id).all()
         if lu.player),
        key=lambda lu: (lu.player.jersey_number is None, lu.player.jersey_number or 0, lu.player.name or ''))

    # The whole game, for the score strip and previous / next
    game_points = Point.query.filter_by(game_id=game.id, team_organization_id=team_id) \
        .order_by(Point.point_number).all()
    position = next(i for i, p in enumerate(game_points) if p.id == point.id)
    prev_point = game_points[position - 1] if position > 0 else None
    next_point = game_points[position + 1] if position + 1 < len(game_points) else None

    pull = Pull.query.filter_by(point_id=point_id, team_organization_id=team_id) \
        .order_by(Pull.id).first()

    clips_query = Clip.query.filter_by(point_id=point_id, team_organization_id=team_id)
    if not sees_hidden_clips():
        clips_query = clips_query.filter(Clip.is_hidden == False)  # noqa: E712
    clips = clips_query.order_by(Clip.is_featured.desc(), Clip.created_at.desc()).all()
    # The game video from where this point starts, when no clip has been cut
    video_url = None
    if not any(c.embed_url for c in clips) and game.youtube_link and point.timestamp_in_video is not None:
        end = point.timestamp_in_video + point.duration if point.duration else None
        video_url = youtube_embed_url(game.youtube_link, point.timestamp_in_video or None, end)

    return render_template(
        'point/point_detail.html',
        point=point,
        game=game,
        replay=replay,
        events=events,
        lineups=lineups,
        game_points=game_points,
        prev_point=prev_point,
        next_point=next_point,
        pull=pull,
        clips=clips,
        video_url=video_url,
        outcome=outcome_label(point),
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

