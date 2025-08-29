from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.stats_storage import IndexStats, TeamStats, GameStats, PlayerStats
from app.models.team_organization import TeamOrganization
from app.models.game import Game
from app.models.player import Player
from app.utils.utils import admin_required
import json
from datetime import datetime

bp = Blueprint('stats_storage', __name__)

@bp.route('/api/stats/save/index', methods=['POST'])
@login_required
@admin_required
def save_index_stats():
    """Save stats from the index page to the database."""
    try:
        data = request.get_json()
        
        if not data or 'stats_data' not in data:
            return jsonify({'error': 'No stats data provided'}), 400
            
        # Get team organization ID from current user
        team_organization_id = current_user.team_organization_id
        
        # Check if stats already exist for this team organization
        existing_stats = IndexStats.query.filter_by(team_organization_id=team_organization_id).first()
        
        # Get version number
        version = data.get('version', 1)
        if existing_stats and not data.get('create_new_version', False):
            # Update existing stats
            existing_stats.stats_data = data['stats_data']
            existing_stats.filter_params = data.get('filter_params')
            existing_stats.updated_at = datetime.utcnow()
            existing_stats.version = version
            db.session.commit()
            return jsonify({'message': 'Index stats updated successfully', 'id': existing_stats.id}), 200
        else:
            # Create new stats or new version
            new_stats = IndexStats(
                team_organization_id=team_organization_id,
                stats_data=data['stats_data'],
                filter_params=data.get('filter_params'),
                version=version
            )
            db.session.add(new_stats)
            db.session.commit()
            return jsonify({'message': 'Index stats saved successfully', 'id': new_stats.id}), 201
            
    except Exception as e:
        current_app.logger.error(f"Error saving index stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/stats/save/team', methods=['POST'])
@login_required
@admin_required
def save_team_stats():
    """Save team stats to the database."""
    try:
        data = request.get_json()
        
        if not data or 'stats_data' not in data:
            return jsonify({'error': 'No stats data provided'}), 400
            
        # Get team organization ID from current user
        team_organization_id = current_user.team_organization_id
        
        # Get version number
        version = data.get('version', 1)
        
        # Check if stats already exist for this team organization
        existing_stats = TeamStats.query.filter_by(
            team_organization_id=team_organization_id
        ).first()
        
        if existing_stats and not data.get('create_new_version', False):
            # Update existing stats
            existing_stats.stats_data = data['stats_data']
            existing_stats.filter_params = data.get('filter_params')
            existing_stats.updated_at = datetime.utcnow()
            existing_stats.version = version
            db.session.commit()
            return jsonify({'message': 'Team stats updated successfully', 'id': existing_stats.id}), 200
        else:
            # Create new stats or new version
            new_stats = TeamStats(
                team_organization_id=team_organization_id,
                stats_data=data['stats_data'],
                filter_params=data.get('filter_params'),
                version=version
            )
            db.session.add(new_stats)
            db.session.commit()
            return jsonify({'message': 'Team stats saved successfully', 'id': new_stats.id}), 201
            
    except Exception as e:
        current_app.logger.error(f"Error saving team stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/stats/save/game/<int:game_id>', methods=['POST'])
@login_required
@admin_required
def save_game_stats(game_id):
    """Save game stats to the database."""
    try:
        data = request.get_json()
        
        if not data or 'stats_data' not in data:
            return jsonify({'error': 'No stats data provided'}), 400
            
        # Get team organization ID from current user
        team_organization_id = current_user.team_organization_id
        
        # Verify the game exists and belongs to the user's team organization
        game = Game.query.filter_by(id=game_id, team_organization_id=team_organization_id).first()
        if not game:
            return jsonify({'error': 'Game not found or access denied'}), 404
            
        # Get version number
        version = data.get('version', 1)
        
        # Check if stats already exist for this game
        existing_stats = GameStats.query.filter_by(
            game_id=game_id,
            team_organization_id=team_organization_id
        ).first()
        
        if existing_stats and not data.get('create_new_version', False):
            # Update existing stats
            existing_stats.stats_data = data['stats_data']
            existing_stats.filter_params = data.get('filter_params')
            existing_stats.updated_at = datetime.utcnow()
            existing_stats.version = version
            db.session.commit()
            return jsonify({'message': 'Game stats updated successfully', 'id': existing_stats.id}), 200
        else:
            # Create new stats or new version
            new_stats = GameStats(
                game_id=game_id,
                team_organization_id=team_organization_id,
                stats_data=data['stats_data'],
                filter_params=data.get('filter_params'),
                version=version
            )
            db.session.add(new_stats)
            db.session.commit()
            return jsonify({'message': 'Game stats saved successfully', 'id': new_stats.id}), 201
            
    except Exception as e:
        current_app.logger.error(f"Error saving game stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/stats/save/player/<int:player_id>', methods=['POST'])
@login_required
@admin_required
def save_player_stats(player_id):
    """Save player stats to the database."""
    try:
        data = request.get_json()
        
        if not data or 'stats_data' not in data:
            return jsonify({'error': 'No stats data provided'}), 400
            
        # Get team organization ID from current user
        team_organization_id = current_user.team_organization_id
        
        # Verify the player exists and belongs to the user's team organization
        player = Player.query.filter_by(id=player_id, team_organization_id=team_organization_id).first()
        if not player:
            return jsonify({'error': 'Player not found or access denied'}), 404
            
        # Get game_id if provided
        game_id = data.get('game_id')
        
        # Get version number
        version = data.get('version', 1)
        
        # Check if stats already exist for this player (and game if specified)
        query = PlayerStats.query.filter_by(
            player_id=player_id,
            team_organization_id=team_organization_id
        )
        
        if game_id:
            query = query.filter_by(game_id=game_id)
        else:
            query = query.filter_by(game_id=None)
            
        existing_stats = query.first()
        
        if existing_stats and not data.get('create_new_version', False):
            # Update existing stats
            existing_stats.stats_data = data['stats_data']
            existing_stats.filter_params = data.get('filter_params')
            existing_stats.updated_at = datetime.utcnow()
            existing_stats.version = version
            db.session.commit()
            return jsonify({'message': 'Player stats updated successfully', 'id': existing_stats.id}), 200
        else:
            # Create new stats or new version
            new_stats = PlayerStats(
                player_id=player_id,
                game_id=game_id,
                team_organization_id=team_organization_id,
                stats_data=data['stats_data'],
                filter_params=data.get('filter_params'),
                version=version
            )
            db.session.add(new_stats)
            db.session.commit()
            return jsonify({'message': 'Player stats saved successfully', 'id': new_stats.id}), 201
            
    except Exception as e:
        current_app.logger.error(f"Error saving player stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Routes to check if stats exist and retrieve them

@bp.route('/api/stats/check/index', methods=['GET'])
@login_required
def check_index_stats():
    """Check if index stats exist for the current team organization."""
    team_organization_id = current_user.team_organization_id
    
    # Get filter parameters from query string
    filter_params = request.args.get('filter_params')
    
    # Get version if specified
    version = request.args.get('version')
    
    query = IndexStats.query.filter_by(team_organization_id=team_organization_id)
    
    # If version is specified, filter by version
    if version:
        query = query.filter_by(version=version)
    else:
        # Otherwise get the latest version
        query = query.order_by(IndexStats.version.desc())
    
    # If filter parameters are provided, try to match them
    if filter_params:
        try:
            filter_params_dict = json.loads(filter_params)
            # This is a simplified approach - in a real implementation, you might want to
            # do a more sophisticated comparison of filter parameters
            stats = query.filter(IndexStats.filter_params.contains(filter_params_dict)).first()
        except json.JSONDecodeError:
            stats = None
    else:
        stats = query.first()
    
    if stats:
        return jsonify({
            'exists': True,
            'id': stats.id,
            'stats_data': stats.stats_data,
            'updated_at': stats.updated_at.isoformat(),
            'version': stats.version
        }), 200
    else:
        return jsonify({'exists': False}), 200

@bp.route('/api/stats/check/team', methods=['GET'])
@login_required
def check_team_stats():
    """Check if team stats exist for the current team organization."""
    team_organization_id = current_user.team_organization_id
    
    # Get filter parameters from query string
    filter_params = request.args.get('filter_params')
    
    # Get version if specified
    version = request.args.get('version')
    
    query = TeamStats.query.filter_by(team_organization_id=team_organization_id)
    
    # If version is specified, filter by version
    if version:
        query = query.filter_by(version=version)
    else:
        # Otherwise get the latest version
        query = query.order_by(TeamStats.version.desc())
    
    # If filter parameters are provided, try to match them
    if filter_params:
        try:
            filter_params_dict = json.loads(filter_params)
            stats = query.filter(TeamStats.filter_params.contains(filter_params_dict)).first()
        except json.JSONDecodeError:
            stats = None
    else:
        stats = query.first()
    
    if stats:
        return jsonify({
            'exists': True,
            'id': stats.id,
            'stats_data': stats.stats_data,
            'updated_at': stats.updated_at.isoformat(),
            'version': stats.version
        }), 200
    else:
        return jsonify({'exists': False}), 200

@bp.route('/api/stats/check/game/<int:game_id>', methods=['GET'])
@login_required
def check_game_stats(game_id):
    """Check if game stats exist for the specified game."""
    team_organization_id = current_user.team_organization_id
    
    # Get filter parameters from query string
    filter_params = request.args.get('filter_params')
    
    # Get version if specified
    version = request.args.get('version')
    
    query = GameStats.query.filter_by(
        game_id=game_id,
        team_organization_id=team_organization_id
    )
    
    # If version is specified, filter by version
    if version:
        query = query.filter_by(version=version)
    else:
        # Otherwise get the latest version
        query = query.order_by(GameStats.version.desc())
    
    # If filter parameters are provided, try to match them
    if filter_params:
        try:
            filter_params_dict = json.loads(filter_params)
            stats = query.filter(GameStats.filter_params.contains(filter_params_dict)).first()
        except json.JSONDecodeError:
            stats = None
    else:
        stats = query.first()
    
    if stats:
        return jsonify({
            'exists': True,
            'id': stats.id,
            'stats_data': stats.stats_data,
            'updated_at': stats.updated_at.isoformat(),
            'version': stats.version
        }), 200
    else:
        return jsonify({'exists': False}), 200

@bp.route('/api/stats/check/player/<int:player_id>', methods=['GET'])
@login_required
def check_player_stats(player_id):
    """Check if player stats exist for the specified player."""
    team_organization_id = current_user.team_organization_id
    
    # Get game_id if provided
    game_id = request.args.get('game_id')
    
    # Get filter parameters from query string
    filter_params = request.args.get('filter_params')
    
    # Get version if specified
    version = request.args.get('version')
    
    query = PlayerStats.query.filter_by(
        player_id=player_id,
        team_organization_id=team_organization_id
    )
    
    if game_id:
        query = query.filter_by(game_id=game_id)
    else:
        query = query.filter_by(game_id=None)
    
    # If version is specified, filter by version
    if version:
        query = query.filter_by(version=version)
    else:
        # Otherwise get the latest version
        query = query.order_by(PlayerStats.version.desc())
    
    # If filter parameters are provided, try to match them
    if filter_params:
        try:
            filter_params_dict = json.loads(filter_params)
            stats = query.filter(PlayerStats.filter_params.contains(filter_params_dict)).first()
        except json.JSONDecodeError:
            stats = None
    else:
        stats = query.first()
    
    if stats:
        return jsonify({
            'exists': True,
            'id': stats.id,
            'stats_data': stats.stats_data,
            'updated_at': stats.updated_at.isoformat(),
            'version': stats.version
        }), 200
    else:
        return jsonify({'exists': False}), 200

# Routes for managing saved stats

@bp.route('/stats/manage', methods=['GET'])
@login_required
@admin_required
def manage_stats():
    """UI for managing saved stats."""
    team_organization_id = current_user.team_organization_id
    
    # Get all stats for the current team organization
    index_stats = IndexStats.query.filter_by(team_organization_id=team_organization_id).order_by(IndexStats.version.desc()).all()
    team_stats = TeamStats.query.filter_by(team_organization_id=team_organization_id).order_by(TeamStats.version.desc()).all()
    game_stats = GameStats.query.filter_by(team_organization_id=team_organization_id).order_by(GameStats.version.desc()).all()
    player_stats = PlayerStats.query.filter_by(team_organization_id=team_organization_id).order_by(PlayerStats.version.desc()).all()
    
    return render_template('stats/manage.html',
                          index_stats=index_stats,
                          team_stats=team_stats,
                          game_stats=game_stats,
                          player_stats=player_stats)

@bp.route('/stats/delete/<string:stats_type>/<int:stats_id>', methods=['POST'])
@login_required
@admin_required
def delete_stats(stats_type, stats_id):
    """Delete saved stats."""
    team_organization_id = current_user.team_organization_id
    
    try:
        if stats_type == 'index':
            stats = IndexStats.query.filter_by(id=stats_id, team_organization_id=team_organization_id).first()
        elif stats_type == 'team':
            stats = TeamStats.query.filter_by(id=stats_id, team_organization_id=team_organization_id).first()
        elif stats_type == 'game':
            stats = GameStats.query.filter_by(id=stats_id, team_organization_id=team_organization_id).first()
        elif stats_type == 'player':
            stats = PlayerStats.query.filter_by(id=stats_id, team_organization_id=team_organization_id).first()
        else:
            return jsonify({'error': 'Invalid stats type'}), 400
        
        if not stats:
            return jsonify({'error': 'Stats not found or access denied'}), 404
        
        db.session.delete(stats)
        db.session.commit()
        
        return jsonify({'message': 'Stats deleted successfully'}), 200
    except Exception as e:
        current_app.logger.error(f"Error deleting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/stats/compare/<string:stats_type>/<int:stats_id1>/<int:stats_id2>', methods=['GET'])
@login_required
@admin_required
def compare_stats(stats_type, stats_id1, stats_id2):
    """Compare two versions of saved stats."""
    team_organization_id = current_user.team_organization_id
    
    try:
        if stats_type == 'index':
            stats1 = IndexStats.query.filter_by(id=stats_id1, team_organization_id=team_organization_id).first()
            stats2 = IndexStats.query.filter_by(id=stats_id2, team_organization_id=team_organization_id).first()
        elif stats_type == 'team':
            stats1 = TeamStats.query.filter_by(id=stats_id1, team_organization_id=team_organization_id).first()
            stats2 = TeamStats.query.filter_by(id=stats_id2, team_organization_id=team_organization_id).first()
        elif stats_type == 'game':
            stats1 = GameStats.query.filter_by(id=stats_id1, team_organization_id=team_organization_id).first()
            stats2 = GameStats.query.filter_by(id=stats_id2, team_organization_id=team_organization_id).first()
        elif stats_type == 'player':
            stats1 = PlayerStats.query.filter_by(id=stats_id1, team_organization_id=team_organization_id).first()
            stats2 = PlayerStats.query.filter_by(id=stats_id2, team_organization_id=team_organization_id).first()
        else:
            return jsonify({'error': 'Invalid stats type'}), 400
        
        if not stats1 or not stats2:
            return jsonify({'error': 'One or both stats not found or access denied'}), 404
        
        # Compare the stats data
        comparison = compare_stats_data(stats1.stats_data, stats2.stats_data)
        
        return render_template('stats/compare.html',
                              stats1=stats1,
                              stats2=stats2,
                              comparison=comparison,
                              stats_type=stats_type)
    except Exception as e:
        current_app.logger.error(f"Error comparing stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

def compare_stats_data(data1, data2):
    """Compare two stats data objects and return the differences."""
    comparison = {
        'added': {},
        'removed': {},
        'changed': {}
    }
    
    # Find keys in data1 that are not in data2 or have different values
    for key, value in data1.items():
        if key not in data2:
            comparison['removed'][key] = value
        elif data2[key] != value:
            comparison['changed'][key] = {
                'old': value,
                'new': data2[key]
            }
    
    # Find keys in data2 that are not in data1
    for key, value in data2.items():
        if key not in data1:
            comparison['added'][key] = value
    
    return comparison