from flask import Blueprint, jsonify, request, render_template, url_for
from flask_login import login_required, current_user
from app import db
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.game import Game
from app.models.stats import PlayerPointStats
from app.models.throws import Throw
from app.models.user import User
from app.utils.stat_utils import determine_possession, is_point_ending_event
import math

bp = Blueprint('stat', __name__, url_prefix='/stats')

def is_break_throw(x_start, y_start, x_end, y_end, force_direction=None):
    """
    Determine if a throw is a break throw based on field position.
    
    A simple heuristic:
    1. If force_direction is known, use that
    2. Otherwise, detect if throw crosses the middle of the field (y=18.5)
    """
    # First check if any coordinates are None
    if x_start is None or y_start is None or x_end is None or y_end is None:
        print(f"Warning: Missing coordinates in is_break_throw: x_start={x_start}, y_start={y_start}, x_end={x_end}, y_end={y_end}")
        return False  # Default to not a break throw if coordinates are missing
        
    if force_direction:
        # If we know the force direction, use that logic
        if force_direction == 'forehand':
            # Forehand force means defense is forcing to the right from thrower's perspective
            # Break throw would go to the left (negative dx)
            return (x_end - x_start) < 0
        elif force_direction == 'backhand':
            # Backhand force means defense is forcing to the left
            # Break throw would go to the right (positive dx)
            return (x_end - x_start) > 0
    else:
        # If force direction is unknown, use field position heuristic
        # Check if throw crosses the middle of the field (assuming middle is at y=18.5m)
        if (y_start < 18.5 and y_end > 18.5) or (y_start > 18.5 and y_end < 18.5):
            return True
    
    return False



@bp.route('/record/<int:point_id>', methods=['GET', 'POST'])
@login_required
def record_events(point_id):
    if request.method == 'GET':
        point = Point.query.get_or_404(point_id)
        return render_template('stats/record.html', point=point)

    if request.method == 'POST':
        try:
            data = request.get_json()
            print(f"Received data: {data}")  # Debug the incoming data
            point = Point.query.get_or_404(point_id)
            
            # Handle special player IDs
            player_id = data.get('player_id')
            is_unknown_player = data.get('is_unknown_player', False)
            is_opponent = data.get('is_opponent', False)
            
            # Safely handle coordinates
            field_position_x = data.get('field_position_x')
            field_position_y = data.get('field_position_y')
            
            print(f"Coordinates: x={field_position_x}, y={field_position_y}")  # Debug coordinates
            
            # Create new event with safer coordinate handling
            event = Event(
                point_id=point_id,
                player_id=int(player_id),
                event_type=data['event_type'],
                field_position_x=float(field_position_x) if field_position_x is not None else 0.0,
                field_position_y=float(field_position_y) if field_position_y is not None else 0.0,
                is_offensive=bool(data.get('is_offensive', True)),
                is_unknown_player=is_unknown_player,
                is_opponent=is_opponent
            )
            
            # Add and flush the event to get its ID
            db.session.add(event)
            db.session.flush()
            


            # Get previous event in this point
            previous_event = Event.query.filter(
                Event.point_id == point_id,
                Event.id < event.id
            ).order_by(Event.id.desc()).first()

            # Handle goal events and create associated throws
            if event.event_type == 'goal':
                # Get previous events for assist and hockey assist
                previous_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.id < event.id
                ).order_by(Event.id.desc()).limit(2).all()
            
                if previous_events:
                    # Mark first previous event as assist
                    assist_event = previous_events[0]
                    assist_event.event_type = 'assist'
                    
                    # Check if all required coordinates are present
                    if (assist_event.field_position_x is not None and 
                        assist_event.field_position_y is not None and
                        event.field_position_x is not None and
                        event.field_position_y is not None):
                        
                        # Calculate break_throw status safely
                        try:
                            is_break = is_break_throw(
                                assist_event.field_position_x,
                                assist_event.field_position_y,
                                event.field_position_x,
                                event.field_position_y
                            )
                        except Exception as e:
                            print(f"Error calculating break throw for assist: {e}")
                            is_break = False
                            
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
                            break_throw=is_break
                        )
                    else:
                        # Create throw without break_throw calculation if coordinates are missing
                        assist_throw = Throw(
                            point_id=point_id,
                            thrower_id=assist_event.player_id,
                            receiver_id=event.player_id,
                            throwing_event_id=assist_event.id,
                            receiving_event_id=event.id,
                            throw_type='assist',
                            is_completion=True,
                            break_throw=False  # Default to False when we can't calculate
                        )
                    
                    db.session.add(assist_throw)
        



                    # If there's a second previous event, mark it as hockey assist
                    if len(previous_events) >= 2:
                        hockey_assist_event = previous_events[1]
                        hockey_assist_event.event_type = 'hockey_assist'
                        
                        # Check if all required coordinates are present
                        if (hockey_assist_event.field_position_x is not None and 
                            hockey_assist_event.field_position_y is not None and
                            assist_event.field_position_x is not None and
                            assist_event.field_position_y is not None):
                            
                            # Calculate break_throw status safely
                            try:
                                is_break = is_break_throw(
                                    hockey_assist_event.field_position_x,
                                    hockey_assist_event.field_position_y,
                                    assist_event.field_position_x,
                                    assist_event.field_position_y
                                )
                            except Exception as e:
                                print(f"Error calculating break throw for hockey assist: {e}")
                                is_break = False
                                
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
                                break_throw=is_break
                            )
                        else:
                            # Create throw without break_throw calculation if coordinates are missing
                            print(f"Warning: Missing coordinates for hockey assist. Creating throw without break_throw calculation.")
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
                                break_throw=False  # Default to False when we can't calculate
                            )
                        db.session.add(hockey_throw)

                        # Remove any regular throws that are now hockey assists
                        regular_throw = Throw.query.filter(
                            Throw.point_id == point_id,
                            Throw.thrower_id == hockey_assist_event.player_id,
                            Throw.receiver_id == assist_event.player_id,
                            Throw.throw_type == 'regular'
                        ).first()
                        
                        if regular_throw:
                            print(f"Removing regular throw {regular_throw.id} that is now a hockey assist")
                            db.session.delete(regular_throw)

                        
                        

            # Create regular throw if this is a catch
            elif event.event_type == 'catch' and previous_event:
                # Check if all required coordinates are present
                if (previous_event.field_position_x is not None and 
                    previous_event.field_position_y is not None and
                    event.field_position_x is not None and
                    event.field_position_y is not None):
                    
                    # Calculate break_throw status
                    try:
                        is_break = is_break_throw(
                            previous_event.field_position_x,
                            previous_event.field_position_y,
                            event.field_position_x,
                            event.field_position_y
                        )
                    except Exception as e:
                        print(f"Error calculating break throw: {e}")
                        is_break = False
                        
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
                        break_throw=is_break
                    )
                    db.session.add(regular_throw)
                else:
                    # Create throw without break_throw calculation if coordinates are missing
                    print(f"Warning: Missing coordinates for throw. Creating throw without break_throw calculation.")
                    regular_throw = Throw(
                        point_id=point_id,
                        thrower_id=previous_event.player_id,
                        receiver_id=event.player_id,
                        throwing_event_id=previous_event.id,
                        receiving_event_id=event.id,
                        throw_type='regular',
                        is_completion=True,
                        break_throw=False  # Default to False when we can't calculate
                    )
                    db.session.add(regular_throw)
                


            # Handle throwaway events
            elif event.event_type == 'throwaway' and previous_event:
                # Check if all required coordinates are present
                if (previous_event.field_position_x is not None and 
                    previous_event.field_position_y is not None and
                    event.field_position_x is not None and
                    event.field_position_y is not None):
                    
                    # Calculate break_throw status safely
                    try:
                        is_break = is_break_throw(
                            previous_event.field_position_x,
                            previous_event.field_position_y,
                            event.field_position_x,
                            event.field_position_y
                        )
                    except Exception as e:
                        print(f"Error calculating break throw for throwaway: {e}")
                        is_break = False
                        
                    throwaway = Throw(
                        point_id=point_id,
                        thrower_id=event.player_id,
                        receiver_id=None,
                        throwing_event_id=previous_event.id,
                        receiving_event_id=event.id,
                        x_start=previous_event.field_position_x,
                        y_start=previous_event.field_position_y,
                        x_end=event.field_position_x,
                        y_end=event.field_position_y,
                        throw_type='throwaway',
                        is_completion=False,
                        break_throw=is_break
                    )
                else:
                    # Create throw without break_throw calculation if coordinates are missing
                    print(f"Warning: Missing coordinates for throwaway. Creating throw without break_throw calculation.")
                    throwaway = Throw(
                        point_id=point_id,
                        thrower_id=event.player_id,
                        receiver_id=None,
                        throwing_event_id=previous_event.id,
                        receiving_event_id=event.id,
                        x_start=previous_event.field_position_x,
                        y_start=previous_event.field_position_y,
                        x_end=event.field_position_x,
                        y_end=event.field_position_y,
                        throw_type='throwaway',
                        is_completion=False,
                        break_throw=False  # Default to False when we can't calculate
                    )
                db.session.add(throwaway)


            # Update PlayerPointStats
            stats = PlayerPointStats.query.filter_by(
                player_id=event.player_id,
                point_id=point_id
            ).first()
            
            if not stats:
                stats = PlayerPointStats(
                    player_id=event.player_id,
                    point_id=point_id,
                    o_line_plus_minus=0.0,
                    d_line_plus_minus=0.0
                )
                db.session.add(stats)

            # Update stats based on event type
            if point.our_line_type == 'O-line':
                if event.event_type in ['goal', 'assist']:
                    stats.o_line_plus_minus += 1
                elif event.event_type in ['throwaway', 'drop']:
                    stats.o_line_plus_minus -= 1
                    # Track O-line turnovers
                    stats.o_line_turnovers += 1
            else:  # D-line
                if event.event_type in ['block', 'forced_turnover']:
                    stats.d_line_plus_minus += 1
                    # Mark as a break opportunity
                    stats.d_line_break_opportunity = True
                elif event.event_type == 'scored_on':
                    stats.d_line_plus_minus -= 1

            # Update point status for point-ending events
            if event.event_type in ['goal', 'callahan']:
                point.point_outcome = 'scored'
                point.our_score_after = point.our_score_before + 1
                
                # If O-line, check for clean hold
                if point.our_line_type == 'O-line':
                    # Check if there were any turnovers in this point
                    turnover_events = Event.query.filter(
                        Event.point_id == point_id,
                        Event.event_type.in_(['throwaway', 'drop'])
                    ).count()
                    
                    if turnover_events == 0:
                        # This was a clean hold
                        stats.o_line_clean_holds = True
                
                # If D-line and there was a break opportunity, mark as converted
                elif point.our_line_type == 'D-line' and stats.d_line_break_opportunity:
                    stats.d_line_break_conversion = True
                    
            elif event.event_type == 'scored_on':
                point.point_outcome = 'conceded'
                point.their_score_after = point.their_score_before + 1

            # Calculate distances for throws
            # Calculate distances for throws
            for throw in db.session.new:
                if isinstance(throw, Throw):
                    try:
                        throw.distance = throw.calculate_distance()  # Use the model's method
                    except Exception as e:
                        print(f"Error calculating distance: {e}")
                        throw.distance = 0  # Set a default value


            # Check for O-line "got it back" scenario
            if point.our_line_type == 'O-line' and stats.o_line_turnovers > 0:
                # If we scored after having a turnover, we "got it back"
                if event.event_type in ['goal', 'callahan']:
                    stats.o_line_got_back = True

            db.session.commit()
            return jsonify(event.to_dict()), 201

        except Exception as e:
            print("Error recording event:", str(e))
            db.session.rollback()
            return jsonify({'error': str(e)}), 400




@bp.route('/undo_event/<int:point_id>', methods=['POST'])
@login_required
def undo_event(point_id):
    try:
        point = Point.query.get_or_404(point_id)
        last_event = Event.query.filter_by(point_id=point_id).order_by(Event.id.desc()).first()

        if last_event:
            # First, delete any throws associated with this event
            from app.models.throws import Throw
            
            # Delete throws where this event is the receiving event
            throws_received = Throw.query.filter_by(receiving_event_id=last_event.id).all()
            for throw in throws_received:
                db.session.delete(throw)
                
            # Delete throws where this event is the throwing event
            throws_thrown = Throw.query.filter_by(throwing_event_id=last_event.id).all()
            for throw in throws_thrown:
                db.session.delete(throw)
            
            # Now delete the event itself
            db.session.delete(last_event)

            # Update point if necessary
            if last_event.event_type == 'goal':
                point.point_outcome = None  # Reset outcome
                point.our_score_after = point.our_score_before
            elif last_event.event_type == 'scored_on':
                point.point_outcome = None
                point.their_score_after = point.their_score_before
            
            # Don't try to update point.is_offensive as it doesn't exist
            # The client-side code will handle possession state

            # Update player stats if necessary
            from app.models.stats import PlayerPointStats
            stats = PlayerPointStats.query.filter_by(
                player_id=last_event.player_id,
                point_id=point_id
            ).first()
            
            if stats:
                # Reverse the stat changes based on event type
                if point.our_line_type == 'O-line':
                    if last_event.event_type in ['goal', 'assist']:
                        stats.o_line_plus_minus -= 1
                    elif last_event.event_type in ['throwaway', 'drop']:
                        stats.o_line_plus_minus += 1
                        # Reverse O-line turnovers
                        stats.o_line_turnovers -= 1
                else:  # D-line
                    if last_event.event_type in ['block', 'forced_turnover']:
                        stats.d_line_plus_minus -= 1
                        # If this was the only break opportunity, reset it
                        if stats.d_line_break_opportunity:
                            # Check if there are other break opportunities
                            other_breaks = Event.query.filter(
                                Event.point_id == point_id,
                                Event.event_type.in_(['block', 'forced_turnover']),
                                Event.id != last_event.id
                            ).count()
                            
                            if other_breaks == 0:
                                stats.d_line_break_opportunity = False
                                stats.d_line_break_conversion = False
                    elif last_event.event_type == 'scored_on':
                        stats.d_line_plus_minus += 1
                
                # If undoing a goal, reset clean hold and got it back flags
                if last_event.event_type == 'goal' and point.our_line_type == 'O-line':
                    stats.o_line_clean_holds = False
                    stats.o_line_got_back = False
                
                db.session.add(stats)

            db.session.add(point)
            db.session.commit()
            return jsonify({'message': 'Event undone'}), 200
        else:
            return jsonify({'error': 'No events to undo'}), 400

    except Exception as e:
        import traceback
        print("Error in undo_event:", str(e))
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/undo_cutting_skill/<int:point_id>', methods=['POST'])
@login_required
def undo_cutting_skill(point_id):
    try:
        data = request.get_json()
        cutting_skill_id = data.get('cutting_skill_id')
        
        if not cutting_skill_id:
            return jsonify({'error': 'No cutting skill ID provided'}), 400
        
        from app.models.cutting_skill import CuttingSkill
        cutting_skill = CuttingSkill.query.get_or_404(cutting_skill_id)
        
        if cutting_skill.point_id != point_id:
            return jsonify({'error': 'Cutting skill does not belong to this point'}), 400
        
        db.session.delete(cutting_skill)
        db.session.commit()
        
        return jsonify({'message': 'Cutting skill undone'}), 200
    
    except Exception as e:
        import traceback
        print("Error in undo_cutting_skill:", str(e))
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/finish_point/<int:point_id>', methods=['POST'])
@login_required
def finish_point(point_id):
    try:
        point = Point.query.get_or_404(point_id)
        game = Game.query.get_or_404(point.game_id)

        # Always check the last event to determine point outcome
        last_event = Event.query.filter_by(point_id=point_id).order_by(Event.id.desc()).first()
        
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
        game.our_score = point.our_score_after
        game.their_score = point.their_score_after

        # Remove duplicate throws (regular throws that were later marked as hockey assists)
        from app.models.throws import Throw
        
        # Get all hockey assist throws in this point
        hockey_assists = Throw.query.filter_by(
            point_id=point_id,
            throw_type='hockey_assist'
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
                Throw.id != hockey.id  # Make sure we don't delete the hockey assist itself
            ).all()
            
            for duplicate in duplicate_throws:
                print(f"Removing duplicate throw: {duplicate.id} (regular) in favor of hockey assist: {hockey.id}")
                db.session.delete(duplicate)

        # Calculate final stats for all players in the point
        for lineup in point.lineups:
            stats = PlayerPointStats.query.filter_by(
                player_id=lineup.player_id,
                point_id=point_id
            ).first()
            
            if not stats:
                stats = PlayerPointStats(
                    player_id=lineup.player_id,
                    point_id=point_id
                )
                db.session.add(stats)
            
            # Calculate O-line clean holds
            if point.our_line_type == 'O-line' and point.point_outcome == 'scored':
                # Check if there were any turnovers in this point
                turnover_events = Event.query.filter(
                    Event.point_id == point_id,
                    Event.event_type.in_(['throwaway', 'drop'])
                ).count()
                
                if turnover_events == 0:
                    stats.o_line_clean_holds = True
                elif turnover_events > 0 and point.point_outcome == 'scored':
                    # If we had turnovers but still scored, we "got it back"
                    stats.o_line_got_back = True
            
            # Calculate D-line break opportunities and conversions
            elif point.our_line_type == 'D-line':
                # Check if we generated any turnovers
                break_opportunities = Event.query.filter(
                    Event.point_id == point_id,
                    Event.event_type.in_(['block', 'forced_turnover'])
                ).count()
                
                if break_opportunities > 0:
                    stats.d_line_break_opportunity = True
                    
                    # If we scored, it's a break conversion
                    if point.point_outcome == 'scored':
                        stats.d_line_break_conversion = True

        throws_without_distance = Throw.query.filter_by(point_id=point_id).filter(
            (Throw.distance.is_(None)) | (Throw.distance == 0)
        ).all()
        
        for throw in throws_without_distance:
            if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
                try:
                    throw.distance = math.sqrt(
                        (throw.x_end - throw.x_start) ** 2 +
                        (throw.y_end - throw.y_start) ** 2
                    )
                    print(f"Calculated missing distance for throw {throw.id}: {throw.distance:.2f}m")
                except Exception as e:
                    print(f"Error calculating distance for throw {throw.id}: {e}")
                    throw.distance = 0  # Set a default value


        db.session.commit()
        
        # Return both redirect and redirect_url for compatibility
        return jsonify({
            'message': f'Point finished. Outcome: {point.point_outcome}', 
            'redirect': url_for('point.game_points', game_id=game.id),
            'redirect_url': url_for('point.game_points', game_id=game.id),
            'game_id': game.id,  # Include game_id explicitly
            'point_outcome': point.point_outcome  # Include the determined outcome
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    


def calculate_assists(point, goal_event):
    # Get events for the point, ordered by timestamp if available, otherwise by ID
    events = sorted(point.events.all(), key=lambda e: (e.timestamp or 0, e.id))

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
    
    # Check if all required coordinates are present
    if (previous_event.field_position_x is not None and 
        previous_event.field_position_y is not None and
        current_event.field_position_x is not None and
        current_event.field_position_y is not None):
        
        # Calculate break_throw status safely
        try:
            is_break = is_break_throw(
                previous_event.field_position_x,
                previous_event.field_position_y,
                current_event.field_position_x,
                current_event.field_position_y
            )
        except Exception as e:
            print(f"Error calculating break throw in create_throw_from_events: {e}")
            is_break = False
    else:
        is_break = False
    
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
        break_throw=is_break
    )
    
    # Calculate distance only if coordinates are valid
    if (throw.x_start is not None and throw.y_start is not None and 
        throw.x_end is not None and throw.y_end is not None):
        try:
            throw.distance = math.sqrt(
                (throw.x_end - throw.x_start) ** 2 +
                (throw.y_end - throw.y_start) ** 2
            )
        except Exception as e:
            print(f"Error calculating distance in create_throw_from_events: {e}")
            throw.distance = 0  # Set a default value
    
    # Determine throw type
    if current_event.event_type == 'goal':
        throw.throw_type = 'assist'
    elif current_event.event_type == 'hockey_assist':
        throw.throw_type = 'hockey_assist'
    else:
        throw.throw_type = 'regular'
    
    return throw


@bp.route('/admin/mark_break_throws')
@login_required
def mark_break_throws():
    """Retroactively mark break throws in the database"""
    # Get all throws that don't have break_throw set
    throws = Throw.query.filter(Throw.break_throw.is_(None)).all()
    
    count = 0
    for throw in throws:
        if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
            throw.break_throw = is_break_throw(throw.x_start, throw.y_start, throw.x_end, throw.y_end)
            if throw.break_throw:
                count += 1
    
    db.session.commit()
    return jsonify({
        'message': f'Marked {count} throws as break throws',
        'total_processed': len(throws)
    })

@bp.route('/debug/break_throws')
@login_required
def debug_break_throws():
    """Debug route to check break throws"""
    # Get all throws
    all_throws = Throw.query.all()
    
    # Count break throws
    break_throws = [t for t in all_throws if t.break_throw]
    
    # Get sample break throws
    sample_break_throws = break_throws[:10]
    
    return jsonify({
        'total_throws': len(all_throws),
        'break_throws': len(break_throws),
        'percentage': (len(break_throws) / len(all_throws) * 100) if all_throws else 0,
        'sample_break_throws': [{
            'id': t.id,
            'thrower_id': t.thrower_id,
            'thrower_name': t.thrower.name if t.thrower else 'Unknown',
            'throw_type': t.throw_type,
            'x_start': t.x_start,
            'y_start': t.y_start,
            'x_end': t.x_end,
            'y_end': t.y_end,
            'is_completion': t.is_completion
        } for t in sample_break_throws]
    })

@bp.route('/admin/recalculate_throw_distances')
@login_required
def recalculate_throw_distances():
    """Recalculate distances for all throws in the database"""
    try:
        from app.models.throws import Throw
        import math
        
        # Get all throws
        throws = Throw.query.all()
        updated_count = 0
        

        for throw in throws:
            if throw.x_start is not None and throw.y_start is not None and throw.x_end is not None and throw.y_end is not None:
                try:
                    old_distance = throw.distance
                    throw.distance = math.sqrt(
                        (throw.x_end - throw.x_start) ** 2 +
                        (throw.y_end - throw.y_start) ** 2
                    )
                    
                    if old_distance != throw.distance:
                        updated_count += 1
                except Exception as e:
                    print(f"Error recalculating distance for throw {throw.id}: {e}")

        
        db.session.commit()
        return jsonify({
            'message': f'Recalculated distances for {updated_count} throws',
            'total_throws': len(throws)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



@bp.route('/available_players/<int:point_id>', methods=['GET'])
@login_required
def available_players(point_id):
    try:
        print(f"Fetching available players for point {point_id}")
        point = Point.query.get_or_404(point_id)
        print(f"Found point: {point}")
        game = Game.query.get_or_404(point.game_id)
        print(f"Found game: {game}")
        
        # Get players already in the point
        current_player_ids = [lineup.player_id for lineup in point.lineups]
        print(f"Current player IDs in lineup: {current_player_ids}")
        
        # Get all active players not in the current lineup
        from app.models.player import Player
        
        # Get all active players
        available_players = Player.query.filter_by(active=True).all()
        
        # Filter out players already in the lineup
        available_players = [p for p in available_players if p.id not in current_player_ids]
        
        print(f"Found {len(available_players)} available players")
        
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
        print(f"Returning result: {result}")
        return jsonify(result)
    except Exception as e:
        import traceback
        print("Error in available_players:", str(e))
        print(traceback.format_exc())
        return jsonify({'error': str(e), 'available_players': []}), 500



@bp.route('/substitute_player/<int:point_id>', methods=['POST'])
@login_required
def substitute_player(point_id):
    try:
        data = request.get_json()
        point = Point.query.get_or_404(point_id)
        
        player_out_id = int(data['player_out_id'])
        player_in_id = int(data['player_in_id'])
        
        # Get the players
        from app.models.player import Player
        player_out = Player.query.get_or_404(player_out_id)
        player_in = Player.query.get_or_404(player_in_id)
        
        # Check if player_out is in the lineup
        lineup_out = LineUp.query.filter_by(
            point_id=point_id,
            player_id=player_out_id
        ).first()
        
        if not lineup_out:
            return jsonify({'success': False, 'error': 'Player not found in lineup'}), 400
        
        # Instead of removing player_out, we'll keep them in the lineup
        # but mark them as substituted out (if you have such a field)
        # If you don't have a field to track substitution status, you can add one
        
        # Add the player_in to the lineup
        lineup_in = LineUp(
            point_id=point_id,
            player_id=player_in_id
        )
        db.session.add(lineup_in)
        
        # Record the substitution as an event
        sub_event = Event(
            point_id=point_id,
            player_id=player_in_id,
            event_type='substitution',
            field_position_x=50,  # Center of field
            field_position_y=18.5,
            is_offensive=point.starting_position == 'offense'
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
        print("Error in substitute_player:", str(e))
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# New route to get player stats with permission checking
@bp.route('/player/<int:player_id>', methods=['GET'])
@login_required
def get_player_stats(player_id):
    # Check if the current user is an admin or if they're viewing their own stats
    is_admin = current_user.is_admin
    is_own_stats = current_user.player and current_user.player.id == player_id
    
    if not (is_admin or is_own_stats):
        return jsonify({'error': 'You do not have permission to view these stats'}), 403
    
    # If permissions are valid, proceed with getting the stats
    from app.models.player import Player
    player = Player.query.get_or_404(player_id)
    
    # Get the player's stats (implementation depends on your data structure)
    # This is just a placeholder - you'll need to implement the actual stats retrieval
    stats = {
        'player': {
            'id': player.id,
            'name': player.name,
            'jersey_number': player.jersey_number
        },
        'stats': {
            # Add all the stats you want to return
        }
    }
    
    return jsonify(stats)

# New route to get team average stats
@bp.route('/team_average', methods=['GET'])
@login_required
def get_team_average_stats():
    # Calculate team average stats
    # This is a placeholder - you'll need to implement the actual calculation
    team_avg_stats = {
        'completion_rate': 0,
        'o_line_clean_holds_rate': 0,
        'o_line_turnovers_per_point': 0,
        'o_line_get_it_back_rate': 0,
        'd_line_break_opportunities_per_point': 0,
        'd_line_break_conversion_rate': 0,
        # Add other team average stats
    }
    
    # Calculate the stats based on all players' data
    from app.models.stats import PlayerPointStats
    from app.models.point import Point
    
    # Get all points
    points = Point.query.all()
    
    # Initialize counters
    total_o_line_points = 0
    total_d_line_points = 0
    total_o_line_clean_holds = 0
    total_o_line_turnovers = 0
    total_o_line_got_back = 0
    total_d_line_break_opportunities = 0
    total_d_line_break_conversions = 0
    
    # Calculate stats from all points
    for point in points:
        if point.our_line_type == 'O-line':
            total_o_line_points += 1
            
            # Get all player stats for this point
            point_stats = PlayerPointStats.query.filter_by(point_id=point.id).all()
            
            # Count clean holds, turnovers, and got-it-back instances
            has_clean_hold = any(stat.o_line_clean_holds for stat in point_stats)
            if has_clean_hold:
                total_o_line_clean_holds += 1
            
            point_turnovers = sum(stat.o_line_turnovers for stat in point_stats)
            total_o_line_turnovers += point_turnovers
            
            got_back = any(stat.o_line_got_back for stat in point_stats)
            if got_back:
                total_o_line_got_back += 1
                
        elif point.our_line_type == 'D-line':
            total_d_line_points += 1
            
            # Get all player stats for this point
            point_stats = PlayerPointStats.query.filter_by(point_id=point.id).all()
            
            # Count break opportunities and conversions
            has_break_opportunity = any(stat.d_line_break_opportunity for stat in point_stats)
            if has_break_opportunity:
                total_d_line_break_opportunities += 1
                
                has_break_conversion = any(stat.d_line_break_conversion for stat in point_stats)
                if has_break_conversion:
                    total_d_line_break_conversions += 1
    
    # Calculate rates
    if total_o_line_points > 0:
        team_avg_stats['o_line_clean_holds_rate'] = (total_o_line_clean_holds / total_o_line_points) * 100
        team_avg_stats['o_line_turnovers_per_point'] = total_o_line_turnovers / total_o_line_points
        
        # Calculate get-it-back rate (only for points with turnovers)
        points_with_turnovers = sum(1 for p in points if p.our_line_type == 'O-line' and 
                                   any(s.o_line_turnovers > 0 for s in PlayerPointStats.query.filter_by(point_id=p.id).all()))
        
        if points_with_turnovers > 0:
            team_avg_stats['o_line_get_it_back_rate'] = (total_o_line_got_back / points_with_turnovers) * 100
    
    if total_d_line_points > 0:
        team_avg_stats['d_line_break_opportunities_per_point'] = total_d_line_break_opportunities / total_d_line_points
        
        if total_d_line_break_opportunities > 0:
            team_avg_stats['d_line_break_conversion_rate'] = (total_d_line_break_conversions / total_d_line_break_opportunities) * 100
    
    return jsonify(team_avg_stats)

