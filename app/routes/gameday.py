from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.game_player import GamePlayer
from app.models.point import Point, LineUp
from app.models.gameday import GameDayEvent, GameDayPlayerStats, LineTemplate, LineTemplatePlayer
from app.models.team_organization import TeamOrganization  # Add this import
from app.utils.utils import admin_required, coach_required, stat_taker_required

bp = Blueprint('gameday', __name__, url_prefix='/gameday')


@bp.route('/')
@login_required
@stat_taker_required
def index():
    """Stat-recording hub: pick a game, then choose Game Day or Positional Analysis mode."""
    from app.utils.team_filter import get_current_team_id
    from sqlalchemy import desc
    from datetime import date
    games = (
        Game.query
        .filter_by(team_organization_id=get_current_team_id())
        .order_by(desc(Game.date), desc(Game.id))
        .limit(30)
        .all()
    )
    return render_template('gameday/index.html', games=games, today=date.today())


@bp.route('/game/<int:game_id>')
@login_required
@stat_taker_required
def game_dashboard(game_id):
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Add our_team attribute if it doesn't exist
    if not hasattr(game, 'our_team'):
        game.our_team = "Our Team"
    
    # Get players assigned to this game — single JOIN instead of two queries
    all_game_players = (
        Player.query
        .join(GamePlayer, GamePlayer.player_id == Player.id)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.team_organization_id == get_current_team_id(),
            Player.team_organization_id == get_current_team_id(),
        )
        .all()
    )
    
    # Split players by gender
    mmp_players = [p for p in all_game_players if p.gender == "male"]
    fmp_players = [p for p in all_game_players if p.gender == "female"]
    
    # Get player stats for this game
    player_stats = GameDayPlayerStats.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary for quick lookup
    stats_dict = {stat.player_id: stat for stat in player_stats}
    
    # Add stats to player objects
    for player in mmp_players + fmp_players:
        if player.id in stats_dict:
            player.game_stats = stats_dict[player.id]
        else:
            # Create empty stats object
            player.game_stats = {
                'points_played': 0,
                'goals': 0,
                'assists': 0,
                'blocks': 0,
                'turns': 0,
                'plus_minus': 0
            }
    
    # Get saved line templates
    line_templates = LineTemplate.query.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Calculate next point number — scalar aggregate avoids loading a full row
    max_point_number = db.session.query(
        func.max(Point.point_number)
    ).filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).scalar()
    next_point_number = (max_point_number or 0) + 1
    
    return render_template('gameday/dashboard.html', 
                          game=game,
                          mmp_players=mmp_players,
                          fmp_players=fmp_players,
                          line_templates=line_templates,
                          next_point_number=next_point_number)



@bp.route('/api/record-point', methods=['POST'])
@login_required
@stat_taker_required
def record_point():
    data = request.json
    
    try:
        game_id = data.get('game_id')
        point_number = data.get('point_number')
        line_type = data.get('line_type')
        gender_ratio = data.get('gender_ratio')
        players = data.get('players', [])
        events = data.get('events', [])
        outcome = data.get('outcome')
        
        # Get current team ID
        team_id = get_current_team_id()
        
        # Verify game belongs to current team
        game = Game.query.filter_by(
            id=game_id,
            team_organization_id=team_id
        ).first_or_404()
        
        # Create new point
        point = Point(
            game_id=game_id,
            point_number=point_number,
            our_line_type=line_type,
            our_score_before=game.our_score,
            their_score_before=game.their_score,
            starting_position='offense' if line_type == 'O-line' else 'defense',
            point_outcome=outcome,
            gender_ratio=gender_ratio,
            team_organization_id=team_id
        )

        
        db.session.add(point)
        db.session.flush()  # Get point ID without committing
        

        # Add players to lineup without relying on auto-incrementing IDs
        for player_id in players:
            # Verify player belongs to current team
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=team_id
            ).first()
            
            if player:
                # Check if a lineup entry already exists for this point and player
                existing_lineup = LineUp.query.filter_by(
                    point_id=point.id,
                    player_id=player_id
                ).first()
                
                if not existing_lineup:
                    lineup = LineUp(
                        point_id=point.id,
                        player_id=player_id,
                        team_organization_id=team_id
                    )
                    db.session.add(lineup)

        
        # Process events
        sequence = 0
        for event in events:
            sequence += 1
            
            # Skip possession changes and point outcomes
            if event['type'] in ['possession_change', 'point_outcome']:
                continue
                
            # Verify player belongs to current team if player_id is provided
            player_id = event.get('player_id')
            if player_id:
                player = Player.query.filter_by(
                    id=player_id,
                    team_organization_id=team_id
                ).first()
                
                if not player:
                    # Skip events for players not in the current team
                    continue
            
            gameday_event = GameDayEvent(
                point_id=point.id,
                player_id=player_id,
                event_type=event['type'],
                event_result=event.get('result'),
                sequence=sequence,
                team_organization_id=team_id  # Add team ID
            )
            db.session.add(gameday_event)
        
        # Update game score
        if outcome == 'scored':
            game.our_score += 1
            point.our_score_after = game.our_score
            point.their_score_after = game.their_score
        else:
            game.their_score += 1
            point.our_score_after = game.our_score
            point.their_score_after = game.their_score
        
        # Update player stats
        for player_id in players:
            # Verify player belongs to current team
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=team_id
            ).first()
            
            if not player:
                continue
                
            # Get or create player stats
            player_stat = GameDayPlayerStats.query.filter_by(
                player_id=player_id,
                game_id=game_id,
                team_organization_id=team_id  # Add team ID
            ).first()
            
            if not player_stat:
                player_stat = GameDayPlayerStats(
                    player_id=player_id,
                    game_id=game_id,
                    # Initialize all stats to 0
                    points_played=0,
                    o_points=0,
                    d_points=0,
                    goals=0,
                    assists=0,
                    blocks=0,
                    turns=0,
                    plus_minus=0,
                    callahans=0,
                    pulls=0,
                    pulls_ob=0,
                    team_organization_id=team_id  # Add team ID
                )
                db.session.add(player_stat)
            
            # Ensure all stats have default values
            if player_stat.points_played is None: player_stat.points_played = 0
            if player_stat.o_points is None: player_stat.o_points = 0
            if player_stat.d_points is None: player_stat.d_points = 0
            if player_stat.goals is None: player_stat.goals = 0
            if player_stat.assists is None: player_stat.assists = 0
            if player_stat.blocks is None: player_stat.blocks = 0
            if player_stat.turns is None: player_stat.turns = 0
            if player_stat.plus_minus is None: player_stat.plus_minus = 0
            if player_stat.callahans is None: player_stat.callahans = 0
            if player_stat.pulls is None: player_stat.pulls = 0
            if player_stat.pulls_ob is None: player_stat.pulls_ob = 0
            
            # Update points played
            player_stat.points_played += 1
            
            if line_type == 'O-line':
                player_stat.o_points += 1
            else:
                player_stat.d_points += 1
            
            # Process player-specific events
            for event in events:
                if event.get('player_id') == player_id:
                    if event['type'] == 'score':
                        player_stat.goals += 1
                        player_stat.plus_minus += 1
                    elif event['type'] == 'assist':
                        player_stat.assists += 1
                        player_stat.plus_minus += 1
                    elif event['type'] == 'block':
                        player_stat.blocks += 1
                        player_stat.plus_minus += 1
                    elif event['type'] == 'callahan':
                        player_stat.goals += 1
                        player_stat.blocks += 1
                        player_stat.callahans += 1
                        player_stat.plus_minus += 2  # Double value for Callahan
                    elif event['type'] in ['throwaway', 'drop', 'stall']:
                        player_stat.turns += 1
                        player_stat.plus_minus -= 1
                    elif event['type'] == 'pull':
                        player_stat.pulls += 1
                        if event.get('result') == 'out':
                            player_stat.pulls_ob += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'our_score': game.our_score,
            'their_score': game.their_score,
            'next_point_number': point.point_number + 1
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        })



@bp.route('/api/line-template/save', methods=['POST'])
@login_required
@stat_taker_required
def save_line_template():
    data = request.json
    
    try:
        name = data.get('name')
        line_type = data.get('line_type')
        gender_ratio = data.get('gender_ratio')
        player_ids = data.get('players', [])
        
        # Get current team ID
        team_id = get_current_team_id()
        
        # Create template
        template = LineTemplate(
            name=name,
            line_type=line_type,
            gender_ratio=gender_ratio,
            team_organization_id=team_id  # Add team ID
        )
        
        db.session.add(template)
        db.session.flush()  # Get template ID without committing
        
        # Add players to template
        for player_id in player_ids:
            # Verify player belongs to current team
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=team_id
            ).first()
            
            if player:
                template_player = LineTemplatePlayer(
                    template_id=template.id,
                    player_id=player_id,
                    team_organization_id=team_id  # Add team ID
                )
                db.session.add(template_player)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'template_id': template.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@bp.route('/api/line-template/<int:template_id>', methods=['GET'])
@login_required
@stat_taker_required
def get_line_template(template_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Verify template belongs to current team
    template = LineTemplate.query.filter_by(
        id=template_id,
        team_organization_id=team_id
    ).first_or_404()
    
    template_players = LineTemplatePlayer.query.filter_by(
        template_id=template_id,
        team_organization_id=team_id
    ).all()
    
    return jsonify({
        'id': template.id,
        'name': template.name,
        'line_type': template.line_type,
        'gender_ratio': template.gender_ratio,
        'players': [tp.player_id for tp in template_players]
    })

@bp.route('/api/line-templates', methods=['GET'])
@login_required
@stat_taker_required
def get_all_line_templates():
    # Get current team ID
    team_id = get_current_team_id()
    
    # Get all templates for the current team
    templates = LineTemplate.query.filter_by(
        team_organization_id=team_id
    ).all()
    
    result = []
    for template in templates:
        template_players = LineTemplatePlayer.query.filter_by(
            template_id=template.id,
            team_organization_id=team_id
        ).all()
        
        result.append({
            'id': template.id,
            'name': template.name,
            'line_type': template.line_type,
            'gender_ratio': template.gender_ratio,
            'players': [tp.player_id for tp in template_players]
        })
    
    return jsonify(result)

@bp.route('/api/line-template/<int:template_id>', methods=['DELETE'])
@login_required
@stat_taker_required
def delete_line_template(template_id):
    try:
        # Get current team ID
        team_id = get_current_team_id()
        
        # Verify template belongs to current team
        template = LineTemplate.query.filter_by(
            id=template_id,
            team_organization_id=team_id
        ).first_or_404()
        
        # Delete associated template players
        LineTemplatePlayer.query.filter_by(
            template_id=template_id,
            team_organization_id=team_id
        ).delete()
        
        # Delete the template
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Template "{template.name}" deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@bp.route('/admin/fix_missing_team_ids', methods=['GET'])
@login_required
@admin_required
def fix_missing_team_ids():
    """
    Administrative route to fix any records that might be missing team_organization_id
    This is useful during the transition to multi-team support
    """
    try:
        # Only allow this operation for admin users
        if not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Get the current team ID
        team_id = get_current_team_id()
        if not team_id:
            return jsonify({'error': 'No team ID available'}), 400
            
        # Fix GameDayEvent records
        events_fixed = GameDayEvent.query.filter(GameDayEvent.team_organization_id.is_(None)).update(
            {'team_organization_id': team_id}, 
            synchronize_session=False
        )
        
        # Fix GameDayPlayerStats records
        stats_fixed = GameDayPlayerStats.query.filter(GameDayPlayerStats.team_organization_id.is_(None)).update(
            {'team_organization_id': team_id}, 
            synchronize_session=False
        )
        
        # Fix LineTemplate records
        templates_fixed = LineTemplate.query.filter(LineTemplate.team_organization_id.is_(None)).update(
            {'team_organization_id': team_id}, 
            synchronize_session=False
        )
        
        # Fix LineTemplatePlayer records
        template_players_fixed = LineTemplatePlayer.query.filter(LineTemplatePlayer.team_organization_id.is_(None)).update(
            {'team_organization_id': team_id}, 
            synchronize_session=False
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Fixed missing team IDs',
            'stats': {
                'events_fixed': events_fixed,
                'stats_fixed': stats_fixed,
                'templates_fixed': templates_fixed,
                'template_players_fixed': template_players_fixed
            }
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error("Error in fix_missing_team_ids:", str(e))
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.errorhandler(Exception)
def handle_error(e):
    db.session.rollback()
    return jsonify({
        'success': False,
        'error': str(e)
    }), 500

@bp.route('/stats/<int:game_id>')
@login_required
@stat_taker_required
def game_stats(game_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Get the game
    game = Game.query.filter_by(
        id=game_id,
        team_organization_id=team_id
    ).first_or_404()
    
    # Get all player stats for this game
    player_stats = GameDayPlayerStats.query.filter_by(
        game_id=game_id,
        team_organization_id=team_id
    ).all()
    
    # Get player details for each stat
    for stat in player_stats:
        stat.player_details = Player.query.get(stat.player_id)
    
    # Get points for this game
    points = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=team_id
    ).order_by(Point.point_number).all()
    
    # Calculate team totals
    team_totals = {
        'goals': sum(stat.goals for stat in player_stats),
        'assists': sum(stat.assists for stat in player_stats),
        'blocks': sum(stat.blocks for stat in player_stats),
        'turns': sum(stat.turns for stat in player_stats),
        'plus_minus': sum(stat.plus_minus for stat in player_stats),
        'callahans': sum(stat.callahans for stat in player_stats),
        'pulls': sum(stat.pulls for stat in player_stats),
        'pulls_ob': sum(stat.pulls_ob for stat in player_stats),
    }
    
    # Calculate efficiency metrics
    if team_totals['goals'] > 0:
        team_totals['completion_rate'] = round(
            (team_totals['goals'] + team_totals['assists']) / 
            (team_totals['goals'] + team_totals['assists'] + team_totals['turns']) * 100, 1
        ) if (team_totals['goals'] + team_totals['assists'] + team_totals['turns']) > 0 else 0
    else:
        team_totals['completion_rate'] = 0
    
    return render_template(
        'gameday/stats.html',
        game=game,
        player_stats=player_stats,
        team_totals=team_totals,
        points=points
    )

@bp.route('/team-stats')
@login_required
@stat_taker_required
def team_stats():
    # Get current team ID
    team_id = get_current_team_id()
    
    # Get all games for this team
    games = Game.query.filter_by(
        team_organization_id=team_id
    ).order_by(Game.date.desc()).all()
    
    # Get all player stats for this team
    all_player_stats = GameDayPlayerStats.query.filter_by(
        team_organization_id=team_id
    ).all()
    
    # Group stats by player
    player_stats_by_id = {}
    for stat in all_player_stats:
        if stat.player_id not in player_stats_by_id:
            player_stats_by_id[stat.player_id] = {
                'player_id': stat.player_id,
                'games_played': 0,
                'points_played': 0,
                'o_points': 0,
                'd_points': 0,
                'goals': 0,
                'assists': 0,
                'blocks': 0,
                'turns': 0,
                'plus_minus': 0,
                'callahans': 0,
                'pulls': 0,
                'pulls_ob': 0
            }
        
        # Add stats
        player_stats_by_id[stat.player_id]['games_played'] += 1
        player_stats_by_id[stat.player_id]['points_played'] += stat.points_played or 0
        player_stats_by_id[stat.player_id]['o_points'] += stat.o_points or 0
        player_stats_by_id[stat.player_id]['d_points'] += stat.d_points or 0
        player_stats_by_id[stat.player_id]['goals'] += stat.goals or 0
        player_stats_by_id[stat.player_id]['assists'] += stat.assists or 0
        player_stats_by_id[stat.player_id]['blocks'] += stat.blocks or 0
        player_stats_by_id[stat.player_id]['turns'] += stat.turns or 0
        player_stats_by_id[stat.player_id]['plus_minus'] += stat.plus_minus or 0
        player_stats_by_id[stat.player_id]['callahans'] += stat.callahans or 0
        player_stats_by_id[stat.player_id]['pulls'] += stat.pulls or 0
        player_stats_by_id[stat.player_id]['pulls_ob'] += stat.pulls_ob or 0
    
    # Get player details
    players = Player.query.filter(
        Player.id.in_(player_stats_by_id.keys()),
        Player.team_organization_id == team_id
    ).all()
    
    # Add player details to stats
    player_stats = []
    for player in players:
        if player.id in player_stats_by_id:
            stats = player_stats_by_id[player.id]
            stats['name'] = player.name
            stats['jersey_number'] = player.jersey_number
            stats['gender'] = player.gender
            
            # Calculate per-game averages
            games_played = stats['games_played']
            if games_played > 0:
                stats['avg_points'] = round(stats['points_played'] / games_played, 1)
                stats['avg_goals'] = round(stats['goals'] / games_played, 1)
                stats['avg_assists'] = round(stats['assists'] / games_played, 1)
                stats['avg_blocks'] = round(stats['blocks'] / games_played, 1)
                stats['avg_turns'] = round(stats['turns'] / games_played, 1)
                stats['avg_plus_minus'] = round(stats['plus_minus'] / games_played, 1)
            
            player_stats.append(stats)
    
    # Calculate team totals
    team_totals = {
        'games_played': len(games),
        'wins': sum(1 for game in games if game.our_score > game.their_score),
        'losses': sum(1 for game in games if game.our_score < game.their_score),
        'points_played': sum(game.our_score + game.their_score for game in games),
        'points_scored': sum(game.our_score for game in games),
        'points_conceded': sum(game.their_score for game in games),
        'goals': sum(stats['goals'] for stats in player_stats),
        'assists': sum(stats['assists'] for stats in player_stats),
        'blocks': sum(stats['blocks'] for stats in player_stats),
        'turns': sum(stats['turns'] for stats in player_stats),
        'plus_minus': sum(stats['plus_minus'] for stats in player_stats),
        'callahans': sum(stats['callahans'] for stats in player_stats),
        'pulls': sum(stats['pulls'] for stats in player_stats),
        'pulls_ob': sum(stats['pulls_ob'] for stats in player_stats),
    }
    
    # Calculate efficiency metrics
    if team_totals['goals'] > 0:
        team_totals['completion_rate'] = round(
            (team_totals['goals'] + team_totals['assists']) / 
            (team_totals['goals'] + team_totals['assists'] + team_totals['turns']) * 100, 1
        ) if (team_totals['goals'] + team_totals['assists'] + team_totals['turns']) > 0 else 0
    else:
        team_totals['completion_rate'] = 0
    
    # Get current team
    team = TeamOrganization.query.get(team_id)
    
    return render_template(
        'gameday/team_stats.html',
        team=team,
        games=games,
        player_stats=player_stats,
        team_totals=team_totals
    )

from sqlalchemy import text  # Add this import at the top of your file
from app.utils.team_filter import get_current_team_id

@bp.route('/admin/reset_all_sequences', methods=['GET'])
@login_required
@admin_required
def reset_all_sequences():
    """Reset ID sequences for all tables that might have issues"""
    results = {}
    
    try:
        # Get list of all tables in the database
        table_list_query = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema='public' 
            AND table_type='BASE TABLE'
        """)
        
        tables = [row[0] for row in db.session.execute(table_list_query)]
        
        # For each table, check if it has an ID column and reset its sequence
        for table in tables:
            try:
                # Check if table has an id column
                has_id_query = text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='{table}' AND column_name='id'
                """)
                
                has_id = db.session.execute(has_id_query).fetchone()
                
                if has_id:
                    # Reset the sequence for this table
                    reset_query = text(f"""
                        SELECT setval(pg_get_serial_sequence('{table}', 'id'), 
                                     (SELECT COALESCE(MAX(id), 1) FROM {table}))
                    """)
                    
                    result = db.session.execute(reset_query)
                    results[table] = result.scalar()
            except Exception as table_error:
                results[table] = f"Error: {str(table_error)}"
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'All sequences reset successfully',
            'results': results
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        current_app.logger.error("Error resetting sequences:", str(e))
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
