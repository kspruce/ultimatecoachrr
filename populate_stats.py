# Import db from models.base instead of from app
from app.models.base import db
from app import create_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.stats import PlayerStats, TeamStats

app = create_app()
app.app_context().push()

def populate_all(team_organization_id=1):  # Add parameter with default value
    # Now import the stats functions inside the function to avoid circular imports
    from app.routes.stats import get_player_base_stats, calculate_team_summary, calculate_per, calculate_team_averages
    from app.utils.stats_calculator import get_players_base_stats, calculate_team_averages as calc_team_avgs
    
    print("Deleting existing stats records...")
    PlayerStats.query.filter_by(team_organization_id=team_organization_id).delete()
    TeamStats.query.filter_by(team_organization_id=team_organization_id).delete()
    db.session.commit()

    print("Populating player stats...")
    players = Player.query.filter_by(team_organization_id=team_organization_id).all()
    
    # Get all stats in one batch for efficiency
    player_stats_dict = get_players_base_stats(players)
    
    # Calculate team averages once
    team_avgs = calc_team_avgs(None)
    
    for player in players:
        print(f"  Processing {player.name}...")
        # Get stats from the pre-calculated dictionary
        stats_dict = player_stats_dict.get(player.id, {})
        
        if stats_dict.get('points_played', 0) > 0:
            # Calculate PER using the team averages
            per = calculate_per(player, None, team_avgs)
            
            # Create a new PlayerStats record
            record = PlayerStats(
                player_id=player.id,
                per=per,
                team_organization_id=team_organization_id,  # Set the team_organization_id explicitly
                **stats_dict
            )
            db.session.add(record)
    
    # Commit all changes at once
    db.session.commit()
    print("Player stats populated.")

if __name__ == '__main__':
    # You can specify a different team_organization_id if needed
    populate_all(team_organization_id=1)
