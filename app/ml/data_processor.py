# app/ml/data_processor.py

import pandas as pd
import numpy as np
from app.models.player import Player
from app.models.stats import Stats
from app.models.game import Game
from app.models.point import Point
from app.models.session import Session
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
        # Get player's recent game stats
        recent_stats = Stats.query.filter_by(player_id=player_id)\
            .join(Game, Stats.game_id == Game.id)\
            .order_by(Game.date.desc())\
            .limit(lookback_games).all()
            
        if not recent_stats:
            return None
            
        # Extract features from stats
        data = []
        for stat in recent_stats:
            game = Game.query.get(stat.game_id)
            
            # Basic game context
            game_data = {
                'game_id': game.id,
                'game_date': game.date,
                'opponent': game.opponent,
                'is_home': game.is_home if hasattr(game, 'is_home') else True,
                'tournament_game': game.tournament_id is not None,
                
                # Player stats - adjust these based on your actual Stats model
                'points_played': stat.points_played if hasattr(stat, 'points_played') else 0,
                'goals': stat.goals if hasattr(stat, 'goals') else 0,
                'assists': stat.assists if hasattr(stat, 'assists') else 0,
                'completions': stat.completions if hasattr(stat, 'completions') else 0,
                'throwaways': stat.throwaways if hasattr(stat, 'throwaways') else 0,
                'drops': stat.drops if hasattr(stat, 'drops') else 0,
                'blocks': stat.blocks if hasattr(stat, 'blocks') else 0,
            }
            
            # Add player attendance for recent practices
            game_date = game.date
            month_before = game_date - timedelta(days=30)
            
            # Get practice attendance in the month before the game
            attendance = Session.query.filter(
                Session.date.between(month_before, game_date)
            ).join(
                # This join will depend on how you track attendance
                # This is a placeholder - adjust based on your actual model relationships
                "attendance_table", 
                Session.id == "attendance_table.session_id"
            ).filter(
                "attendance_table.player_id" == player_id,
                "attendance_table.attended" == True
            ).count()
            
            game_data['recent_practices_attended'] = attendance
            
            data.append(game_data)
            
        return pd.DataFrame(data)
    
    @staticmethod
    def get_team_lineup_data(team_id, lookback_games=10):
        """
        Extract data about different line combinations and their effectiveness
        
        Args:
            team_id: ID of the team
            lookback_games: Number of past games to consider
            
        Returns:
            DataFrame with line combinations and performance metrics
        """
        # Get recent games
        recent_games = Game.query.filter_by(team_id=team_id)\
            .order_by(Game.date.desc())\
            .limit(lookback_games).all()
            
        if not recent_games:
            return None
            
        # Extract line combinations from points
        line_data = []
        for game in recent_games:
            points = Point.query.filter_by(game_id=game.id).all()
            
            for point in points:
                # This will depend on how you store lineups in your database
                # Assuming there's a relationship between Point and Player through a lineup table
                lineup = point.players if hasattr(point, 'players') else []
                
                if not lineup:
                    continue
                    
                # Create a sorted tuple of player IDs to represent this line
                line_key = tuple(sorted([player.id for player in lineup]))
                
                # Get point outcome
                point_data = {
                    'game_id': game.id,
                    'point_id': point.id,
                    'line_players': line_key,
                    'num_players': len(line_key),
                    'offense': point.line_type == 'offense' if hasattr(point, 'line_type') else None,
                    'point_scored': point.scored if hasattr(point, 'scored') else None,
                    'opponent': game.opponent,
                    'tournament_game': game.tournament_id is not None,
                }
                
                line_data.append(point_data)
                
        return pd.DataFrame(line_data)