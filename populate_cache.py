#!/usr/bin/env python
# populate_cache.py
import os
import sys
import time
import argparse
import traceback
from datetime import datetime, timedelta

# Disable Discord integration
os.environ['DISCORD_ENABLED'] = 'False'

# Import after setting environment variable
from app_factory import create_app, db
from app.models.player import Player
from app.models.game import Game
from app.models.team_organization import TeamOrganization
from app.utils.stats_service import StatsService

def print_status(message):
    """Print a timestamped status message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def print_progress(current, total, entity_type="items", start_time=None):
    """Print progress information with time estimates"""
    percent = (current / total) * 100 if total > 0 else 0
    progress_msg = f"  Progress: {current}/{total} {entity_type} ({percent:.1f}%)"
    
    if start_time is not None:
        elapsed = time.time() - start_time
        avg_time = elapsed / current if current > 0 else 0
        remaining = avg_time * (total - current) if avg_time > 0 else 0
        
        # Format time strings
        elapsed_str = format_time(elapsed)
        remaining_str = format_time(remaining)
        
        progress_msg += f" - Elapsed: {elapsed_str}, Est. remaining: {remaining_str}"
    
    print(progress_msg)

def format_time(seconds):
    """Format seconds into a readable time string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def main():
    """Main function to populate the stats cache"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Populate statistics cache')
    parser.add_argument('--team', type=int, help='Team organization ID to process (default: all teams)')
    parser.add_argument('--skip-teams', action='store_true', help='Skip team stats caching')
    parser.add_argument('--skip-games', action='store_true', help='Skip game stats caching')
    parser.add_argument('--skip-players', action='store_true', help='Skip player stats caching')
    parser.add_argument('--player', type=int, help='Process only a specific player ID')
    parser.add_argument('--days', type=int, help='Process only data from the last N days')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--inactive', action='store_true', help='Include inactive players')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed progress')
    args = parser.parse_args()

    # Create the app
    app = create_app()
    
    # Determine date range
    start_date = None
    end_date = None
    
    if args.days:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.days)
        print_status(f"Processing data from {start_date} to {end_date}")
    elif args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end_date = datetime.now().date()
        print_status(f"Processing data from {start_date} to {end_date}")

    # Create application context
    with app.app_context():
        try:
            # Get team organizations based on command line args
            if args.team:
                team_orgs = TeamOrganization.query.filter_by(id=args.team).all()
            else:
                team_orgs = TeamOrganization.query.all()
            
            print_status(f"Found {len(team_orgs)} team organizations")
            team_start_time = time.time()
            
            for team_idx, team_org in enumerate(team_orgs, 1):
                print_status(f"Processing team {team_org.name} ({team_idx}/{len(team_orgs)})")
                
                try:
                    # Cache team stats if not skipped
                    if not args.skip_teams:
                        print_status(f"Caching team stats for {team_org.name}...")
                        StatsService.update_team_stats_cache(team_org.id, start_date, end_date)
                    else:
                        print_status("Skipping team stats (--skip-teams flag)")
                    
                    # Cache game stats for this team (if not skipped)
                    if not args.skip_games:
                        games = Game.query.filter_by(team_organization_id=team_org.id)
                        if start_date:
                            games = games.filter(Game.date >= start_date)
                        if end_date:
                            games = games.filter(Game.date <= end_date)
                        games = games.all()
                        
                        print_status(f"Found {len(games)} games for {team_org.name}")
                        
                        if games:
                            game_start_time = time.time()
                            for game_idx, game in enumerate(games, 1):
                                try:
                                    if args.verbose:
                                        print(f"  Caching stats for game vs {game.opponent}...")
                                    
                                    StatsService.update_game_stats_cache(game.id)
                                    
                                    # Print progress periodically
                                    if game_idx % 5 == 0 or game_idx == len(games):
                                        print_progress(game_idx, len(games), "games", game_start_time)
                                        
                                except Exception as e:
                                    print(f"  Error caching game stats for game {game.id}: {str(e)}")
                                    if args.verbose:
                                        traceback.print_exc()
                    else:
                        print_status("Skipping game stats (--skip-games flag)")
                    
                    # Cache player stats for this team (if not skipped)
                    if not args.skip_players:
                        # Filter players based on command line args
                        players_query = Player.query.filter_by(team_organization_id=team_org.id)
                        
                        if args.player:
                            players_query = players_query.filter_by(id=args.player)
                        elif not args.inactive:
                            players_query = players_query.filter_by(active=True)
                            
                        players = players_query.all()
                        
                        print_status(f"Found {len(players)} players to process for {team_org.name}")
                        
                        if players:
                            player_start_time = time.time()
                            for player_idx, player in enumerate(players, 1):
                                try:
                                    if args.verbose:
                                        print(f"  Caching stats for player {player.name}...")
                                    
                                    StatsService.update_player_stats_cache(player, team_org.id, start_date, end_date)
                                    
                                    # Print progress periodically
                                    if player_idx % 5 == 0 or player_idx == len(players):
                                        print_progress(player_idx, len(players), "players", player_start_time)
                                        
                                except Exception as e:
                                    print(f"  Error caching player stats for {player.name}: {str(e)}")
                                    if args.verbose:
                                        traceback.print_exc()
                    else:
                        print_status("Skipping player stats (--skip-players flag)")
                    
                    # Print team progress
                    print_progress(team_idx, len(team_orgs), "teams", team_start_time)
                        
                except Exception as e:
                    print_status(f"Error processing team {team_org.name}: {str(e)}")
                    if args.verbose:
                        traceback.print_exc()
                    
            # Calculate and print total time
            total_time = time.time() - team_start_time
            print_status(f"Cache population complete! Total time: {format_time(total_time)}")
            
        except Exception as e:
            print_status(f"Error during cache population: {str(e)}")
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    main()
