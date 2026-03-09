"""
PER Calculator Service
Provides efficient calculation and caching of Player Efficiency Ratings
"""
import time
from datetime import datetime
from flask import current_app
from app.models.player import Player
from app.models.game import Game

class PERCalculator:
    def __init__(self):
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_duration = 3600  # Cache duration in seconds (1 hour)
        self._debug_info = {}  # Store debug information for troubleshooting

    def _is_cache_valid(self, cache_key):
        """Check if the cache is still valid"""
        current_time = time.time()
        is_valid = (cache_key in self._cache and 
                   current_time - self._cache_timestamp < self._cache_duration)
        
        if current_app.debug:
            self._debug_info['cache_check'] = {
                'key': cache_key,
                'valid': is_valid,
                'current_time': datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S'),
                'cache_time': datetime.fromtimestamp(self._cache_timestamp).strftime('%Y-%m-%d %H:%M:%S') if self._cache_timestamp else 'None',
                'age': f"{(current_time - self._cache_timestamp) / 60:.1f} minutes" if self._cache_timestamp else 'N/A',
                'expires_in': f"{(self._cache_duration - (current_time - self._cache_timestamp)) / 60:.1f} minutes" if self._cache_timestamp else 'N/A'
            }
            
        return is_valid

    def _generate_cache_key(self, games=None):
        """Generate a unique cache key based on the games parameter"""
        cache_key = 'all_pers'
        if games:
            if isinstance(games, list):
                if games:
                    cache_key += '_games_' + '_'.join(str(g.id) for g in games)
                else:
                    cache_key += '_empty_games_list'
            else:
                cache_key += '_game_' + str(games.id)
        else:
            cache_key += '_all_games'
        return cache_key

    def calculate_all_pers(self, games=None, force_recalculate=False):
        """
        Calculate PER for all active players
        
        Args:
            games: Optional list of games or single game to filter stats
            force_recalculate: Force recalculation even if cache is valid
            
        Returns:
            Dictionary of {player_id: per_value}
        """
        # Import here to avoid circular imports
        from app.stats import get_player_base_stats, calculate_unadjusted_per, calculate_team_averages
        
        # Create a cache key based on the games parameter
        cache_key = self._generate_cache_key(games)
        
        # Return cached results if valid
        if not force_recalculate and self._is_cache_valid(cache_key):
            if current_app.debug:
                current_app.logger.debug(f"Using cached PER values for key: {cache_key}")
            return self._cache[cache_key]
            
        if current_app.debug:
            current_app.logger.debug(f"Calculating PER values for key: {cache_key}")
            calculation_start = time.time()
        
        # Get all active players
        players = Player.query.filter_by(active=True).all()
        
        # Calculate team averages
        team_avgs = calculate_team_averages(games)
        
        # Calculate raw PER for all players
        raw_pers = {}
        for player in players:
            stats = get_player_base_stats(player, games)
            if stats['points_played'] > 0:
                raw_per = calculate_unadjusted_per(stats)
                # Scale to league average of 15
                avg_uper = team_avgs.get('avg_uper', 1)
                if avg_uper <= 0:
                    avg_uper = 1
                scaled_per = raw_per * (15 / avg_uper)
                raw_pers[player.id] = scaled_per
        
        # Find the maximum PER
        max_per = max(raw_pers.values()) if raw_pers else 1
        
        # Scale all PERs relative to the maximum
        normalized_pers = {
            player_id: (per_value / max_per) * 100 
            for player_id, per_value in raw_pers.items()
        }
        
        # Cache the results
        self._cache[cache_key] = normalized_pers
        self._cache_timestamp = time.time()
        
        if current_app.debug:
            calculation_time = time.time() - calculation_start
            self._debug_info['last_calculation'] = {
                'key': cache_key,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'duration': f"{calculation_time:.3f} seconds",
                'player_count': len(normalized_pers),
                'max_per': max_per,
                'team_avgs': team_avgs
            }
            current_app.logger.debug(f"PER calculation completed in {calculation_time:.3f} seconds for {len(normalized_pers)} players")
        
        return normalized_pers
    
    def get_player_per(self, player_id, games=None, force_recalculate=False):
        """Get normalized PER for a specific player"""
        all_pers = self.calculate_all_pers(games, force_recalculate)
        return all_pers.get(player_id, 0)
    
    def clear_cache(self):
        """Clear the cache"""
        old_size = len(self._cache)
        self._cache = {}
        self._cache_timestamp = 0
        if current_app.debug:
            current_app.logger.debug(f"PER cache cleared. {old_size} entries removed.")
            self._debug_info['cache_cleared'] = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'entries_removed': old_size
            }
    
    def get_debug_info(self):
        """Get debug information about the cache"""
        cache_info = {
            'cache_size': len(self._cache),
            'cache_keys': list(self._cache.keys()),
            'cache_timestamp': datetime.fromtimestamp(self._cache_timestamp).strftime('%Y-%m-%d %H:%M:%S') if self._cache_timestamp else 'None',
            'cache_duration': f"{self._cache_duration / 60:.1f} minutes",
            'debug_info': self._debug_info
        }
        return cache_info

# Create a singleton instance
per_calculator = PERCalculator()
