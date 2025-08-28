# app/utils/__init__.py
# Import utility functions but not models
from app.utils.utils import admin_required, coach_required, stat_taker_required

# Import stats functions from the new module
try:
    from app.utils.stats_utils import (
        calculate_throw_distance,
        is_break_throw,
        determine_possession,
        is_point_ending_event,
        calculate_player_stats,
        calculate_team_stats,
        calculate_player_game_stats,
        find_optimal_line,
        generate_field_heatmap_data,
        generate_player_connections
    )
except ImportError:
    # Handle the case where stats_utils might not be available yet
    import logging
    logging.warning("Could not import stats_utils functions")
