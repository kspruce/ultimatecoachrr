from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app import db
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.player import Player
from app.models.event import Pull
from app.forms.point import PointForm
from app.models.event import Event
from app.models.throws import Throw
from app.models.stats import PlayerPointStats
from app.utils.utils import admin_required

bp = Blueprint('point', __name__, url_prefix='/points')

@bp.route('/game/<int:game_id>')
@login_required
def game_points(game_id):
    game = Game.query.get_or_404(game_id)
    points = Point.query.filter_by(game_id=game_id).order_by(Point.point_number).all()
    return render_template('point/game_points.html', game=game, points=points)

def get_player_stats(game_id):
    """Get statistics for all players who have played in the game."""
    # Get all points for this game
    points = Point.query.filter_by(game_id=game_id).all()
    point_ids = [p.id for p in points]
    
    if not point_ids:
        return []
    
    # Initialize stats dictionary
    player_stats = {}
    
    # Get all players who have played in the game
    players = db.session.query(Player)\
        .join(LineUp)\
        .join(Point)\
        .filter(Point.game_id == game_id)\
        .distinct().all()
    
    for player in players:
        # Get all events for this player
        events = Event.query\
            .filter(
                Event.point_id.in_(point_ids),
                Event.player_id == player.id
            )\
            .order_by(Event.id)\
            .all()
        
        # Initialize stats
        stats = {
            'completions': 0,
            'throwaways': 0,
            'drops': 0,
            'catches': 0,
            'goals': 0,
            'assists': 0,
            'blocks': 0,
            'hockey_assists': 0,
            'throws': 0  # Track total throws separately
        }
        
        # Count each event type
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
                stats['throws'] += 1  # A drop implies a throw was made
        
        # Count additional completions from regular throws
        for i in range(len(events)-1):
            current_event = events[i]
            next_event = events[i+1]
            
            # If this is a regular throw (not already counted as assist/hockey assist)
            if (current_event.event_type == 'regular' and
                current_event.field_position_x is not None and 
                current_event.field_position_y is not None and 
                next_event.field_position_x is not None and 
                next_event.field_position_y is not None):
                stats['completions'] += 1
                stats['throws'] += 1
        
        # Calculate plus/minus
        plus_minus = (
            stats['goals'] + 
            stats['assists'] + 
            stats['blocks'] - 
            stats['throwaways'] - 
            stats['drops']
        )
        
        # Count points played
        points_played = LineUp.query\
            .join(Point)\
            .filter(
                Point.game_id == game_id,
                LineUp.player_id == player.id
            ).count()
        
        # Calculate completion rate using total throws
        completion_rate = 0
        if stats['throws'] > 0:
            completion_rate = round((stats['completions'] / stats['throws']) * 100, 1)
        
        player_stats[player.id] = {
            'player_id': player.id,  # Add this line to include player ID
            'player_name': player.name,
            'jersey_number': player.jersey_number,
            'points_played': points_played,
            'plus_minus': plus_minus,
            'completion_rate': completion_rate,
            'completions': stats['completions'],
            'throws': stats['throws'],  # Total throws
            'throwaways': stats['throwaways'],
            'drops': stats['drops'],
            'goals': stats['goals'],
            'assists': stats['assists'],
            'blocks': stats['blocks'],
            'hockey_assists': stats['hockey_assists']
        }
    
    # Sort by points played (descending)
    return sorted(
        player_stats.values(),
        key=lambda x: (x['points_played'], x['plus_minus']),
        reverse=True
    )


def calculate_completion_rate(game_id):
    """Calculate the team's completion rate for the game so far."""
    # Get all points for this game
    points = Point.query.filter_by(game_id=game_id).all()
    point_ids = [p.id for p in points]
    
    if not point_ids:
        return 0
    
    # Get all events in chronological order
    events = Event.query\
        .filter(Event.point_id.in_(point_ids))\
        .order_by(Event.id)\
        .all()
    
    completions = 0
    throwaways = 0
    
    # Count consecutive throw/catch sequences
    for i in range(len(events)-1):
        current_event = events[i]
        next_event = events[i+1]
        
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





def determine_gender_ratio(point_number):
    """
    Determine gender ratio based on ABBAABBAABBAA pattern
    A = 4-3, B = 3-4
    """
    if point_number == 1:
        return '4-3'  # First point starts with A
    
    # Calculate position in pattern (1-4)
    pattern_position = ((point_number - 1) % 4) + 1
    
    # Points 1 and 2 in pattern are "A" (4-3), points 3 and 4 are "B" (3-4)
    return '4-3' if pattern_position in [1, 2] else '3-4'

def determine_line_and_position(previous_point):
    """
    Determine line type and starting position based on previous point outcome
    """
    if not previous_point:
        return 'O-line', 'offense'  # Default for first point
        
    if previous_point.point_outcome == 'scored':
        # We scored, so we're now on defense
        return 'D-line', 'defense'
    else:
        # They scored, so we're now on offense
        return 'O-line', 'offense'



@bp.route('/add/<int:game_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_point(game_id):
    game = Game.query.get_or_404(game_id)
    form = PointForm()
    
    # Get all active players
    all_players = Player.query.filter_by(active=True).order_by(Player.jersey_number).all()
    
    # Get player stats
    player_stats = get_player_stats(game_id)
    
    # Create a dictionary for quick player stats lookup
    player_stats_dict = {}
    for stat in player_stats:
        if 'player_id' in stat:
            player_stats_dict[stat['player_id']] = stat
    
    # Get the last point for this game
    last_point = Point.query.filter_by(game_id=game_id)\
        .order_by(Point.point_number.desc())\
        .first()
    
    # On GET request, set default values
    if request.method == 'GET':
        # Set point number
        next_point_number = 1 if not last_point else last_point.point_number + 1
        form.point_number.data = next_point_number
        
        # Set scores
        form.our_score_before.data = game.our_score
        form.their_score_before.data = game.their_score
        
        # Set gender ratio based on pattern
        form.gender_ratio.data = determine_gender_ratio(next_point_number)
        
        # Set line type and starting position based on previous point
        line_type, starting_position = determine_line_and_position(last_point)
        form.our_line_type.data = line_type
        form.starting_position.data = starting_position
    
    # Process the player selection before form validation
    if request.method == 'POST':
        # Get the selected players from the form data
        selected_players_str = request.form.get('players', '')
        print(f"DEBUG: Raw players field value: '{selected_players_str}'")
        
        if selected_players_str:
            try:
                # Convert comma-separated string to list of integers
                selected_players = [int(pid) for pid in selected_players_str.split(',') if pid]
                print(f"DEBUG: Selected players: {selected_players}")
                
                # Set the data directly, bypassing validation
                form.players.data = selected_players
                
                # Clear any errors for this field
                if 'players' in form.errors:
                    del form.errors['players']
            except ValueError as e:
                print(f"DEBUG: Error converting player IDs: {e}")
                form.players.data = []
        else:
            print("DEBUG: No players selected in form data")
            form.players.data = []
    
    if form.validate_on_submit() or (request.method == 'POST' and form.errors.get('players') and len(form.errors) == 1):
        try:
            # Check if we have exactly 7 players
            if len(form.players.data) != 7:
                flash(f'You must select exactly 7 players. You selected {len(form.players.data)}.', 'danger')
                return render_template('point/point_form.html',
                                     form=form,
                                     game=game,
                                     title='Add Point',
                                     completion_rate=calculate_completion_rate(game_id),
                                     player_stats=player_stats,
                                     all_players=all_players,
                                     player_stats_dict=player_stats_dict)
            
            # Validate gender ratio
            male_count = 0
            female_count = 0
            
            for player_id in form.players.data:
                player = Player.query.get(player_id)
                if player:
                    if player.gender == "male":
                        male_count += 1
                    elif player.gender == "female":
                        female_count += 1
            
            # Get required ratio
            required_male, required_female = map(int, form.gender_ratio.data.split('-'))
            
            if male_count != required_male or female_count != required_female:
                flash(f'Selected players do not match the gender ratio. Need {required_male} male and {required_female} female players. You selected {male_count} male and {female_count} female players.', 'danger')
                return render_template('point/point_form.html',
                                     form=form,
                                     game=game,
                                     title='Add Point',
                                     completion_rate=calculate_completion_rate(game_id),
                                     player_stats=player_stats,
                                     all_players=all_players,
                                     player_stats_dict=player_stats_dict)
            
            # Create the point
            point = Point(
                game_id=game_id,
                point_number=form.point_number.data,
                our_line_type=form.our_line_type.data,
                our_score_before=form.our_score_before.data,
                their_score_before=form.their_score_before.data,
                starting_position=form.starting_position.data,
                gender_ratio=form.gender_ratio.data,
                force_direction=form.force_direction.data,
                point_outcome=form.point_outcome.data,
                duration=form.duration.data,
                timestamp_in_video=form.timestamp_in_video.data
            )
            
            # Calculate scores after point
            if form.point_outcome.data == 'scored':
                point.our_score_after = form.our_score_before.data + 1
                point.their_score_after = form.their_score_before.data
            else:
                point.our_score_after = form.our_score_before.data
                point.their_score_after = form.their_score_before.data + 1
            
            db.session.add(point)
            db.session.commit()
            
            # Add players to lineup
            for player_id in form.players.data:
                lineup = LineUp(point_id=point.id, player_id=player_id)
                db.session.add(lineup)
            
            # Update game score
            game.our_score = point.our_score_after
            game.their_score = point.their_score_after
            
            db.session.commit()
            
            flash(f'Point {point.point_number} has been added!', 'success')
            return redirect(url_for('stat.record_events', point_id=point.id))
            
        except Exception as e:
            db.session.rollback()
            import traceback
            print(f"Error saving point: {str(e)}")
            print(traceback.format_exc())
            flash(f'Error saving point: {str(e)}', 'danger')
    else:
        # If form validation failed, print the errors
        if form.errors:
            print(f"DEBUG: Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field}: {error}", 'danger')
    
    return render_template('point/point_form.html',
                         form=form,
                         game=game,
                         title='Add Point',
                         completion_rate=calculate_completion_rate(game_id),
                         player_stats=player_stats,
                         all_players=all_players,
                         player_stats_dict=player_stats_dict)





@bp.route('/edit/<int:point_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_point(point_id):
    point = Point.query.get_or_404(point_id)
    game = Game.query.get(point.game_id)
    form = PointForm(obj=point)
    
    # Get all active players
    all_players = Player.query.filter_by(active=True).order_by(Player.jersey_number).all()
    
    # Get player stats
    player_stats = get_player_stats(game.id)
    
    # Create a dictionary for quick player stats lookup
    player_stats_dict = {}
    for stat in player_stats:
        if 'player_id' in stat:
            player_stats_dict[stat['player_id']] = stat
    
    # Pre-select players on GET request
    if request.method == 'GET':
        # Get the current lineup player IDs
        current_lineup_player_ids = [lineup.player_id for lineup in point.lineups]
        form.players.data = current_lineup_player_ids
        print(f"DEBUG: Pre-selected players: {current_lineup_player_ids}")
    
    # Process the player selection before form validation on POST
    if request.method == 'POST':
        # Get the selected players from the form data
        selected_players_str = request.form.get('players', '')
        print(f"DEBUG: Raw players field value: '{selected_players_str}'")
        
        if selected_players_str:
            try:
                # Convert comma-separated string to list of integers
                selected_players = [int(pid) for pid in selected_players_str.split(',') if pid]
                print(f"DEBUG: Selected players: {selected_players}")
                
                # Set the data directly
                form.players.data = selected_players
            except ValueError as e:
                print(f"DEBUG: Error converting player IDs: {e}")
                form.players.data = []
        else:
            print("DEBUG: No players selected in form data")
            # IMPORTANT: Instead of setting to empty list, keep the existing lineup
            form.players.data = [lineup.player_id for lineup in point.lineups]
    
    if form.validate_on_submit():
        point.point_number = form.point_number.data
        point.our_line_type = form.our_line_type.data
        point.our_score_before = form.our_score_before.data
        point.their_score_before = form.their_score_before.data
        point.starting_position = form.starting_position.data
        point.point_outcome = form.point_outcome.data
        point.duration = form.duration.data
        point.timestamp_in_video = form.timestamp_in_video.data
        
        # Calculate scores after point
        if form.point_outcome.data == 'scored':
            point.our_score_after = form.our_score_before.data + 1
            point.their_score_after = form.their_score_before.data
        else:
            point.our_score_after = form.our_score_before.data
            point.their_score_after = form.their_score_before.data + 1
        
        # IMPORTANT: Only update lineup if players were explicitly selected
        if form.players.data:
            # First, get the current lineup player IDs
            current_lineup_player_ids = [lineup.player_id for lineup in point.lineups]
            
            # Only update if the selection has changed
            if set(current_lineup_player_ids) != set(form.players.data):
                print(f"DEBUG: Updating lineup from {current_lineup_player_ids} to {form.players.data}")
                
                # Remove all existing lineups
                LineUp.query.filter_by(point_id=point.id).delete()
                
                # Then add the new ones
                for player_id in form.players.data:
                    lineup = LineUp(point_id=point.id, player_id=player_id)
                    db.session.add(lineup)
            else:
                print("DEBUG: Lineup unchanged, not updating")
        else:
            print("DEBUG: No players selected, keeping existing lineup")
        
        db.session.commit()
        
        flash(f'Point {point.point_number} has been updated!', 'success')
        return redirect(url_for('point.game_points', game_id=point.game_id))
    
    return render_template('point/point_form.html', 
                          form=form, 
                          game=game, 
                          point=point, 
                          title='Edit Point',
                          player_stats=player_stats,
                          all_players=all_players,
                          player_stats_dict=player_stats_dict)


@bp.route('/delete/<int:point_id>', methods=['POST'])
@login_required
def delete_point(point_id):
    point = Point.query.get_or_404(point_id)
    game_id = point.game_id
    point_number = point.point_number
    
    try:
        # First, get all event IDs for this point
        event_ids = [event.id for event in Event.query.filter_by(point_id=point.id).all()]
        
        # Delete throws that reference these events
        if event_ids:
            Throw.query.filter(Throw.throwing_event_id.in_(event_ids)).delete(synchronize_session=False)
            
        # Delete player_point_stats records
        PlayerPointStats.query.filter_by(point_id=point.id).delete()
        
        # Delete lineups
        LineUp.query.filter_by(point_id=point.id).delete()
        
        # Now it's safe to delete events
        Event.query.filter_by(point_id=point.id).delete()
        
        # Delete pulls
        Pull.query.filter_by(point_id=point.id).delete()
        
        # Delete the point
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
    point = Point.query.get_or_404(point_id)
    game = Game.query.get(point.game_id)
    
    # Get events
    from app.models.event import Event
    events = Event.query.filter_by(point_id=point_id).order_by(Event.timestamp).all()
    
    # Reorder events to ensure assists and hockey assists appear before goals
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
    
    # First add all non-goal/assist/hockey_assist events
    reordered_events.extend(other_events)
    
    # Then add hockey assists, assists, and goals in that order
    reordered_events.extend(hockey_assist_events)
    reordered_events.extend(assist_events)
    reordered_events.extend(goal_events)
    
    # Explicitly load lineups
    from app.models.point import LineUp
    lineups = LineUp.query.filter_by(point_id=point_id).all()
    
    # Create a serializable version of events for JavaScript
    events_data = []
    for event in reordered_events:  # Use reordered_events instead of events
        event_dict = {
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
        }
        events_data.append(event_dict)
    
    return render_template('point/point_detail.html', 
                          point=point, 
                          game=game, 
                          events=reordered_events,  # Use reordered_events here too
                          events_data=events_data,
                          lineups=lineups)




@bp.route('/fix_lineups/<int:point_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def fix_lineups(point_id):
    point = Point.query.get_or_404(point_id)
    
    if request.method == 'POST':
        # Get selected players
        player_ids = request.form.getlist('players')
        
        if len(player_ids) != 7:
            flash(f'You must select exactly 7 players. You selected {len(player_ids)}.', 'danger')
            return redirect(url_for('point.fix_lineups', point_id=point_id))
        
        # Delete existing lineups
        LineUp.query.filter_by(point_id=point_id).delete()
        
        # Add new lineups
        for player_id in player_ids:
            lineup = LineUp(point_id=point_id, player_id=player_id)
            db.session.add(lineup)
        
        db.session.commit()
        flash('Lineups have been updated!', 'success')
        return redirect(url_for('point.point_detail', point_id=point_id))
    
    # Get all active players
    all_players = Player.query.filter_by(active=True).order_by(Player.jersey_number).all()
    
    return render_template('point/fix_lineups.html', 
                          point=point, 
                          all_players=all_players)

