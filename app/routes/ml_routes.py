# app/routes/ml_routes.py

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.ml.player_prediction import PlayerPerformancePredictor
from app.ml.line_optimizer import LineOptimizer
from app.models.player import Player
from app.models.game import Game
from app.models.team import Team

bp = Blueprint('ml', __name__, url_prefix='/ml')

@bp.route('/player-prediction/<int:player_id>', methods=['GET'])
@login_required
def player_prediction(player_id):
    """
    Get performance predictions for a player
    """
    # Check if player exists
    player = Player.query.get_or_404(player_id)
    
    # Get upcoming game ID if provided
    upcoming_game_id = request.args.get('game_id', type=int)
    
    # Initialize predictor
    predictor = PlayerPerformancePredictor()
    
    # Get predictions
    predictions = predictor.predict(player_id, upcoming_game_id)
    
    if predictions is None:
        return jsonify({
            'error': 'Not enough historical data for this player'
        }), 400
        
    # Get player details
    player_details = {
        'id': player.id,
        'name': f"{player.first_name} {player.last_name}",
    }
    
    # Get game details if provided
    game_details = None
    if upcoming_game_id:
        game = Game.query.get(upcoming_game_id)
        if game:
            game_details = {
                'id': game.id,
                'opponent': game.opponent,
                'date': game.date.strftime('%Y-%m-%d')
            }
    
    # Return predictions
    return jsonify({
        'player': player_details,
        'game': game_details,
        'predictions': predictions
    })

@bp.route('/line-optimizer/<int:team_id>', methods=['GET'])
@login_required
def line_optimizer(team_id):
    """
    Get suggested lines for a team
    """
    # Check if team exists
    team = Team.query.get_or_404(team_id)
    
    # Get parameters
    num_lines = request.args.get('num_lines', 3, type=int)
    players_per_line = request.args.get('players_per_line', 7, type=int)
    situation = request.args.get('situation', 'offense')
    
    # Initialize optimizer
    optimizer = LineOptimizer()
    
    # Get suggested lines
    suggested_lines = optimizer.suggest_lines(
        team_id, 
        num_lines=num_lines,
        players_per_line=players_per_line,
        situation=situation
    )
    
    if not suggested_lines:
        return jsonify({
            'error': 'Not enough data to suggest lines'
        }), 400
        
    # Return suggested lines
    return jsonify({
        'team': {
            'id': team.id,
            'name': team.name
        },
        'situation': situation,
        'suggested_lines': suggested_lines
    })

@bp.route('/train', methods=['POST'])
@login_required
def train_models():
    """
    Manually trigger model training
    """
    # Check if user has permission (admin)
    if not current_user.is_admin:
        return jsonify({'error': 'Permission denied'}), 403
        
    # Get team ID if provided
    team_id = request.json.get('team_id')
    
    # Train player prediction model
    player_predictor = PlayerPerformancePredictor()
    player_success = player_predictor.train(team_id)
    
    # Train line optimizer model
    line_optimizer = LineOptimizer()
    line_success = line_optimizer.train(team_id)
    
    return jsonify({
        'player_prediction_trained': player_success,
        'line_optimizer_trained': line_success
    })