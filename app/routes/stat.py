from flask import Blueprint, jsonify, request, render_template, url_for, current_app, flash, redirect
from flask_login import current_user, login_required
from app import db
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.game import Game
from app.models.player import Player
from app.models.throws import Throw
from app.utils.utils import admin_required, stat_taker_required
from app.utils.point_flow import get_game_roster, next_point_to_analyse, sync_game_score
from app.stats.throwing import is_break_throw
import math

from werkzeug.exceptions import HTTPException

bp = Blueprint('stat', __name__, url_prefix='/stats')


@bp.route('/record/<int:point_id>', methods=['GET', 'POST'])
@login_required
@stat_taker_required
def record_events(point_id):
    if request.method == 'GET':
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        # Anything already recorded, so reopening a point picks up where it left off.
        from app.models.cutting_skill import CuttingSkill
        events = Event.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).order_by(Event.id).all()
        skills = CuttingSkill.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).order_by(CuttingSkill.id).all()
        existing = {
            'events': [{
                'id': e.id, 'event_type': e.event_type, 'player_id': e.player_id,
                'player_name': e.player.name if getattr(e, 'player', None) else None,
                'field_position_x': e.field_position_x, 'field_position_y': e.field_position_y,
                'is_offensive': e.is_offensive,
            } for e in events],
            'cutting_skills': [{
                'id': c.id, 'cutting_type': c.cutting_type, 'outcome': c.outcome,
                'player_id': c.player_id,
                'player_name': c.player.name if getattr(c, 'player', None) else None,
                'field_position_x': c.field_position_x, 'field_position_y': c.field_position_y,
            } for c in skills],
        }
        # Players in kit-number order (no number last), not the order picked
        line = sorted((lu.player for lu in point.lineups if lu.player),
                      key=lambda p: (p.jersey_number is None, p.jersey_number or 0, p.name or ''))
        return render_template('stats/record.html', point=point, line=line, existing=existing)

    if request.method == 'POST':
        try:
            data = request.get_json()
            point = Point.query.filter_by(
                id=point_id,
                team_organization_id=get_current_team_id()
            ).first_or_404()
            
            # Opponent / Unknown plays have no player of ours. Ignore any
            # player_id sent with them (older clients sent a placeholder),
            # so nobody is credited with the play.
            is_unknown_player = bool(data.get('is_unknown_player', False))
            is_opponent = bool(data.get('is_opponent', False))
            if is_unknown_player or is_opponent:
                player_id = None
            elif data.get('player_id') in (None, ''):
                return jsonify({'error': 'player_id is required'}), 400
            else:
                player_id = int(data['player_id'])
                if not Player.query.filter_by(id=player_id,
                                              team_organization_id=get_current_team_id()).first():
                    return jsonify({'error': 'Player not found'}), 404

            # Create new event
            event = Event(
                point_id=point_id,
                player_id=player_id,
                event_type=data['event_type'],
                field_position_x=float(data.get('field_position_x', 0)),
                field_position_y=float(data.get('field_position_y', 0)),
                is_offensive=bool(data.get('is_offensive', True)),
                is_unknown_player=is_unknown_player,
                is_opponent=is_opponent,
                team_organization_id=get_current_team_id()  # Add team ID
            )
            
            # Add and flush the event to get its ID
            db.session.add(event)
            db.session.flush()

            # Get previous event in this point
            previous_event = Event.query.filter(
                Event.point_id == point_id,
                Event.id < event.id,
                Event.team_organization_id == get_current_team_id()
            ).order_by(Event.id.desc()).first()

            # Handle goal events and create associated throws
            if event.event_type == 'goal':
                # Get previous events for assist and hockey assist
                previous_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.id < event.id,
                    Event.team_organization_id == get_current_team_id()
                ).order_by(Event.id.desc()).limit(2).all()

                # Only promote events that are valid precursors to a goal
                # (catch or pickup). Blocks, drops, throwaways etc. should
                # never be silently retyped as assists.
                # Opponent plays are never part of our passing chain.
                ASSISTABLE = ('catch', 'pickup')

                def assistable(e):
                    return e.event_type in ASSISTABLE and not e.is_opponent

                if previous_events and assistable(previous_events[0]):
                    # Mark first previous event as assist
                    assist_event = previous_events[0]
                    assist_event.event_type = 'assist'

                    # Create throw for the assist
                    assist_throw = Throw(
                        point_id=point_id,
                        thrower_id=assist_event.player_id,
                        receiver_id=event.player_id,
                        throwing_event_id=assist_event.id,
                        receiving_event_id=event.id,
                        x_start=assist_event.field_position_x,
                        y_start=assist_event.field_position_y,
                        x_end=event.field_position_x,
                        y_end=event.field_position_y,
                        throw_type='assist',
                        is_completion=True,
                        break_throw=is_break_throw(
                            assist_event.field_position_x,
                            assist_event.field_position_y,
                            event.field_position_x,
                            event.field_position_y,
                            point.force_direction
                        ),
                        team_organization_id=get_current_team_id()
                    )
                    db.session.add(assist_throw)

                    # If there's a second previous event of a valid type,
                    # mark it as hockey assist
                    if len(previous_events) >= 2 and assistable(previous_events[1]):
                        hockey_assist_event = previous_events[1]
                        hockey_assist_event.event_type = 'hockey_assist'
                        
                        # Create throw for the hockey assist
                        hockey_throw = Throw(
                            point_id=point_id,
                            thrower_id=hockey_assist_event.player_id,
                            receiver_id=assist_event.player_id,
                            throwing_event_id=hockey_assist_event.id,
                            receiving_event_id=assist_event.id,
                            x_start=hockey_assist_event.field_position_x,
                            y_start=hockey_assist_event.field_position_y,
                            x_end=assist_event.field_position_x,
                            y_end=assist_event.field_position_y,
                            throw_type='hockey_assist',
                            is_completion=True,
                            break_throw=is_break_throw(
                                hockey_assist_event.field_position_x,
                                hockey_assist_event.field_position_y,
                                assist_event.field_position_x,
                                assist_event.field_position_y,
                                point.force_direction
                            ),
                            team_organization_id=get_current_team_id()  # Add team ID
                        )
                        db.session.add(hockey_throw)
                        # Remove any regular throws that are now hockey assists
                        regular_throw = Throw.query.filter(
                            Throw.point_id == point_id,
                            Throw.throwing_event_id == hockey_assist_event.id,
                            Throw.receiving_event_id == assist_event.id,
                            Throw.throw_type == 'regular',
                            Throw.team_organization_id == get_current_team_id()  # Add team ID
                        ).first()
                        
                        if regular_throw:
                            current_app.logger.debug(f"Removing regular throw {regular_throw.id} that is now a hockey assist")
                            db.session.delete(regular_throw)

                        
                        
            # Create regular throw if this is a catch. The thrower is NULL
            # after an Opponent/Unknown play; the throw still counts for the
            # team and the catch for the receiver.
            elif event.event_type == 'catch' and previous_event:
                regular_throw = Throw(
                    point_id=point_id,
                    thrower_id=previous_event.player_id,
                    receiver_id=event.player_id,
                    throwing_event_id=previous_event.id,
                    receiving_event_id=event.id,
                    x_start=previous_event.field_position_x,
                    y_start=previous_event.field_position_y,
                    x_end=event.field_position_x,
                    y_end=event.field_position_y,
                    throw_type='regular',
                    is_completion=True,
                    break_throw=is_break_throw(
                        previous_event.field_position_x,
                        previous_event.field_position_y,
                        event.field_position_x,
                        event.field_position_y,
                        point.force_direction
                    ),
                    team_organization_id=get_current_team_id()  # Add team ID
                )
                db.session.add(regular_throw)

            # Handle throwaway events
            elif event.event_type == 'throwaway' and previous_event:
                throwaway = Throw(
                    point_id=point_id,
                    thrower_id=event.player_id,
                    receiver_id=None,
                    throwing_event_id=event.id,       # the throwaway IS the throw
                    receiving_event_id=None,           # no receiver on a throwaway
                    x_start=previous_event.field_position_x,
                    y_start=previous_event.field_position_y,
                    x_end=event.field_position_x,
                    y_end=event.field_position_y,
                    throw_type='throwaway',
                    is_completion=False,
                    break_throw=is_break_throw(
                        previous_event.field_position_x,
                        previous_event.field_position_y,
                        event.field_position_x,
                        event.field_position_y,
                        point.force_direction
                    ),
                    team_organization_id=get_current_team_id()
                )
                db.session.add(throwaway)

            # Update point status for point-ending events and keep the
            # game-level score in sync so the scoreboard stays correct
            # even when the point outcome is determined via event recording.
            if event.event_type in ['goal', 'callahan']:
                point.point_outcome = 'scored'
                point.our_score_after = point.our_score_before + 1
                point.their_score_after = point.their_score_before
                sync_game_score(point.game)
            elif event.event_type == 'scored_on':
                point.point_outcome = 'conceded'
                point.their_score_after = point.their_score_before + 1
                point.our_score_after = point.our_score_before
                sync_game_score(point.game)

            # Calculate distances for throws
            for throw in db.session.new:
                if isinstance(throw, Throw):
                    throw.distance = throw.calculate_distance()  # Use the model's method

            db.session.commit()
            return jsonify(event.to_dict()), 201

        except Exception as e:
            current_app.logger.error("Error recording event: %s", str(e))
            db.session.rollback()
            return jsonify({'error': str(e)}), 400




@bp.route('/undo_event/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def undo_event(point_id):
    try:
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        last_event = Event.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).order_by(Event.id.desc()).first()

        if last_event:
            # If undoing a goal, restore the two events before it that were
            # silently retyped to 'assist' / 'hockey_assist' when the goal
            # was recorded — put them back to 'catch' so their stats remain
            # correct and a re-recorded goal will promote them cleanly.
            if last_event.event_type == 'goal':
                prior_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.id < last_event.id,
                    Event.team_organization_id == get_current_team_id()
                ).order_by(Event.id.desc()).limit(2).all()

                if prior_events:
                    if prior_events[0].event_type == 'assist':
                        prior_events[0].event_type = 'catch'
                    if len(prior_events) >= 2 and prior_events[1].event_type == 'hockey_assist':
                        prior_events[1].event_type = 'catch'
                        # The goal replaced that pass's regular throw with a
                        # hockey-assist throw; make it a regular throw again,
                        # or re-recording the goal would count the pass twice.
                        Throw.query.filter_by(
                            receiving_event_id=prior_events[0].id,
                            throw_type='hockey_assist',
                            team_organization_id=get_current_team_id()
                        ).update({'throw_type': 'regular'})

            # First, delete any throws associated with this event
            # Delete throws where this event is the receiving event
            throws_received = Throw.query.filter_by(
                receiving_event_id=last_event.id,
                team_organization_id=get_current_team_id()
            ).all()
            for throw in throws_received:
                db.session.delete(throw)

            # Delete throws where this event is the throwing event
            throws_thrown = Throw.query.filter_by(
                throwing_event_id=last_event.id,
                team_organization_id=get_current_team_id()
            ).all()
            for throw in throws_thrown:
                db.session.delete(throw)

            # Now delete the event itself
            db.session.delete(last_event)

            # Update point outcome and keep game score in sync
            if last_event.event_type in ('goal', 'callahan'):
                point.point_outcome = None
                point.our_score_after = point.our_score_before
                sync_game_score(point.game)
            elif last_event.event_type == 'scored_on':
                point.point_outcome = None
                point.their_score_after = point.their_score_before
                sync_game_score(point.game)
            
            # Don't try to update point.is_offensive as it doesn't exist
            # The client-side code will handle possession state

            db.session.add(point)
            db.session.commit()
            return jsonify({'message': 'Event undone'}), 200
        else:
            return jsonify({'error': 'No events to undo'}), 400

    except Exception as e:
        import traceback
        current_app.logger.error("Error in undo_event: %s", str(e))
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/undo_cutting_skill/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def undo_cutting_skill(point_id):
    try:
        data = request.get_json()
        cutting_skill_id = data.get('cutting_skill_id')
        
        if not cutting_skill_id:
            return jsonify({'error': 'No cutting skill ID provided'}), 400
        
        from app.models.cutting_skill import CuttingSkill
        cutting_skill = CuttingSkill.query.filter_by(
            id=cutting_skill_id,
            team_organization_id=get_current_team_id()  # Add team ID
        ).first_or_404()
        
        if cutting_skill.point_id != point_id:
            return jsonify({'error': 'Cutting skill does not belong to this point'}), 400
        
        db.session.delete(cutting_skill)
        db.session.commit()
        
        return jsonify({'message': 'Cutting skill undone'}), 200
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        current_app.logger.error("Error in undo_cutting_skill: %s", e)
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/finish_point/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def finish_point(point_id):
    try:
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        game = Game.query.filter_by(
            id=point.game_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()

        # Always check the last event to determine point outcome
        last_event = Event.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).order_by(Event.id.desc()).first()
        
        if last_event:
            if last_event.event_type in ['goal', 'callahan']:
                # We scored
                point.point_outcome = 'scored'
                point.our_score_after = point.our_score_before + 1
                point.their_score_after = point.their_score_before  # Keep opponent score the same
            elif last_event.event_type == 'scored_on':
                # They scored
                point.point_outcome = 'conceded'
                point.our_score_after = point.our_score_before  # Keep our score the same
                point.their_score_after = point.their_score_before + 1
            else:
                # If last event doesn't determine outcome, check if we already have an outcome
                if point.point_outcome is None:
                    # No outcome determined yet, provide a warning
                    return jsonify({
                        'error': 'Cannot determine point outcome from events. Please record a goal or scored_on event.'
                    }), 400
        else:
            # No events recorded
            return jsonify({
                'error': 'No events recorded for this point. Please record at least one event.'
            }), 400

        # Update game score
        sync_game_score(game)

        # Remove duplicate throws (regular throws that were later marked as hockey assists)
        from app.models.throws import Throw
        
        # Get all hockey assist throws in this point
        hockey_assists = Throw.query.filter_by(
            point_id=point_id,
            throw_type='hockey_assist',
            team_organization_id=get_current_team_id()  # Add team ID
        ).all()
        
        # For each hockey assist, find and remove any regular throws with the same coordinates
        for hockey in hockey_assists:
            duplicate_throws = Throw.query.filter(
                Throw.point_id == point_id,
                Throw.throw_type == 'regular',
                Throw.thrower_id == hockey.thrower_id,
                Throw.receiver_id == hockey.receiver_id,
                Throw.x_start == hockey.x_start,
                Throw.y_start == hockey.y_start,
                Throw.x_end == hockey.x_end,
                Throw.y_end == hockey.y_end,
                Throw.id != hockey.id,  # Make sure we don't delete the hockey assist itself
                Throw.team_organization_id == get_current_team_id()  # Add team ID
            ).all()
            
            for duplicate in duplicate_throws:
                current_app.logger.debug(f"Removing duplicate throw: {duplicate.id} (regular) in favor of hockey assist: {hockey.id}")
                db.session.delete(duplicate)

        throws_without_distance = Throw.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()  # Add team ID
        ).filter(
            (Throw.distance.is_(None)) | (Throw.distance == 0)
        ).all()
        
        for throw in throws_without_distance:
            if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
                throw.distance = math.sqrt(
                    (throw.x_end - throw.x_start) ** 2 +
                    (throw.y_end - throw.y_start) ** 2
                )
                current_app.logger.debug(f"Calculated missing distance for throw {throw.id}: {throw.distance:.2f}m")

        db.session.commit()

        # Auto-advance: the next point not analysed yet (e.g. taken live on
        # Game Day), otherwise set up a new one.
        next_point = next_point_to_analyse(game, after_number=point.point_number)
        if next_point:
            next_point_url = url_for('stat.record_events', point_id=next_point.id)
        elif current_user.is_admin:
            next_point_url = url_for('point.add_point', game_id=game.id)
        else:
            next_point_url = None  # setting up points is admin-only

        # Return both redirect and redirect_url for compatibility
        return jsonify({
            'message': f'Point finished. Outcome: {point.point_outcome}',
            'redirect': url_for('point.game_points', game_id=game.id),
            'redirect_url': url_for('point.game_points', game_id=game.id),
            'game_id': game.id,
            'point_outcome': point.point_outcome,
            'next_point_url': next_point_url,   # Auto-advance to next unfinished point
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    



def calculate_assists(point, goal_event):
    # Get events for the point, ordered by timestamp if available, otherwise by ID
    events = sorted(
        Event.query.filter_by(
            point_id=point.id,
            team_organization_id=get_current_team_id()
        ).all(),
        key=lambda e: (e.timestamp or 0, e.id)
    )

    # Find the throw leading to the goal
    for i in range(len(events) - 2, -1, -1):  # Iterate backward from the goal
        event = events[i]
        if event.event_type == 'throw' and event.receiver_id == goal_event.player_id:
            event.event_type = 'assist'
            db.session.add(event)

            # Find the hockey assist
            for j in range(i - 1, -1, -1):
                hockey_event = events[j]
                if hockey_event.event_type == 'throw' and hockey_event.receiver_id == event.player_id:
                    hockey_event.event_type = 'hockey_assist'
                    db.session.add(hockey_event)
                    break  # Only one hockey assist per goal
            break


def create_throw_from_events(previous_event, current_event):
    """Create a throw record from two consecutive events"""
    if not (previous_event and current_event):
        return None
        
    # Validate event types
    valid_sequences = [
        ('catch', 'catch'),
        ('catch', 'goal'),
        ('catch', 'hockey_assist'),
        ('hockey_assist', 'assist'),
        ('assist', 'goal')
    ]
    
    if (previous_event.event_type, current_event.event_type) not in valid_sequences:
        return None
    
    throw = Throw(
        point_id=current_event.point_id,
        thrower_id=previous_event.player_id,
        receiver_id=current_event.player_id,
        throwing_event_id=previous_event.id,
        receiving_event_id=current_event.id,
        x_start=previous_event.field_position_x,
        y_start=previous_event.field_position_y,
        x_end=current_event.field_position_x,
        y_end=current_event.field_position_y,
        break_throw=is_break_throw(
            previous_event.field_position_x,
            previous_event.field_position_y,
            current_event.field_position_x,
            current_event.field_position_y,
            current_event.point.force_direction if current_event.point else None
        ),
        team_organization_id=get_current_team_id()  # Add team ID
    )
    
    # Calculate distance
    throw.distance = math.sqrt(
        (throw.x_end - throw.x_start) ** 2 +
        (throw.y_end - throw.y_start) ** 2
    )
    
    # Determine throw type
    if current_event.event_type == 'goal':
        throw.throw_type = 'assist'
    elif current_event.event_type == 'hockey_assist':
        throw.throw_type = 'hockey_assist'
    else:
        throw.throw_type = 'regular'
    
    return throw

@bp.route('/admin/mark_break_throws', methods=['POST'])
@login_required
@admin_required
def mark_break_throws():
    """Re-mark open/break on this team's throws from each point's force."""
    throws = Throw.query.filter(
        Throw.team_organization_id == get_current_team_id()
    ).all()
    breaks = unknown = 0
    for throw in throws:
        force = throw.point.force_direction if throw.point else None
        throw.break_throw = is_break_throw(throw.x_start, throw.y_start,
                                           throw.x_end, throw.y_end, force)
        breaks += throw.break_throw is True
        unknown += throw.break_throw is None
    db.session.commit()
    flash(f'Checked {len(throws)} throws: {breaks} break throws, '
          f'{unknown} without a known force.', 'success')
    return redirect(url_for('data_management.data_management'))


@bp.route('/admin/recalculate_throw_distances', methods=['POST'])
@login_required
@admin_required
def recalculate_throw_distances():
    """Recalculate the distance of every one of this team's throws."""
    throws = Throw.query.filter_by(team_organization_id=get_current_team_id()).all()
    updated = 0
    for throw in throws:
        if None not in (throw.x_start, throw.y_start, throw.x_end, throw.y_end):
            distance = math.hypot(throw.x_end - throw.x_start, throw.y_end - throw.y_start)
            if throw.distance != distance:
                throw.distance = distance
                updated += 1
    db.session.commit()
    flash(f'Recalculated distances: {updated} of {len(throws)} throws changed.', 'success')
    return redirect(url_for('data_management.data_management'))



@bp.route('/available_players/<int:point_id>', methods=['GET'])
@login_required
@stat_taker_required
def available_players(point_id):
    try:
        current_app.logger.debug(f"Fetching available players for point {point_id}")
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        current_app.logger.debug(f"Found point: {point}")
        game = Game.query.filter_by(
            id=point.game_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        current_app.logger.debug(f"Found game: {game}")
        
        # Get players already in the point
        current_player_ids = [lineup.player_id for lineup in point.lineups]
        current_app.logger.debug(f"Current player IDs in lineup: {current_player_ids}")
        
        # Players on the game's roster who aren't on the line
        available_players = get_game_roster(game)
        
        # Filter out players already in the lineup
        available_players = [p for p in available_players if p.id not in current_player_ids]
        
        current_app.logger.debug(f"Found {len(available_players)} available players")
        
        result = {
            'available_players': [
                {
                    'id': player.id,
                    'name': player.name,
                    'jersey_number': player.jersey_number or 'N/A'
                }
                for player in available_players
            ]
        }

        current_app.logger.debug(f"Returning result: {result}")
        return jsonify(result)
    except Exception as e:
        import traceback
        current_app.logger.error("Error in available_players:", str(e))
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'available_players': []}), 500



@bp.route('/substitute_player/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def substitute_player(point_id):
    try:
        data = request.get_json()
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        player_out_id = int(data['player_out_id'])
        player_in_id = int(data['player_in_id'])
        
        # Get the players
        from app.models.player import Player
        player_out = Player.query.filter_by(
            id=player_out_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        player_in = Player.query.filter_by(
            id=player_in_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Check if player_out is in the lineup
        lineup_out = LineUp.query.filter_by(
            point_id=point_id,
            player_id=player_out_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if not lineup_out:
            return jsonify({'success': False, 'error': 'Player not found in lineup'}), 400
        
        # Instead of removing player_out, we'll keep them in the lineup
        # but mark them as substituted out (if you have such a field)
        # If you don't have a field to track substitution status, you can add one
        
        # Add the player_in to the lineup
        lineup_in = LineUp(
            point_id=point_id,
            player_id=player_in_id,
            team_organization_id=get_current_team_id()  # Add team ID
        )
        db.session.add(lineup_in)
        
        # Record the substitution as an event
        sub_event = Event(
            point_id=point_id,
            player_id=player_in_id,
            event_type='substitution',
            field_position_x=50,  # Center of field
            field_position_y=18.5,
            is_offensive=point.starting_position == 'offense',
            team_organization_id=get_current_team_id()  # Add team ID
        )
        db.session.add(sub_event)
        
        # Add a reference to the player being substituted out
        sub_event.receiver_id = player_out_id  # Using receiver_id to store the player being subbed out
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'player_out': {
                'id': player_out.id,
                'name': player_out.name,
                'jersey_number': player_out.jersey_number or 'N/A'
            },
            'player_in': {
                'id': player_in.id,
                'name': player_in.name,
                'jersey_number': player_in.jersey_number or 'N/A'
            }
        })
    except Exception as e:
        import traceback
        current_app.logger.error("Error in substitute_player:", str(e))
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/record_cutting_skill/<int:point_id>', methods=['POST'])
@login_required
@stat_taker_required
def record_cutting_skill(point_id):
    try:
        data = request.get_json()
        point = Point.query.filter_by(
            id=point_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Extract data from request
        player_id = int(data.get('player_id'))
        cutting_type = data.get('cutting_type')
        outcome = data.get('outcome')
        # One-tap "open, not thrown to" records have no position
        field_position_x = data.get('field_position_x')
        field_position_y = data.get('field_position_y')
        field_position_x = float(field_position_x) if field_position_x is not None else None
        field_position_y = float(field_position_y) if field_position_y is not None else None
        
        # Validate player belongs to the team
        from app.models.player import Player
        player = Player.query.filter_by(
            id=player_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Create cutting skill record
        from app.models.cutting_skill import CuttingSkill
        cutting_skill = CuttingSkill(
            point_id=point_id,
            player_id=player_id,
            cutting_type=cutting_type,
            outcome=outcome,
            field_position_x=field_position_x,
            field_position_y=field_position_y,
            team_organization_id=get_current_team_id()  # Add team ID
        )
        
        db.session.add(cutting_skill)
        db.session.commit()
        
        return jsonify({
            **cutting_skill.to_dict(),
            'player_name': player.name,
            'success': True,
            'cutting_skill_id': cutting_skill.id,
            'message': f'Cutting skill recorded for {player.name}'
        }), 201
        
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError) as e:  # a bad type, outcome or number
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        current_app.logger.error("Error in record_cutting_skill: %s", e)
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/get_cutting_skills/<int:point_id>', methods=['GET'])
@login_required
@stat_taker_required
def get_cutting_skills(point_id):
    try:
        from app.models.cutting_skill import CuttingSkill
        from app.models.player import Player
        
        # Get all cutting skills for this point
        cutting_skills = CuttingSkill.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).all()
        
        # Format the data for the frontend
        result = []
        for skill in cutting_skills:
            player = Player.query.filter_by(
                id=skill.player_id,
                team_organization_id=get_current_team_id()
            ).first()
            
            if player:
                result.append({
                    'id': skill.id,
                    'player_id': skill.player_id,
                    'player_name': player.name,
                    'jersey_number': player.jersey_number or 'N/A',
                    'cutting_type': skill.cutting_type,
                    'outcome': skill.outcome,
                    'field_position_x': skill.field_position_x,
                    'field_position_y': skill.field_position_y,
                    'timestamp': skill.created_at.isoformat() if skill.created_at else None
                })
        
        return jsonify({
            'success': True,
            'cutting_skills': result
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error("Error in get_cutting_skills:", str(e))
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/get_events/<int:point_id>', methods=['GET'])
@login_required
@stat_taker_required
def get_events(point_id):
    try:
        # Get all events for this point
        events = Event.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).order_by(Event.timestamp).all()
        
        # Format the data for the frontend
        result = []
        for event in events:
            # Get player name if available
            player_name = "Unknown"
            jersey_number = "N/A"
            
            if event.player_id:
                from app.models.player import Player
                player = Player.query.filter_by(
                    id=event.player_id,
                    team_organization_id=get_current_team_id()
                ).first()
                
                if player:
                    player_name = player.name
                    jersey_number = player.jersey_number or "N/A"
            
            result.append({
                'id': event.id,
                'event_type': event.event_type,
                'player_id': event.player_id,
                'player_name': player_name,
                'jersey_number': jersey_number,
                'field_position_x': event.field_position_x,
                'field_position_y': event.field_position_y,
                'is_offensive': event.is_offensive,
                'timestamp': event.timestamp.isoformat() if event.timestamp else None
            })
        
        return jsonify({
            'success': True,
            'events': result
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error("Error in get_events:", str(e))
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/get_throws/<int:point_id>', methods=['GET'])
@login_required
@stat_taker_required
def get_throws(point_id):
    try:
        # Get all throws for this point
        throws = Throw.query.filter_by(
            point_id=point_id,
            team_organization_id=get_current_team_id()
        ).all()
        
        # Format the data for the frontend
        result = []
        for throw in throws:
            # Get thrower and receiver names if available
            thrower_name = "Unknown"
            receiver_name = "Unknown"
            
            if throw.thrower_id:
                from app.models.player import Player
                thrower = Player.query.filter_by(
                    id=throw.thrower_id,
                    team_organization_id=get_current_team_id()
                ).first()
                
                if thrower:
                    thrower_name = thrower.name
            
            if throw.receiver_id:
                from app.models.player import Player
                receiver = Player.query.filter_by(
                    id=throw.receiver_id,
                    team_organization_id=get_current_team_id()
                ).first()
                
                if receiver:
                    receiver_name = receiver.name
            
            result.append({
                'id': throw.id,
                'throw_type': throw.throw_type,
                'thrower_id': throw.thrower_id,
                'thrower_name': thrower_name,
                'receiver_id': throw.receiver_id,
                'receiver_name': receiver_name,
                'x_start': throw.x_start,
                'y_start': throw.y_start,
                'x_end': throw.x_end,
                'y_end': throw.y_end,
                'is_completion': throw.is_completion,
                'break_throw': throw.break_throw,
                'distance': throw.distance
            })
        
        return jsonify({
            'success': True,
            'throws': result
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error("Error in get_throws:", str(e))
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500



from app.utils.team_filter import get_current_team_id


