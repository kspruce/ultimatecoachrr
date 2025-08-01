# app/ml/data_processor.py

import pandas as pd
import numpy as np
from app.models.player import Player
from app.models.stats import PlayerPointStats  # Assuming this is the correct import
from app.models.game import Game
from app.models.point import Point
from app.models.session import SessionPlan, Attendance
from sqlalchemy import func
from flask import current_app
from datetime import datetime, timedelta

class DataProcessor:
    @staticmethod
    def get_player_historical_data(player_id, lookback_games=10):
        """
        Extract historical performance data for a specific player
        
        Args:
            player_id: ID of the player
            lookback_games: Number of past games to consider
            
        Returns:
            DataFrame with player stats and features
        """
        # Get player
        player = Player.query.get(player_id)
        if not player:
            return None
            
        # Get player's recent games through points
        recent_games = Game.query.join(Point).join(
            PlayerPointStats, Point.id == PlayerPointStats.point_id
        ).filter(
            PlayerPointStats.player_id == player_id
        ).order_by(Game.date.desc()).limit(lookback_games).all()
            
        if not recent_games:
            return None
            
        # Extract features from stats
        data = []
        for game in recent_games:
            # Get points for this game
            points = Point.query.filter_by(game_id=game.id).all()
            point_ids = [p.id for p in points]
            
            # Get player stats for these points
            player_stats = PlayerPointStats.query.filter(
                PlayerPointStats.player_id == player_id,
                PlayerPointStats.point_id.in_(point_ids)
            ).all()
            
            if not player_stats:
                continue
                
            # Get throws for this player in this game
            throws_made = player.throws_made.join(Point).filter(Point.game_id == game.id).all()
            completions = sum(1 for t in throws_made if t.is_completion)
            throwaways = sum(1 for t in throws_made if not t.is_completion)
            assists = sum(1 for t in throws_made if t.throw_type == 'assist')
            
            # Get receptions for this player in this game
            receptions = player.throws_received.join(Point).filter(Point.game_id == game.id).all()
            goals = sum(1 for r in receptions if r.throw_type == 'assist')
            
            # Calculate blocks (this depends on your data model)
            # For now, we'll use a placeholder
            blocks = 0  # Replace with actual calculation if you track blocks
            
            # Count points played
            points_played = len(player_stats)
            
            # Calculate PER metrics
            avg_per = sum(ps.calculated_per for ps in player_stats) / len(player_stats) if player_stats else 0
            
            # Basic game context
            game_data = {
                'game_id': game.id,
                'game_date': game.date,
                'opponent': game.opponent,
                'is_home': getattr(game, 'is_home', True),
                'tournament_game': getattr(game, 'tournament_id', None) is not None,
                
                # Player stats
                'points_played': points_played,
                'goals': goals,
                'assists': assists,
                'completions': completions,
                'throwaways': throwaways,
                'drops': 0,  # Replace with actual calculation if you track drops
                'blocks': blocks,
                'per': avg_per,
            }
            
            # Add player attendance for recent practices
            game_date = game.date
            month_before = game_date - timedelta(days=30)
            
            # Get practice attendance in the month before the game
            attendance_count = Attendance.query.join(SessionPlan).filter(
                SessionPlan.date.between(month_before, game_date),
                Attendance.player_id == player_id,
                Attendance.attended == True
            ).count()
            
            game_data['recent_practices_attended'] = attendance_count
            
            data.append(game_data)
            
        return pd.DataFrame(data)
    
    @staticmethod
    def get_team_lineup_data(team_name, lookback_games=10):
        """
        Extract data about different line combinations and their effectiveness
        
        Args:
            team_name: Name of the team
            lookback_games: Number of past games to consider
            
        Returns:
            DataFrame with line combinations and performance metrics
        """
        # Get recent games for the team
        recent_games = Game.query.filter_by(team=team_name)\
            .order_by(Game.date.desc())\
            .limit(lookback_games).all()
            
        if not recent_games:
            return None
            
        # Extract line combinations from points
        line_data = []
        for game in recent_games:
            points = Point.query.filter_by(game_id=game.id).all()
            
            for point in points:
                # Get players in this point through lineups
                lineups = point.lineups.all()
                players = [lineup.player for lineup in lineups if lineup.player]
                
                if not players:
                    continue
                    
                # Create a sorted tuple of player IDs to represent this line
                line_key = tuple(sorted([player.id for player in players]))
                
                # Get point outcome
                point_data = {
                    'game_id': game.id,
                    'point_id': point.id,
                    'line_players': line_key,
                    'num_players': len(line_key),
                    'offense': point.line_type == 'offense' if hasattr(point, 'line_type') else None,
                    'point_scored': point.scored if hasattr(point, 'scored') else None,
                    'opponent': game.opponent,
                    'tournament_game': hasattr(game, 'tournament_id') and game.tournament_id is not None,
                }
                
                line_data.append(point_data)
                
        return pd.DataFrame(line_data)