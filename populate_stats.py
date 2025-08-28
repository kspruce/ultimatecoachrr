# Import db from models.base instead of from app
from app.models.base import db
from app import create_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.stats import PlayerStats, TeamStats

app = create_app()
app.app_context().push()

def populate_all():
    # Now import the stats functions inside the function to avoid circular imports
    from app.routes.stats import get_player_base_stats, calculate_team_summary, calculate_per, calculate_team_averages
    
    print("Deleting existing stats records...")
    PlayerStats.query.delete()
    TeamStats.query.delete()
    db.session.commit()

    print("Populating player stats...")
    players = Player.query.all()
    for player in players:
        print(f"  Processing {player.name}...")
        # All-time stats
        stats_dict = get_player_base_stats(player)
        if stats_dict['points_played'] > 0:
            team_avgs = calculate_team_averages()
            per = calculate_per(player, None, team_avgs)
            record = PlayerStats(player_id=player.id, per=per, **stats_dict)
            db.session.add(record)
    db.session.commit()
    print("Player stats populated.")

if __name__ == '__main__':
    populate_all()
