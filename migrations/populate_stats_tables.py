# migrations/populate_stats_tables.py
from app import db, create_app
from app.models.player import Player
from app.models.game import Game
from app.models.tournament import Tournament
from app.models.point import Point, LineUp
from app.models.stats import PlayerStats, TeamStats
from app.stats_dashboard.stats import (
    get_player_base_stats, calculate_team_summary, 
    calculate_additional_team_metrics, calculate_per
)
from datetime import datetime
import logging

app = create_app()
logger = logging.getLogger(__name__)

def calculate_team_averages(games=None):
    """Calculate team averages for PER normalization"""
    # This function should be imported from app.stats_dashboard.stats
    # If not available, here's a simplified implementation
    team_org_id = None
    
    # Get a sample player to determine team_organization_id
    if games and len(games) > 0:
        team_org_id = games[0].team_organization_id
    else:
        player = Player.query.first()
        if player:
            team_org_id = player.team_organization_id
    
    if not team_org_id:
        return {
            'avg_o_line_plus_minus_per_point': 0,
            'avg_d_line_plus_minus_per_point': 0,
            'avg_uper': 1
        }
    
    players = Player.query.filter_by(
        active=True,
        team_organization_id=team_org_id
    ).all()
    
    totals = {
        'o_line_plus_minus': 0,
        'o_line_points': 0,
        'd_line_plus_minus': 0,
        'd_line_points': 0,
        'uper_total': 0,
        'player_count': 0
    }
    
    # Calculate basic stats for each player
    for player in players:
        stats = get_player_base_stats(player, games)
        if stats['points_played'] > 0:
            totals['player_count'] += 1
            totals['o_line_plus_minus'] += stats.get('o_line_plus_minus', 0)
            totals['o_line_points'] += stats.get('o_line_points_played', 0)
            totals['d_line_plus_minus'] += stats.get('d_line_plus_minus', 0)
            totals['d_line_points'] += stats.get('d_line_points_played', 0)
            
            # Add a simple uPER calculation
            totals['uper_total'] += (
                stats['goals'] + stats['assists'] + stats['blocks'] - 
                stats['throwaways'] - stats['drops']
            ) / stats['points_played']
    
    # Calculate averages
    return {
        'avg_o_line_plus_minus_per_point': (totals['o_line_plus_minus'] / totals['o_line_points']) if totals['o_line_points'] > 0 else 0,
        'avg_d_line_plus_minus_per_point': (totals['d_line_plus_minus'] / totals['d_line_points']) if totals['d_line_points'] > 0 else 0,
        'avg_uper': totals['uper_total'] / totals['player_count'] if totals['player_count'] > 0 else 1
    }

def populate_player_stats():
    with app.app_context():
        print("Starting player stats migration...")
        players = Player.query.all()
        total = len(players)
        
        # Process all-time stats for each player
        for i, player in enumerate(players):
            print(f"Processing player {i+1}/{total}: {player.name}")
            
            # Get all-time stats
            stats = get_player_base_stats(player)
            if stats['points_played'] > 0:
                team_avgs = calculate_team_averages()
                per_value = calculate_per(player, None, team_avgs)
                
                all_time_stats = PlayerStats(
                    player_id=player.id,
                    points_played=stats['points_played'],
                    o_line_points_played=stats['o_line_points_played'],
                    d_line_points_played=stats['d_line_points_played'],
                    goals=stats['goals'],
                    assists=stats['assists'],
                    hockey_assists=stats['hockey_assists'],
                    blocks=stats['blocks'],
                    throws=stats['throws'],
                    completions=stats['completions'],
                    throwaways=stats['throwaways'],
                    drops=stats['drops'],
                    stalls=stats.get('stalls', 0),
                    completion_rate=stats['completion_rate'],
                    catch_rate=stats['catch_rate'],
                    o_line_plus_minus=stats['o_line_plus_minus'],
                    d_line_plus_minus=stats['d_line_plus_minus'],
                    per=per_value,
                    team_organization_id=player.team_organization_id,
                    last_calculated=datetime.utcnow()
                )
                db.session.add(all_time_stats)
            
            # Process per-game stats
            # First get all games where this player participated
            games_query = db.session.query(Game).join(
                Point, Point.game_id == Game.id
            ).join(
                LineUp, LineUp.point_id == Point.id
            ).filter(
                LineUp.player_id == player.id
            ).distinct()
            
            games = games_query.all()
            
            for game in games:
                game_stats = get_player_base_stats(player, game)
                if game_stats['points_played'] > 0:
                    game_team_avgs = calculate_team_averages([game])
                    game_per = calculate_per(player, [game], game_team_avgs)
                    
                    game_player_stats = PlayerStats(
                        player_id=player.id,
                        game_id=game.id,
                        tournament_id=game.tournament_id,
                        season=game.tournament.season if game.tournament else None,
                        points_played=game_stats['points_played'],
                        o_line_points_played=game_stats['o_line_points_played'],
                        d_line_points_played=game_stats['d_line_points_played'],
                        goals=game_stats['goals'],
                        assists=game_stats['assists'],
                        hockey_assists=game_stats['hockey_assists'],
                        blocks=game_stats['blocks'],
                        throws=game_stats['throws'],
                        completions=game_stats['completions'],
                        throwaways=game_stats['throwaways'],
                        drops=game_stats['drops'],
                        stalls=game_stats.get('stalls', 0),
                        completion_rate=game_stats['completion_rate'],
                        catch_rate=game_stats['catch_rate'],
                        o_line_plus_minus=game_stats['o_line_plus_minus'],
                        d_line_plus_minus=game_stats['d_line_plus_minus'],
                        per=game_per,
                        team_organization_id=player.team_organization_id,
                        last_calculated=datetime.utcnow()
                    )
                    db.session.add(game_player_stats)
            
            # Process per-tournament stats
            tournaments_query = db.session.query(Tournament).join(
                Game, Game.tournament_id == Tournament.id
            ).join(
                Point, Point.game_id == Game.id
            ).join(
                LineUp, LineUp.point_id == Point.id
            ).filter(
                LineUp.player_id == player.id
            ).distinct()
            
            tournaments = tournaments_query.all()
            
            for tournament in tournaments:
                tournament_games = Game.query.filter_by(tournament_id=tournament.id).all()
                tournament_stats = get_player_base_stats(player, tournament_games)
                
                if tournament_stats['points_played'] > 0:
                    tournament_team_avgs = calculate_team_averages(tournament_games)
                    tournament_per = calculate_per(player, tournament_games, tournament_team_avgs)
                    
                    tournament_player_stats = PlayerStats(
                        player_id=player.id,
                        tournament_id=tournament.id,
                        season=tournament.season,
                        points_played=tournament_stats['points_played'],
                        o_line_points_played=tournament_stats['o_line_points_played'],
                        d_line_points_played=tournament_stats['d_line_points_played'],
                        goals=tournament_stats['goals'],
                        assists=tournament_stats['assists'],
                        hockey_assists=tournament_stats['hockey_assists'],
                        blocks=tournament_stats['blocks'],
                        throws=tournament_stats['throws'],
                        completions=tournament_stats['completions'],
                        throwaways=tournament_stats['throwaways'],
                        drops=tournament_stats['drops'],
                        stalls=tournament_stats.get('stalls', 0),
                        completion_rate=tournament_stats['completion_rate'],
                        catch_rate=tournament_stats['catch_rate'],
                        o_line_plus_minus=tournament_stats['o_line_plus_minus'],
                        d_line_plus_minus=tournament_stats['d_line_plus_minus'],
                        per=tournament_per,
                        team_organization_id=player.team_organization_id,
                        last_calculated=datetime.utcnow()
                    )
                    db.session.add(tournament_player_stats)
            
            # Process per-season stats
            seasons = db.session.query(Tournament.season).distinct().all()
            for season_tuple in seasons:
                season = season_tuple[0]
                if not season:
                    continue
                    
                season_tournaments = Tournament.query.filter_by(season=season).all()
                season_games = Game.query.filter(Game.tournament_id.in_([t.id for t in season_tournaments])).all()
                season_stats = get_player_base_stats(player, season_games)
                
                if season_stats['points_played'] > 0:
                    season_team_avgs = calculate_team_averages(season_games)
                    season_per = calculate_per(player, season_games, season_team_avgs)
                    
                    season_player_stats = PlayerStats(
                        player_id=player.id,
                        season=season,
                        points_played=season_stats['points_played'],
                        o_line_points_played=season_stats['o_line_points_played'],
                        d_line_points_played=season_stats['d_line_points_played'],
                        goals=season_stats['goals'],
                        assists=season_stats['assists'],
                        hockey_assists=season_stats['hockey_assists'],
                        blocks=season_stats['blocks'],
                        throws=season_stats['throws'],
                        completions=season_stats['completions'],
                        throwaways=season_stats['throwaways'],
                        drops=season_stats['drops'],
                        stalls=season_stats.get('stalls', 0),
                        completion_rate=season_stats['completion_rate'],
                        catch_rate=season_stats['catch_rate'],
                        o_line_plus_minus=season_stats['o_line_plus_minus'],
                        d_line_plus_minus=season_stats['d_line_plus_minus'],
                        per=season_per,
                        team_organization_id=player.team_organization_id,
                        last_calculated=datetime.utcnow()
                    )
                    db.session.add(season_player_stats)
            
            # Commit after each player to avoid large transactions
            db.session.commit()
        
        print("Player stats migration complete!")

def populate_team_stats():
    with app.app_context():
        print("Starting team stats migration...")
        
        # Process all-time team stats
        team_orgs = db.session.query(db.distinct(Player.team_organization_id)).all()
        for team_org_tuple in team_orgs:
            team_org_id = team_org_tuple[0]
            if not team_org_id:
                continue
                
            print(f"Processing team organization ID: {team_org_id}")
            
            # Get all games for this team
            games = Game.query.filter_by(team_organization_id=team_org_id).all()
            if not games:
                continue
                
            # Calculate all-time team stats
            team_summary = calculate_team_summary(games)
            team_metrics = calculate_additional_team_metrics(games)
            
            all_time_stats = TeamStats(
                games_played=team_summary['games_played'],
                wins=team_summary['wins'],
                losses=team_summary['losses'],
                ties=team_summary['ties'],
                total_points=team_summary['total_points'],
                o_line_points=team_summary['o_line_points'],
                o_line_conversions=team_summary['o_line_conversions'],
                d_line_points=team_summary['d_line_points'],
                d_line_conversions=team_summary['d_line_conversions'],
                breaks=team_summary['breaks'],
                holds=team_summary['holds'],
                win_percentage=team_summary['win_percentage'],
                o_line_conversion_rate=team_summary['o_line_conversion_rate'],
                d_line_conversion_rate=team_summary['d_line_conversion_rate'],
                completion_rate=team_metrics['completion_rate'],
                goals_per_point=team_metrics['goals_per_point'],
                assists_per_point=team_metrics['assists_per_point'],
                throws_per_point=team_metrics['throws_per_point'],
                hucks_per_point=team_metrics['hucks_per_point'],
                blocks_per_point=team_metrics['blocks_per_point'],
                turnovers_forced_per_point=team_metrics['turnovers_forced_per_point'],
                defensive_efficiency=team_metrics['defensive_efficiency'],
                break_percentage=team_metrics['break_percentage'],
                team_organization_id=team_org_id,
                last_calculated=datetime.utcnow()
            )
            db.session.add(all_time_stats)
            
            # Process per-game team stats
            for game in games:
                game_summary = calculate_team_summary([game])
                game_metrics = calculate_additional_team_metrics([game])
                
                game_team_stats = TeamStats(
                    game_id=game.id,
                    tournament_id=game.tournament_id,
                    season=game.tournament.season if game.tournament else None,
                    games_played=1,
                    wins=1 if game.is_win else 0,
                    losses=1 if game.is_loss else 0,
                    ties=1 if game.is_tie else 0,
                    total_points=game_summary['total_points'],
                    o_line_points=game_summary['o_line_points'],
                    o_line_conversions=game_summary['o_line_conversions'],
                    d_line_points=game_summary['d_line_points'],
                    d_line_conversions=game_summary['d_line_conversions'],
                    breaks=game_summary['breaks'],
                    holds=game_summary['holds'],
                    win_percentage=100 if game.is_win else 0,
                    o_line_conversion_rate=game_summary['o_line_conversion_rate'],
                    d_line_conversion_rate=game_summary['d_line_conversion_rate'],
                    completion_rate=game_metrics['completion_rate'],
                    goals_per_point=game_metrics['goals_per_point'],
                    assists_per_point=game_metrics['assists_per_point'],
                    throws_per_point=game_metrics['throws_per_point'],
                    hucks_per_point=game_metrics['hucks_per_point'],
                    blocks_per_point=game_metrics['blocks_per_point'],
                    turnovers_forced_per_point=game_metrics['turnovers_forced_per_point'],
                    defensive_efficiency=game_metrics['defensive_efficiency'],
                    break_percentage=game_metrics['break_percentage'],
                    team_organization_id=team_org_id,
                    last_calculated=datetime.utcnow()
                )
                db.session.add(game_team_stats)
            
            # Process per-tournament team stats
            tournaments = Tournament.query.join(Game).filter(
                Game.team_organization_id == team_org_id
            ).distinct().all()
            
            for tournament in tournaments:
                tournament_games = Game.query.filter_by(
                    tournament_id=tournament.id,
                    team_organization_id=team_org_id
                ).all()
                
                tournament_summary = calculate_team_summary(tournament_games)
                tournament_metrics = calculate_additional_team_metrics(tournament_games)
                
                tournament_team_stats = TeamStats(
                    tournament_id=tournament.id,
                    season=tournament.season,
                    games_played=tournament_summary['games_played'],
                    wins=tournament_summary['wins'],
                    losses=tournament_summary['losses'],
                    ties=tournament_summary['ties'],
                    total_points=tournament_summary['total_points'],
                    o_line_points=tournament_summary['o_line_points'],
                    o_line_conversions=tournament_summary['o_line_conversions'],
                    d_line_points=tournament_summary['d_line_points'],
                    d_line_conversions=tournament_summary['d_line_conversions'],
                    breaks=tournament_summary['breaks'],
                    holds=tournament_summary['holds'],
                    win_percentage=tournament_summary['win_percentage'],
                    o_line_conversion_rate=tournament_summary['o_line_conversion_rate'],
                    d_line_conversion_rate=tournament_summary['d_line_conversion_rate'],
                    completion_rate=tournament_metrics['completion_rate'],
                    goals_per_point=tournament_metrics['goals_per_point'],
                    assists_per_point=tournament_metrics['assists_per_point'],
                    throws_per_point=tournament_metrics['throws_per_point'],
                    hucks_per_point=tournament_metrics['hucks_per_point'],
                    blocks_per_point=tournament_metrics['blocks_per_point'],
                    turnovers_forced_per_point=tournament_metrics['turnovers_forced_per_point'],
                    defensive_efficiency=tournament_metrics['defensive_efficiency'],
                    break_percentage=tournament_metrics['break_percentage'],
                    team_organization_id=team_org_id,
                    last_calculated=datetime.utcnow()
                )
                db.session.add(tournament_team_stats)
            
            # Process per-season team stats
            seasons = db.session.query(Tournament.season).distinct().all()
            for season_tuple in seasons:
                season = season_tuple[0]
                if not season:
                    continue
                    
                season_tournaments = Tournament.query.filter_by(season=season).all()
                season_games = Game.query.filter(
                    Game.tournament_id.in_([t.id for t in season_tournaments]),
                    Game.team_organization_id == team_org_id
                ).all()
                
                if not season_games:
                    continue
                    
                season_summary = calculate_team_summary(season_games)
                season_metrics = calculate_additional_team_metrics(season_games)
                
                season_team_stats = TeamStats(
                    season=season,
                    games_played=season_summary['games_played'],
                    wins=season_summary['wins'],
                    losses=season_summary['losses'],
                    ties=season_summary['ties'],
                    total_points=season_summary['total_points'],
                    o_line_points=season_summary['o_line_points'],
                    o_line_conversions=season_summary['o_line_conversions'],
                    d_line_points=season_summary['d_line_points'],
                    d_line_conversions=season_summary['d_line_conversions'],
                    breaks=season_summary['breaks'],
                    holds=season_summary['holds'],
                    win_percentage=season_summary['win_percentage'],
                    o_line_conversion_rate=season_summary['o_line_conversion_rate'],
                    d_line_conversion_rate=season_summary['d_line_conversion_rate'],
                    completion_rate=season_metrics['completion_rate'],
                    goals_per_point=season_metrics['goals_per_point'],
                    assists_per_point=season_metrics['assists_per_point'],
                    throws_per_point=season_metrics['throws_per_point'],
                    hucks_per_point=season_metrics['hucks_per_point'],
                    blocks_per_point=season_metrics['blocks_per_point'],
                    turnovers_forced_per_point=season_metrics['turnovers_forced_per_point'],
                    defensive_efficiency=season_metrics['defensive_efficiency'],
                    break_percentage=season_metrics['break_percentage'],
                    team_organization_id=team_org_id,
                    last_calculated=datetime.utcnow()
                )
                db.session.add(season_team_stats)
            
            # Commit after each team organization
            db.session.commit()
        
        print("Team stats migration complete!")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    populate_player_stats()
    populate_team_stats()
