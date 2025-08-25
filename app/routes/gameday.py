from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
from app_factory import db
from app.models.game import Game
from app.models.player import Player
from app.models.game_player import GamePlayer
from app.models.point import Point, LineUp
from app.models.gameday import GameDayEvent, GameDayPlayerStats, LineTemplate, LineTemplatePlayer
from app.utils.utils import admin_required, coach_required, stat_taker_required

bp = Blueprint('gameday', __name__, url_prefix='/gameday')

# Helper function to get current team ID
def get_current_team_id():
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

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
    
    # Get players assigned to this game
    game_player_entries = GamePlayer.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).all()
    game_player_ids = [gp.player_id for gp in game_player_entries]
    
    # Get player objects
    all_game_players = Player.query.filter(
        Player.id.in_(game_player_ids),
        Player.team_organization_id == get_current_team_id()
    ).all()
    
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
    
    # Calculate next point number
    next_point_number = 1
    last_point = Point.query.filter_by(
        game_id=game_id,
        team_organization_id=get_current_team_id()
    ).order_by(Point.point_number.desc()).first()
    if last_point:
        next_point_number = last_point.point_number + 1
    
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
            team_organization_id=team_id  # Add team ID
        )
        
        db.session.add(point)
        db.session.flush()  # Get point ID without committing
        
        # Add players to lineup
        for player_id in players:
            # Verify player belongs to current team
            player = Player.query.filter_by(
                id=player_id,
                team_organization_id=team_id
            ).first()
            
            if player:
                lineup = LineUp(
                    point_id=point.id,
                    player_id=player_id,
                    team_organization_id=team_id  # Add team ID
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
        print(traceback.format_exc())  # Print the full traceback for debugging
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
        print("Error in fix_missing_team_ids:", str(e))
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.errorhandler(Exception)
def handle_error(e):
    db.session.rollback()
    return jsonify({
        'success': False,
        'error': str(e)
    }), 500
