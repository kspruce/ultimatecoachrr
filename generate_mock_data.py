# -*- coding: utf-8 -*-
"""
Created on Sat May 17 15:09:18 2025

@author: kspruce
"""

from app import create_app, db
from app.models.tournament import Tournament
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event, Pull
from app.models.player import Player
from datetime import datetime, date, timedelta
import random

def generate_mock_data():
    app = create_app()
    with app.app_context():
        # Check if we already have mock data
        if Tournament.query.filter_by(name='Mock Tournament').first():
            print("Mock data already exists. Skipping generation.")
            return
        
        print("Generating mock data...")
        
        # Create a tournament
        tournament = Tournament(
            name='Mock Tournament',
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() - timedelta(days=5),
            location='Mock City',
            season='2023'
        )
        db.session.add(tournament)
        db.session.commit()
        print(f"Created tournament: {tournament.name}")
        
        # Create a game
        game = Game(
            tournament_id=tournament.id,
            opponent='Mock Opponent',
            date=date.today() - timedelta(days=6),
            youtube_link='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            notes='This is a mock game for testing statistics'
        )
        db.session.add(game)
        db.session.commit()
        print(f"Created game against: {game.opponent}")
        
        # Get all active players
        players = Player.query.filter_by(active=True).all()
        if not players:
            print("No active players found. Please add players first.")
            return
        
        # Separate players by position and line preference
        o_line_handlers = [p for p in players if p.position == 'handler' and p.line_preference in ['O-line', 'both']]
        o_line_cutters = [p for p in players if p.position == 'cutter' and p.line_preference in ['O-line', 'both']]
        d_line_handlers = [p for p in players if p.position == 'handler' and p.line_preference in ['D-line', 'both']]
        d_line_cutters = [p for p in players if p.position == 'cutter' and p.line_preference in ['D-line', 'both']]
        
        # Ensure we have enough players
        if len(o_line_handlers) < 2 or len(o_line_cutters) < 3 or len(d_line_handlers) < 2 or len(d_line_cutters) < 3:
            print("Not enough players of each position/line preference. Adding generic players...")
            
            # Create generic players if needed
            positions = ['handler', 'cutter']
            line_prefs = ['O-line', 'D-line', 'both']
            
            for i in range(1, 15):
                if Player.query.filter_by(name=f'Mock Player {i}').first():
                    continue
                    
                position = positions[i % 2]
                line_pref = line_prefs[i % 3]
                
                player = Player(
                    name=f'Mock Player {i}',
                    position=position,
                    line_preference=line_pref,
                    jersey_number=i,
                    gender_match='male' if i % 2 == 0 else 'female',
                    active=True
                )
                db.session.add(player)
            
            db.session.commit()
            print("Added generic players")
            
            # Refresh player lists
            players = Player.query.filter_by(active=True).all()
            o_line_handlers = [p for p in players if p.position == 'handler' and p.line_preference in ['O-line', 'both']]
            o_line_cutters = [p for p in players if p.position == 'cutter' and p.line_preference in ['O-line', 'both']]
            d_line_handlers = [p for p in players if p.position == 'handler' and p.line_preference in ['D-line', 'both']]
            d_line_cutters = [p for p in players if p.position == 'cutter' and p.line_preference in ['D-line', 'both']]
        
        # Create points and events
        our_score = 0
        their_score = 0
        point_number = 1
        
        # Simulate a game to 15
        while our_score < 15 and their_score < 15:
            # Alternate starting on offense and defense
            starting_position = 'offense' if point_number % 2 == 1 else 'defense'
            our_line_type = 'O-line' if starting_position == 'offense' else 'D-line'
            
            # Select 7 players for the line
            if our_line_type == 'O-line':
                line_handlers = random.sample(o_line_handlers, min(3, len(o_line_handlers)))
                line_cutters = random.sample(o_line_cutters, min(4, len(o_line_cutters)))
            else:
                line_handlers = random.sample(d_line_handlers, min(3, len(d_line_handlers)))
                line_cutters = random.sample(d_line_cutters, min(4, len(d_line_cutters)))
            
            line_players = line_handlers + line_cutters
            if len(line_players) < 7:
                # Fill with any available players
                other_players = [p for p in players if p not in line_players]
                line_players.extend(random.sample(other_players, min(7 - len(line_players), len(other_players))))
            
            # Determine point outcome (slightly favor the offense)
            we_scored = random.random() < (0.6 if starting_position == 'offense' else 0.4)
            point_outcome = 'scored' if we_scored else 'conceded'
            
            # Update scores
            our_score_before = our_score
            their_score_before = their_score
            
            if we_scored:
                our_score += 1
            else:
                their_score += 1
            
            # Create point
            point = Point(
                game_id=game.id,
                point_number=point_number,
                our_line_type=our_line_type,
                our_score_before=our_score_before,
                their_score_before=their_score_before,
                our_score_after=our_score,
                their_score_after=their_score,
                starting_position=starting_position,
                point_outcome=point_outcome,
                duration=random.randint(30, 180),  # 30 seconds to 3 minutes
                timestamp_in_video=point_number * 180  # 3 minutes per point
            )
            db.session.add(point)
            db.session.commit()
            
            # Add players to lineup
            for player in line_players:
                lineup = LineUp(
                    point_id=point.id,
                    player_id=player.id
                )
                db.session.add(lineup)
            
            # Add pull if starting on defense
            if starting_position == 'defense':
                puller = random.choice(line_players)
                pull = Pull(
                    point_id=point.id,
                    player_id=puller.id,
                    is_inbounds=random.random() < 0.9  # 90% chance of in-bounds pull
                )
                db.session.add(pull)
            
            # Generate events for the point
            generate_point_events(point, line_players, we_scored)
            
            db.session.commit()
            print(f"Created point {point_number}: {our_score}-{their_score}")
            
            point_number += 1
        
        # Update final game score
        game.our_score = our_score
        game.their_score = their_score
        db.session.commit()
        
        print(f"Mock data generation complete. Final score: {our_score}-{their_score}")

def generate_point_events(point, players, we_scored):
    # Simulate events in a point
    # For simplicity, we'll create a basic flow:
    # 1. Series of throws/catches
    # 2. Either a score or a turnover
    # 3. If turnover, another series of throws/catches
    # 4. Final outcome
    
    # Field dimensions
    field_length = 100  # meters
    field_width = 37  # meters
    
    # Starting position
    current_x = 20 if point.starting_position == 'offense' else 80
    current_y = field_width / 2
    
    # Track current thrower/receiver
    current_players = random.sample(players, 2)
    current_thrower = current_players[0]
    current_receiver = current_players[1]
    
    # Track timestamp
    timestamp = 0
    
    # First possession
    possession_length = random.randint(3, 8)  # 3-8 throws
    
    # Direction of play (1 = towards endzone, -1 = away from endzone)
    direction = 1 if point.starting_position == 'offense' else -1
    target_x = 95 if direction == 1 else 5
    
    # Generate events for first possession
    for i in range(possession_length):
        # Determine if this is the last throw in possession
        is_last_throw = i == possession_length - 1
        
        # Calculate new position
        new_x = current_x + direction * random.randint(5, 15)
        new_y = max(5, min(field_width - 5, current_y + random.uniform(-5, 5)))
        
        # Ensure we don't go out of bounds or past endzone
        new_x = max(5, min(95, new_x))
        
        # Create throw event
        throw_type = random.choice(['backhand', 'forehand', 'hammer', 'scoober'])
        force_direction = random.choice(['forehand', 'backhand', 'no_force'])
        
        throw_event = Event(
            point_id=point.id,
            event_type='throw' if not is_last_throw else 'assist',
            player_id=current_thrower.id,
            field_position_x=current_x,
            field_position_y=current_y,
            throw_type=throw_type,
            force_direction=force_direction,
            receiver_id=current_receiver.id,
            timestamp=timestamp
        )
        
        # Calculate if it's a break throw
        if throw_type and force_direction:
            if (throw_type == 'backhand' and force_direction == 'forehand') or \
               (throw_type == 'forehand' and force_direction == 'backhand'):
                throw_event.is_break_throw = True
        
        db.session.add(throw_event)
        timestamp += random.randint(2, 5)
        
        # Create catch/goal event
        catch_event = Event(
            point_id=point.id,
            event_type='catch' if not is_last_throw else 'goal',
            player_id=current_receiver.id,
            field_position_x=new_x,
            field_position_y=new_y,
            timestamp=timestamp
        )
        db.session.add(catch_event)
        timestamp += random.randint(1, 3)
        
        # Update positions and players
        current_x, current_y = new_x, new_y
        current_thrower, current_receiver = current_receiver, random.choice([p for p in players if p != current_receiver])
        
        # If we're close to the endzone and it's the last throw, make it a goal
        if is_last_throw and ((direction == 1 and new_x >= 90) or (direction == -1 and new_x <= 10)):
            # We scored!
            if (point.starting_position == 'offense' and we_scored) or \
               (point.starting_position == 'defense' and not we_scored):
                break
        
    # If the point outcome doesn't match the first possession, simulate a turnover and second possession
    if (point.starting_position == 'offense' and not we_scored) or \
       (point.starting_position == 'defense' and we_scored):
        
        # Create turnover event
        turnover_type = random.choice(['throwaway', 'drop', 'block'])
        
        if turnover_type == 'throwaway':
            # Throwaway
            new_x = current_x + direction * random.randint(5, 15)
            new_y = max(5, min(field_width - 5, current_y + random.uniform(-5, 5)))
            
            turnover_event = Event(
                point_id=point.id,
                event_type='throwaway',
                player_id=current_thrower.id,
                field_position_x=current_x,
                field_position_y=current_y,
                throw_type=random.choice(['backhand', 'forehand', 'hammer', 'scoober']),
                timestamp=timestamp
            )
            db.session.add(turnover_event)
            
        elif turnover_type == 'drop':
            # Drop
            new_x = current_x + direction * random.randint(5, 15)
            new_y = max(5, min(field_width - 5, current_y + random.uniform(-5, 5)))
            
            throw_event = Event(
                point_id=point.id,
                event_type='throw',
                player_id=current_thrower.id,
                field_position_x=current_x,
                field_position_y=current_y,
                throw_type=random.choice(['backhand', 'forehand', 'hammer', 'scoober']),
                receiver_id=current_receiver.id,
                timestamp=timestamp
            )
            db.session.add(throw_event)
            timestamp += random.randint(2, 5)
            
            drop_event = Event(
                point_id=point.id,
                event_type='drop',
                player_id=current_receiver.id,
                field_position_x=new_x,
                field_position_y=new_y,
                timestamp=timestamp
            )
            db.session.add(drop_event)
            
        else:
            # Block
            new_x = current_x + direction * random.randint(5, 15)
            new_y = max(5, min(field_width - 5, current_y + random.uniform(-5, 5)))
            
            throw_event = Event(
                point_id=point.id,
                event_type='throw',
                player_id=current_thrower.id,
                field_position_x=current_x,
                field_position_y=current_y,
                throw_type=random.choice(['backhand', 'forehand', 'hammer', 'scoober']),
                receiver_id=current_receiver.id,
                timestamp=timestamp
            )
            db.session.add(throw_event)
            timestamp += random.randint(2, 5)
            
            # Pick a defender
            defender = random.choice([p for p in players if p != current_receiver])
            
            block_event = Event(
                point_id=point.id,
                event_type='block',
                player_id=defender.id,
                field_position_x=new_x,
                field_position_y=new_y,
                timestamp=timestamp
            )
            db.session.add(block_event)
        
        timestamp += random.randint(3, 8)
        
        # Switch direction for second possession
        direction *= -1
        target_x = 95 if direction == 1 else 5
        
        # Reset players for second possession
        current_players = random.sample(players, 2)
        current_thrower = current_players[0]
        current_receiver = current_players[1]
        
        # Second possession
        possession_length = random.randint(2, 6)  # 2-6 throws
        
        # Generate events for second possession
        for i in range(possession_length):
            # Determine if this is the last throw in possession
            is_last_throw = i == possession_length - 1
            
            # Calculate new position
            new_x = current_x + direction * random.randint(5, 15)
            new_y = max(5, min(field_width - 5, current_y + random.uniform(-5, 5)))
            
            # Ensure we don't go out of bounds or past endzone
            new_x = max(5, min(95, new_x))
            
            # Create throw event
            throw_type = random.choice(['backhand', 'forehand', 'hammer', 'scoober'])
            force_direction = random.choice(['forehand', 'backhand', 'no_force'])
            
            throw_event = Event(
                point_id=point.id,
                event_type='throw' if not is_last_throw else 'assist',
                player_id=current_thrower.id,
                field_position_x=current_x,
                field_position_y=current_y,
                throw_type=throw_type,
                force_direction=force_direction,
                receiver_id=current_receiver.id,
                timestamp=timestamp
            )
            
            # Calculate if it's a break throw
            if throw_type and force_direction:
                if (throw_type == 'backhand' and force_direction == 'forehand') or \
                   (throw_type == 'forehand' and force_direction == 'backhand'):
                    throw_event.is_break_throw = True
            
            db.session.add(throw_event)
            timestamp += random.randint(2, 5)
            
            # Create catch/goal event
            catch_event = Event(
                point_id=point.id,
                event_type='catch' if not is_last_throw else 'goal',
                player_id=current_receiver.id,
                field_position_x=new_x,
                field_position_y=new_y,
                timestamp=timestamp
            )
            db.session.add(catch_event)
            timestamp += random.randint(1, 3)
            
            # Update positions and players
            current_x, current_y = new_x, new_y
            current_thrower, current_receiver = current_receiver, random.choice([p for p in players if p != current_receiver])

if __name__ == '__main__':
    generate_mock_data()
