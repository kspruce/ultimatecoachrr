from flask import Blueprint, jsonify, request, render_template, url_for
from flask_login import login_required
from app import db
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.game import Game
from app.models.stats import PlayerPointStats
from app.models.throws import Throw
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
            point = Point.query.get_or_404(point_id)
            
            # Create new event
            event = Event(
                point_id=point_id,
                player_id=int(data['player_id']),
                event_type=data['event_type'],
                field_position_x=float(data.get('field_position_x', 0)),
                field_position_y=float(data.get('field_position_y', 0)),
                is_offensive=bool(data.get('is_offensive', True))
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
                            event.field_position_y
                        )
                    )
                    db.session.add(assist_throw)

                    # If there's a second previous event, mark it as hockey assist
                    if len(previous_events) >= 2:
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
                                assist_event.field_position_y
                            )
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
                        event.field_position_y
                    )
                )
                db.session.add(regular_throw)

            # Handle throwaway events
            elif event.event_type == 'throwaway' and previous_event:
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
                    break_throw=is_break_throw(
                        previous_event.field_position_x,
                        previous_event.field_position_y,
                        event.field_position_x,
                        event.field_position_y
                    )
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
            else:  # D-line
                if event.event_type in ['block', 'forced_turnover']:
                    stats.d_line_plus_minus += 1
                elif event.event_type == 'scored_on':
                    stats.d_line_plus_minus -= 1

            # Update point status for point-ending events
            if event.event_type in ['goal', 'callahan']:
                point.point_outcome = 'scored'
                point.our_score_after = point.our_score_before + 1
            elif event.event_type == 'scored_on':
                point.point_outcome = 'conceded'
                point.their_score_after = point.their_score_before + 1

            # Calculate distances for throws
            for throw in db.session.new:
                if isinstance(throw, Throw):
                    throw.distance = throw.calculate_distance()  # Use the model's method

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
            elif last_event.event_type in ['throwaway', 'drop', 'block', 'handblock', 'stallout', 'forced_turnover', 'unforced_turnover']:
                point.is_offensive = not point.is_offensive  # Toggle possession back

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
                else:  # D-line
                    if last_event.event_type in ['block', 'forced_turnover']:
                        stats.d_line_plus_minus -= 1
                    elif last_event.event_type == 'scored_on':
                        stats.d_line_plus_minus += 1
                
                db.session.add(stats)

            db.session.add(point)
            db.session.commit()
            return jsonify({'message': 'Event undone'}), 200
        else:
            return jsonify({'error': 'No events to undo'}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



@bp.route('/finish_point/<int:point_id>', methods=['POST'])
@login_required
def finish_point(point_id):
    try:
        point = Point.query.get_or_404(point_id)
        game = Game.query.get_or_404(point.game_id)

        # Ensure point outcome is set
        if point.point_outcome is None:
            last_event = Event.query.filter_by(point_id=point_id).order_by(Event.id.desc()).first()
            if last_event:
                if last_event.event_type in ['goal', 'callahan']:
                    point.point_outcome = 'scored'
                    point.our_score_after = point.our_score_before + 1
                elif last_event.event_type == 'scored_on':
                    point.point_outcome = 'conceded'
                    point.their_score_after = point.their_score_before + 1

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

        db.session.commit()
        return jsonify({
            'message': 'Point finished', 
            'redirect': url_for('point.game_points', game_id=game.id)
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
            current_event.field_position_y
        )
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
