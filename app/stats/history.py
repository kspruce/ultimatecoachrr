"""A player's game-by-game history (player page and history CSV)."""
from app.models.game import Game
from app.models.point import Point, LineUp
from app.utils.team_filter import get_current_team_id
from app.stats.cache import get_cached_team_averages
from app.stats.formulas import calculate_per
from app.stats.players import get_players_base_stats


def get_player_game_history(player, tournament_id, game_id):
    """Fetches and calculates stats for a player's game history."""
    player_games = []
    games_query = Game.query.filter_by(team_organization_id=get_current_team_id())
    if tournament_id:
        games_query = games_query.filter_by(tournament_id=tournament_id)
    elif game_id:
        games_query = games_query.filter_by(id=game_id)
    
    for game in games_query.order_by(Game.date.desc()).all():
        if LineUp.query.join(Point).filter(LineUp.player_id == player.id, Point.game_id == game.id).first():
            game_stats_dict = get_players_base_stats([player], [game])
            game_stats = game_stats_dict[player.id]
            game_team_avgs = get_cached_team_averages([game])
            game_stats['per'] = calculate_per(game_stats, game_team_avgs)
            player_games.append({'game': game, 'stats': game_stats})
            
    return player_games
