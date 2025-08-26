from app_factory import db
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, not_
from app.models.stats_cache import PlayerStatsCache, TeamStatsCache, GameStatsCache
from app.models.player import Player
from app.models.game import Game
from app.models.point import Point, LineUp
from app.models.event import Event
from app.models.throws import Throw
from app.models.stats import PlayerPointStats
import math

class StatsService:
    """
    Service class for calculating and managing statistics.
    This class provides methods for calculating statistics and managing the cache.
    """
    
    @staticmethod
    def calculate_offensive_efficiency(points):
        """
        Calculate offensive efficiency: (points scored / points played) * 100
        
        Args:
            points: List of Point objects
            
        Returns:
            float: Offensive efficiency as a percentage
        """
        if not points:
            return 0.0
            
        o_points = [p for p in points if p.our_line_type == 'O-line']
        if not o_points:
            return 0.0
            
        scored = sum(1 for p in o_points if p.point_outcome == 'scored')
        return (scored / len(o_points)) * 100
    
    @staticmethod
    def calculate_defensive_efficiency(points):
        """
        Calculate defensive efficiency: (points where opponent didn't score / points played) * 100
        
        Args:
            points: List of Point objects
            
        Returns:
            float: Defensive efficiency as a percentage
        """
        if not points:
            return 0.0
            
        d_points = [p for p in points if p.our_line_type == 'D-line']
        if not d_points:
            return 0.0
            
        # Defensive efficiency is the percentage of points where the opponent didn't score
        not_conceded = sum(1 for p in d_points if p.point_outcome != 'conceded')
        return (not_conceded / len(d_points)) * 100
    
    @staticmethod
    def calculate_player_per(player, team_stats, start_date=None, end_date=None):
        """
        Calculate Player Efficiency Rating (PER)
        
        Args:
            player: Player object
            team_stats: Dictionary containing team average statistics
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            float: PER value
        """
        # Get player events with optional date filtering
        query = player.player_events
        if start_date or end_date:
            query = query.join(Event.point).join(Game, Point.game_id == Game.id)
            if start_date:
                query = query.filter(Game.date >= start_date)
            if end_date:
                query = query.filter(Game.date <= end_date)

            
        # Calculate basic stats
        goals = query.filter_by(event_type='goal').count()
        assists = query.filter_by(event_type='assist').count()
        turnovers = query.filter_by(event_type='turnover').count()
        blocks = query.filter_by(event_type='block').count()
        
        # Get throws data
        throws_query = db.session.query(Throw).filter_by(team_organization_id=team_organization_id)
        if start_date or end_date:
            throws_query = throws_query.join(Throw.point).join(Game, Point.game_id == Game.id)
            if start_date:
                throws_query = throws_query.filter(Game.date >= start_date)
            if end_date:
                throws_query = throws_query.filter(Game.date <= end_date)
                
        completions = throws_query.filter_by(is_completion=True).count()
        throw_attempts = throws_query.count()
        
        # Calculate completion percentage
        completion_pct = (completions / throw_attempts * 100) if throw_attempts > 0 else 0
        
        # Get player's plus/minus from PlayerPointStats
        query = db.session.query(func.sum(PlayerPointStats.o_line_plus_minus), 
                               func.sum(PlayerPointStats.d_line_plus_minus))
        query = query.filter(PlayerPointStats.player_id == player.id)
        
        if start_date or end_date:
            query = query.join(PlayerPointStats.point)
            if start_date:
                query = query.filter(Game.date>= start_date)
            if end_date:
                query = query.filter(Game.date<= end_date)
                
        o_plus_minus, d_plus_minus = query.first()
        o_plus_minus = o_plus_minus or 0
        d_plus_minus = d_plus_minus or 0
        
        # Calculate PER using a weighted formula
        # This is a simplified version - adjust weights based on your specific needs
        per = (
            (goals * 1.5) + 
            (assists * 1.2) + 
            (blocks * 1.4) - 
            (turnovers * 1.0) + 
            ((completion_pct - team_stats.get('avg_completion_pct', 0)) * 0.05) +
            (o_plus_minus * 0.8) + 
            (d_plus_minus * 0.8)
        )
        
        # Normalize PER to a 0-100 scale
        # This is a simple normalization - adjust based on your data distribution
        normalized_per = min(max(per * 5 + 50, 0), 100)
        
        return normalized_per
    
    @classmethod
    def update_player_stats_cache(cls, player, team_organization_id, start_date=None, end_date=None):
        """
        Calculate and update the cache for a player's statistics
        
        Args:
            player: Player object
            team_organization_id: ID of the team organization
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            PlayerStatsCache: Updated cache object
        """
        # Find existing cache or create new one
        cache = PlayerStatsCache.query.filter_by(
            player_id=player.id,
            team_organization_id=team_organization_id,
            start_date=start_date,
            end_date=end_date
        ).first()
        
        if not cache:
            cache = PlayerStatsCache(
                player_id=player.id,
                team_organization_id=team_organization_id,
                start_date=start_date,
                end_date=end_date
            )
        
        # Get points played by the player
        points_query = db.session.query(Point).join(LineUp).filter(LineUp.player_id == player.id)
        
        # If date filtering is needed, join with Game which has the date
        if start_date or end_date:
            points_query = points_query.join(Game, Point.game_id == Game.id)
            if start_date:
                points_query = points_query.filter(Game.date >= start_date)
            if end_date:
                points_query = points_query.filter(Game.date <= end_date)
            
        points = points_query.all()
        
        # Calculate basic stats
        cache.points_played = len(points)
        cache.o_line_points_played = sum(1 for p in points if p.our_line_type == 'O-line')
        cache.d_line_points_played = sum(1 for p in points if p.our_line_type == 'D-line')
        
        # Calculate efficiency stats
        o_line_points = [p for p in points if p.our_line_type == 'O-line']
        d_line_points = [p for p in points if p.our_line_type == 'D-line']
        
        if o_line_points:
            o_scored = sum(1 for p in o_line_points if p.point_outcome == 'scored')
            cache.o_line_efficiency = o_scored / len(o_line_points)
        else:
            cache.o_line_efficiency = 0.0
            
        if d_line_points:
            d_not_conceded = sum(1 for p in d_line_points if p.point_outcome != 'conceded')
            cache.d_line_efficiency = d_not_conceded / len(d_line_points)
        else:
            cache.d_line_efficiency = 0.0
        
        # Get throw stats
        throws_query = player.throws_made
        if start_date or end_date:
            throws_query = throws_query.join(Throw.point)
            if start_date:
                throws_query = throws_query.filter(Game.date>= start_date)
            if end_date:
                throws_query = throws_query.filter(Game.date<= end_date)
        if team_organization_id:
            throws_query = throws_query.filter(Throw.team_organization_id == team_organization_id)
            
        cache.completions = throws_query.filter_by(is_completion=True).count()
        cache.throw_attempts = throws_query.count()
        
        # Get scoring stats
        events_query = player.player_events
        if start_date or end_date:
            events_query = events_query.join(Event.point)
            if start_date:
                events_query = events_query.filter(Game.date>= start_date)
            if end_date:
                events_query = events_query.filter(Game.date<= end_date)
        if team_organization_id:
            events_query = events_query.filter(Event.team_organization_id == team_organization_id)
            
        cache.goals = events_query.filter_by(event_type='goal').count()
        cache.assists = events_query.filter_by(event_type='assist').count()
        cache.blocks = events_query.filter_by(event_type='block').count()
        
        # Get plus/minus from PlayerPointStats
        plus_minus_query = db.session.query(
            func.sum(PlayerPointStats.o_line_plus_minus).label('o_plus_minus'),
            func.sum(PlayerPointStats.d_line_plus_minus).label('d_plus_minus')
        ).filter(PlayerPointStats.player_id == player.id)
        
        if start_date or end_date:
            plus_minus_query = plus_minus_query.join(PlayerPointStats.point)
            if start_date:
                plus_minus_query = plus_minus_query.filter(Game.date>= start_date)
            if end_date:
                plus_minus_query = plus_minus_query.filter(Game.date<= end_date)
        if team_organization_id:
            plus_minus_query = plus_minus_query.filter(PlayerPointStats.team_organization_id == team_organization_id)
            
        result = plus_minus_query.first()
        cache.o_line_plus_minus = result.o_plus_minus or 0.0
        cache.d_line_plus_minus = result.d_plus_minus or 0.0
        
        # Get team stats for PER calculation
        team_stats = cls.get_team_stats_summary(team_organization_id, start_date, end_date)
        
        # Calculate PER
        cache.per = cls.calculate_player_per(player, team_stats, start_date, end_date)
        
        # Save to database
        db.session.add(cache)
        db.session.commit()
        
        return cache
    
    @classmethod
    def update_team_stats_cache(cls, team_organization_id, start_date=None, end_date=None):
        """
        Calculate and update the cache for a team's statistics
        
        Args:
            team_organization_id: ID of the team organization
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            TeamStatsCache: Updated cache object
        """
        # Don't proceed if team_organization_id is None
        if team_organization_id is None:
            return None
        # Find existing cache or create new one
        cache = TeamStatsCache.query.filter_by(
            team_organization_id=team_organization_id,
            start_date=start_date,
            end_date=end_date
        ).first()
        
        if not cache:
            cache = TeamStatsCache(
                team_organization_id=team_organization_id,
                start_date=start_date,
                end_date=end_date
            )
        
        # Get points for the team
        points_query = Point.query.filter_by(team_organization_id=team_organization_id)
        if start_date or end_date:
            points_query = points_query.join(Game, Point.game_id == Game.id)
            if start_date:
                points_query = points_query.filter(Game.date >= start_date)
            if end_date:
                points_query = points_query.filter(Game.date <= end_date)
            
        points = points_query.all()
        
        # Calculate offensive stats
        o_points = [p for p in points if p.our_line_type == 'O-line']
        if o_points:
            o_scored = sum(1 for p in o_points if p.point_outcome == 'scored')
            cache.o_line_conversion_rate = (o_scored / len(o_points)) * 100
            cache.o_line_efficiency = (o_scored / len(o_points)) * 100  # Same as conversion rate for team
        else:
            cache.o_line_conversion_rate = 0.0
            cache.o_line_efficiency = 0.0
        
        # Calculate defensive stats
        d_points = [p for p in points if p.our_line_type == 'D-line']
        if d_points:
            d_scored = sum(1 for p in d_points if p.point_outcome == 'scored')
            cache.d_line_conversion_rate = (d_scored / len(d_points)) * 100
            
            # Defensive efficiency: percentage of points where opponent didn't score
            d_not_conceded = sum(1 for p in d_points if p.point_outcome != 'conceded')
            cache.d_line_efficiency = (d_not_conceded / len(d_points)) * 100
            cache.defensive_efficiency = (d_not_conceded / len(d_points)) * 100  # Same as d_line_efficiency
        else:
            cache.d_line_conversion_rate = 0.0
            cache.d_line_efficiency = 0.0
            cache.defensive_efficiency = 0.0
        
        # Calculate break percentage
        if points:
            breaks = sum(1 for p in points if p.is_break)
            cache.break_percentage = (breaks / len(points)) * 100
        else:
            cache.break_percentage = 0.0
        
        # Calculate blocks per point
        events_query = Event.query.filter_by(
            event_type='block',
            team_organization_id=team_organization_id
        )
        if start_date or end_date:
            events_query = events_query.join(Event.point)
            if start_date:
                events_query = events_query.filter(Game.date>= start_date)
            if end_date:
                events_query = events_query.filter(Game.date<= end_date)
                
        blocks = events_query.count()
        cache.blocks_per_point = blocks / len(points) if points else 0.0
        
        # Calculate turnovers forced per point
        events_query = Event.query.filter_by(
            event_type='turnover',
            team_organization_id=team_organization_id
        )
        if start_date or end_date:
            events_query = events_query.join(Event.point)
            if start_date:
                events_query = events_query.filter(Game.date>= start_date)
            if end_date:
                events_query = events_query.filter(Game.date<= end_date)
                
        turnovers_forced = events_query.count()
        cache.turnovers_forced_per_point = turnovers_forced / len(points) if points else 0.0
        
        # Save to database
        db.session.add(cache)
        db.session.commit()
        
        return cache
    
    @classmethod
    def update_game_stats_cache(cls, game_id):
        """
        Calculate and update the cache for a game's statistics
        
        Args:
            game_id: ID of the game
            
        Returns:
            GameStatsCache: Updated cache object
        """
        # Find existing cache or create new one
        cache = GameStatsCache.query.filter_by(game_id=game_id).first()
        
        if not cache:
            game = Game.query.get(game_id)
            if not game:
                return None
                
            cache = GameStatsCache(
                game_id=game_id,
                team_organization_id=game.team_organization_id
            )
        
        # Get points for the game
        points = Point.query.filter_by(game_id=game_id).all()
        
        # Calculate offensive stats
        o_points = [p for p in points if p.our_line_type == 'O-line']
        if o_points:
            o_scored = sum(1 for p in o_points if p.point_outcome == 'scored')
            cache.o_line_conversion_rate = (o_scored / len(o_points)) * 100
            cache.o_line_efficiency = (o_scored / len(o_points)) * 100  # Same as conversion rate for game
        else:
            cache.o_line_conversion_rate = 0.0
            cache.o_line_efficiency = 0.0
        
        # Calculate defensive stats
        d_points = [p for p in points if p.our_line_type == 'D-line']
        if d_points:
            d_scored = sum(1 for p in d_points if p.point_outcome == 'scored')
            cache.d_line_conversion_rate = (d_scored / len(d_points)) * 100
            
            # Defensive efficiency: percentage of points where opponent didn't score
            d_not_conceded = sum(1 for p in d_points if p.point_outcome != 'conceded')
            cache.d_line_efficiency = (d_not_conceded / len(d_points)) * 100
        else:
            cache.d_line_conversion_rate = 0.0
            cache.d_line_efficiency = 0.0
        
        # Save to database
        db.session.add(cache)
        db.session.commit()
        
        return cache
    
    @staticmethod
    def get_player_stats(player_id, team_organization_id=None, start_date=None, end_date=None, use_cache=True):
        """
        Get statistics for a player, either from cache or by calculating them
        
        Args:
            player_id: ID of the player
            team_organization_id: Optional ID of the team organization
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            use_cache: Whether to use cached values if available
            
        Returns:
            dict: Player statistics
        """
        if use_cache:
            # Try to get from cache first
            cache = PlayerStatsCache.query.filter_by(
                player_id=player_id,
                team_organization_id=team_organization_id,
                start_date=start_date,
                end_date=end_date
            ).first()
            
            if cache:
                # Convert cache object to dictionary
                return {
                    'points_played': cache.points_played,
                    'o_line_points_played': cache.o_line_points_played,
                    'd_line_points_played': cache.d_line_points_played,
                    'o_line_efficiency': cache.o_line_efficiency,
                    'd_line_efficiency': cache.d_line_efficiency,
                    'per': cache.per,
                    'o_line_plus_minus': cache.o_line_plus_minus,
                    'd_line_plus_minus': cache.d_line_plus_minus,
                    'completions': cache.completions,
                    'throw_attempts': cache.throw_attempts,
                    'completion_percentage': cache.completion_percentage,
                    'goals': cache.goals,
                    'assists': cache.assists,
                    'blocks': cache.blocks
                }
        
        # If not using cache or cache not found, calculate and update cache
        player = Player.query.get(player_id)
        if not player:
            return {}
            
        cache = StatsService.update_player_stats_cache(
            player, 
            team_organization_id, 
            start_date, 
            end_date
        )
        
        # Convert cache object to dictionary
        return {
            'points_played': cache.points_played,
            'o_line_points_played': cache.o_line_points_played,
            'd_line_points_played': cache.d_line_points_played,
            'o_line_efficiency': cache.o_line_efficiency,
            'd_line_efficiency': cache.d_line_efficiency,
            'per': cache.per,
            'o_line_plus_minus': cache.o_line_plus_minus,
            'd_line_plus_minus': cache.d_line_plus_minus,
            'completions': cache.completions,
            'throw_attempts': cache.throw_attempts,
            'completion_percentage': cache.completion_percentage,
            'goals': cache.goals,
            'assists': cache.assists,
            'blocks': cache.blocks
        }
    
    @staticmethod
    def get_team_stats(team_organization_id, start_date=None, end_date=None, use_cache=True):
        """
        Get statistics for a team, either from cache or by calculating them
        
        Args:
            team_organization_id: ID of the team organization
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            use_cache: Whether to use cached values if available
            
        Returns:
            dict: Team statistics
        """
        # Return empty stats if team_organization_id is None
        if team_organization_id is None:
            return {
                'o_line_conversion_rate': 0.0,
                'o_line_efficiency': 0.0,
                'd_line_conversion_rate': 0.0,
                'd_line_efficiency': 0.0,
                'defensive_efficiency': 0.0,
                'break_percentage': 0.0,
                'blocks_per_point': 0.0,
                'turnovers_forced_per_point': 0.0
            }
        
        if use_cache:
            # Try to get from cache first
            cache = TeamStatsCache.query.filter_by(
                team_organization_id=team_organization_id,
                start_date=start_date,
                end_date=end_date
            ).first()
            
            if cache:
                # Convert cache object to dictionary
                return {
                    'o_line_conversion_rate': cache.o_line_conversion_rate,
                    'o_line_efficiency': cache.o_line_efficiency,
                    'd_line_conversion_rate': cache.d_line_conversion_rate,
                    'd_line_efficiency': cache.d_line_efficiency,
                    'defensive_efficiency': cache.defensive_efficiency,
                    'break_percentage': cache.break_percentage,
                    'blocks_per_point': cache.blocks_per_point,
                    'turnovers_forced_per_point': cache.turnovers_forced_per_point
                }
        
        # If not using cache or cache not found, calculate and update cache
        cache = StatsService.update_team_stats_cache(
            team_organization_id, 
            start_date, 
            end_date
        )
        
        if not cache:
            return {
                'o_line_conversion_rate': 0.0,
                'o_line_efficiency': 0.0,
                'd_line_conversion_rate': 0.0,
                'd_line_efficiency': 0.0,
                'defensive_efficiency': 0.0,
                'break_percentage': 0.0,
                'blocks_per_point': 0.0,
                'turnovers_forced_per_point': 0.0
            }
        
        # Convert cache object to dictionary
        return {
            'o_line_conversion_rate': cache.o_line_conversion_rate,
            'o_line_efficiency': cache.o_line_efficiency,
            'd_line_conversion_rate': cache.d_line_conversion_rate,
            'd_line_efficiency': cache.d_line_efficiency,
            'defensive_efficiency': cache.defensive_efficiency,
            'break_percentage': cache.break_percentage,
            'blocks_per_point': cache.blocks_per_point,
            'turnovers_forced_per_point': cache.turnovers_forced_per_point
        }

    
    @staticmethod
    def get_game_stats(game_id, use_cache=True):
        """
        Get statistics for a game, either from cache or by calculating them
        
        Args:
            game_id: ID of the game
            use_cache: Whether to use cached values if available
            
        Returns:
            dict: Game statistics
        """
        if use_cache:
            # Try to get from cache first
            cache = GameStatsCache.query.filter_by(game_id=game_id).first()
            
            if cache:
                # Convert cache object to dictionary
                return {
                    'o_line_conversion_rate': cache.o_line_conversion_rate,
                    'd_line_conversion_rate': cache.d_line_conversion_rate,
                    'o_line_efficiency': cache.o_line_efficiency,
                    'd_line_efficiency': cache.d_line_efficiency
                }
        
        # If not using cache or cache not found, calculate and update cache
        cache = StatsService.update_game_stats_cache(game_id)
        
        if not cache:
            return {}
            
        # Convert cache object to dictionary
        return {
            'o_line_conversion_rate': cache.o_line_conversion_rate,
            'd_line_conversion_rate': cache.d_line_conversion_rate,
            'o_line_efficiency': cache.o_line_efficiency,
            'd_line_efficiency': cache.d_line_efficiency
        }
    
    @staticmethod
    def get_team_stats_summary(team_organization_id, start_date=None, end_date=None):
        """
        Get a summary of team statistics for use in calculations
        
        Args:
            team_organization_id: ID of the team organization
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            dict: Team statistics summary
        """
        # Get team stats
        team_stats = StatsService.get_team_stats(team_organization_id, start_date, end_date)
        
        # Calculate average completion percentage for the team
        throws_query = db.session.query(Throw).filter_by(team_organization_id=team_organization_id)
        if start_date or end_date:
            throws_query = throws_query.join(Throw.point).join(Game, Point.game_id == Game.id)
            if start_date:
                throws_query = throws_query.filter(Game.date >= start_date)
            if end_date:
                throws_query = throws_query.filter(Game.date <= end_date)
                
        completions = throws_query.filter_by(is_completion=True).count()

        throw_attempts = throws_query.count()
        avg_completion_pct = (completions / throw_attempts * 100) if throw_attempts > 0 else 0
        
        # Add to team stats
        team_stats['avg_completion_pct'] = avg_completion_pct
        
        return team_stats
    
    @staticmethod
    def invalidate_cache(player_id=None, team_organization_id=None, game_id=None):
        """
        Invalidate cache entries based on provided parameters
        
        Args:
            player_id: Optional ID of the player
            team_organization_id: Optional ID of the team organization
            game_id: Optional ID of the game
            
        Returns:
            int: Number of cache entries invalidated
        """
        count = 0
        
        # Invalidate player stats cache
        if player_id:
            query = PlayerStatsCache.query.filter_by(player_id=player_id)
            if team_organization_id:
                query = query.filter_by(team_organization_id=team_organization_id)
            count += query.delete()
        
        # Invalidate team stats cache
        if team_organization_id:
            count += TeamStatsCache.query.filter_by(team_organization_id=team_organization_id).delete()
        
        # Invalidate game stats cache
        if game_id:
            count += GameStatsCache.query.filter_by(game_id=game_id).delete()
        
        # Commit changes
        db.session.commit()
        
        return count
    
    @staticmethod
    def update_cache_after_event(event_type, entity_id):
        """
        Update cache after an event occurs
        
        Args:
            event_type: Type of event (point, game, player, throw)
            entity_id: ID of the entity
            
        Returns:
            bool: True if cache was updated, False otherwise
        """
        if event_type == 'point':
            # Get point
            point = Point.query.get(entity_id)
            if not point:
                return False
                
            # Invalidate game stats cache
            StatsService.invalidate_cache(game_id=point.game_id)
            
            # Invalidate team stats cache
            if point.team_organization_id:
                StatsService.invalidate_cache(team_organization_id=point.team_organization_id)
            
            # Invalidate player stats cache for all players in the point
            for lineup in point.lineups:
                StatsService.invalidate_cache(player_id=lineup.player_id)
                
            return True
            
        elif event_type == 'game':
            # Get game
            game = Game.query.get(entity_id)
            if not game:
                return False
                
            # Invalidate game stats cache
            StatsService.invalidate_cache(game_id=game.id)
            
            # Invalidate team stats cache
            if game.team_organization_id:
                StatsService.invalidate_cache(team_organization_id=game.team_organization_id)
            
            # Invalidate player stats cache for all players in the game
            for player in game.assigned_players:
                StatsService.invalidate_cache(player_id=player.player_id)
                
            return True
            
        elif event_type == 'player':
            # Invalidate player stats cache
            StatsService.invalidate_cache(player_id=entity_id)
            return True
            
        elif event_type == 'throw':
            # Get throw
            throw = Throw.query.get(entity_id)
            if not throw:
                return False
                
            # Invalidate player stats cache for thrower and receiver
            if throw.thrower_id:
                StatsService.invalidate_cache(player_id=throw.thrower_id)
            if throw.receiver_id:
                StatsService.invalidate_cache(player_id=throw.receiver_id)
                
            # Invalidate team stats cache
            if throw.team_organization_id:
                StatsService.invalidate_cache(team_organization_id=throw.team_organization_id)
                
            return True
            
        return False