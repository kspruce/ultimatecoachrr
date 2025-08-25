from app_factory import app, db
from models import Player, Game, TeamOrganization
from stats_service import StatsService

# Create application context
with app.app_context():
    # Get all team organizations
    team_orgs = TeamOrganization.query.all()
    
    for team_org in team_orgs:
        print(f"Caching stats for team {team_org.name}...")
        
        # Cache team stats
        StatsService.update_team_stats_cache(team_org.id)
        
        # Cache game stats for this team
        games = Game.query.filter_by(team_organization_id=team_org.id).all()
        for game in games:
            print(f"  Caching stats for game vs {game.opponent}...")
            StatsService.update_game_stats_cache(game.id)
        
        # Cache player stats for this team
        players = Player.query.filter_by(team_organization_id=team_org.id, active=True).all()
        for player in players:
            print(f"  Caching stats for player {player.name}...")
            StatsService.update_player_stats_cache(player, team_org.id)
    
    print("Cache population complete!")