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
from app.stats.throw_rebuild import rebuild_point_throws, rebuild_throws
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

            # A goal makes the catch before it the assist, and the catch
            # before that the hockey assist (substitutions aren't play).
            # Only catches are promoted: blocks, drops, throwaways etc. are
            # never retyped, and opponent plays aren't part of our chain.
            if event.event_type == 'goal':
                previous_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.id < event.id,
                    Event.event_type != 'substitution',
                    Event.team_organization_id == get_current_team_id()
                ).order_by(Event.id.desc()).limit(2).all()

                def assistable(e):
                    return e.event_type == 'catch' and not e.is_opponent

                if previous_events and assistable(previous_events[0]):
                    previous_events[0].event_type = 'assist'
                    if len(previous_events) >= 2 and assistable(previous_events[1]):
                        previous_events[1].event_type = 'hockey_assist'

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

            # The point's throws follow from its events
            rebuild_point_throws(point)

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
            # Undoing a goal puts the assist and hockey assist back to the
            # catches they were, so a re-recorded goal promotes them cleanly.
            if last_event.event_type == 'goal':
                prior_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.id < last_event.id,
                    Event.event_type != 'substitution',
                    Event.team_organization_id == get_current_team_id()
                ).order_by(Event.id.desc()).limit(2).all()
                for prior, retyped in zip(prior_events, ('assist', 'hockey_assist')):
                    if prior.event_type == retyped:
                        prior.event_type = 'catch'

            db.session.delete(last_event)
            rebuild_point_throws(point)

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

        # Make sure the stored throws match the events
        rebuild_point_throws(point)

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
    



@bp.route('/admin/rebuild_throws', methods=['POST'])
@login_required
@admin_required
def rebuild_team_throws():
    """Rebuild every one of this team's stored throws from the events."""
    points = Point.query.filter_by(team_organization_id=get_current_team_id()).all()
    count, removed, added = rebuild_throws(points)
    db.session.commit()
    flash(f'Rebuilt throws for {count} points: {removed} throws replaced by {added}.', 'success')
    return redirect(url_for('data_management.data_management'))


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
        current_app.logger.exception("Error in available_players")
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
        current_app.logger.exception("Error in substitute_player")
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
        current_app.logger.exception("Error in get_cutting_skills")
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
        current_app.logger.exception("Error in get_events")
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
        current_app.logger.exception("Error in get_throws")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500



from app.utils.team_filter import get_current_team_id


