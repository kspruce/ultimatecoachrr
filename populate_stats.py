# populate_stats.py
from app.models.base import db
from app import create_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.stats import PlayerStats, TeamStats
from app.utils.stats_calculator import get_players_base_stats, calculate_per_from_stats, calculate_team_averages
from app.utils.stats_calculator import calculate_team_summary, calculate_additional_team_metrics

app = create_app()
app.app_context().push()

def populate_all(team_organization_id=1):
    print("Deleting existing stats records...")
    PlayerStats.query.filter_by(team_organization_id=team_organization_id).delete()
    TeamStats.query.filter_by(team_organization_id=team_organization_id).delete()
    db.session.commit()

    print("Populating player stats...")
    players = Player.query.filter_by(team_organization_id=team_organization_id).all()
    
    # Get all games for this team
    games = Game.query.filter_by(team_organization_id=team_organization_id).all()
    
    # Calculate player stats in batch
    player_stats_dict = get_players_base_stats(players, games)
    
    # Calculate team averages
    team_avgs = calculate_team_averages(games)
    
    # Create PlayerStats records
    for player in players:
        print(f"  Processing {player.name}...")
        stats = player_stats_dict.get(player.id, {})
        
        if stats.get('points_played', 0) > 0:
            # Calculate PER using the stats calculator function directly
            per = calculate_per_from_stats(stats, team_avgs)
            
            # Create record
            record = PlayerStats(
                player_id=player.id,
                per=per,
                team_organization_id=team_organization_id,
                games_played=stats.get('games_played', 0),
                points_played=stats.get('points_played', 0),
                o_line_points_played=stats.get('o_line_points_played', 0),
                d_line_points_played=stats.get('d_line_points_played', 0),
                goals=stats.get('goals', 0),
                assists=stats.get('assists', 0),
                hockey_assists=stats.get('hockey_assists', 0),
                blocks=stats.get('blocks', 0),
                throws=stats.get('throws', 0),
                completions=stats.get('completions', 0),
                throwaways=stats.get('throwaways', 0),
                drops=stats.get('drops', 0),
                stalls=stats.get('stalls', 0),
                completion_rate=stats.get('completion_rate', 0),
                catch_rate=stats.get('catch_rate', 0),
                plus_minus=stats.get('plus_minus', 0),
                break_throws=stats.get('break_throws', 0)
            )
            db.session.add(record)
    
    # Create TeamStats record
    team_summary = calculate_team_summary(games)
    additional_metrics = calculate_additional_team_metrics(games)
    
    team_stats = TeamStats(
        team_organization_id=team_organization_id,
        games_played=team_summary.get('games_played', 0),
        wins=team_summary.get('wins', 0),
        losses=team_summary.get('losses', 0),
        ties=team_summary.get('ties', 0),
        total_points=team_summary.get('total_points', 0),
        o_line_points=team_summary.get('o_line_points', 0),
        o_line_conversions=team_summary.get('o_line_conversions', 0),
        d_line_points=team_summary.get('d_line_points', 0),
        d_line_conversions=team_summary.get('d_line_conversions', 0),
        breaks=team_summary.get('breaks', 0),
        holds=team_summary.get('holds', 0),
        win_percentage=team_summary.get('win_percentage', 0),
        o_line_conversion_rate=team_summary.get('o_line_conversion_rate', 0),
        d_line_conversion_rate=team_summary.get('d_line_conversion_rate', 0),
        completion_rate=additional_metrics.get('completion_rate', 0),
        goals_per_point=additional_metrics.get('goals_per_point', 0),
        assists_per_point=additional_metrics.get('assists_per_point', 0),
        throws_per_point=additional_metrics.get('throws_per_point', 0),
        hucks_per_point=additional_metrics.get('hucks_per_point', 0),
        blocks_per_point=additional_metrics.get('blocks_per_point', 0),
        turnovers_forced_per_point=additional_metrics.get('turnovers_forced_per_point', 0),
        defensive_efficiency=additional_metrics.get('defensive_efficiency', 0),
        break_percentage=additional_metrics.get('break_percentage', 0)
    )
    db.session.add(team_stats)
    
    # Commit all changes
    db.session.commit()
    print("Player stats populated.")

if __name__ == '__main__':
    import sys
    
    # Default to team_organization_id 1 if not specified
    team_id = 1
    if len(sys.argv) > 1:
        team_id = int(sys.argv[1])
    
    populate_all(team_id)
