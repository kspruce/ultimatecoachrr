# app/routes/ml_routes.py

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.ml.player_prediction import PlayerPerformancePredictor
from app.ml.line_optimizer import LineOptimizer
from app.models.player import Player
from app.models.game import Game
from datetime import datetime

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
        'name': player.name,
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

@bp.route('/line-optimizer/<team_name>', methods=['GET'])
@login_required
def line_optimizer(team_name):
    """
    Get suggested lines for a team
    """
    # Validate team name
    if not team_name:
        return jsonify({'error': 'Team name is required'}), 400
    
    # Get parameters
    num_lines = request.args.get('num_lines', 3, type=int)
    players_per_line = request.args.get('players_per_line', 7, type=int)
    situation = request.args.get('situation', 'offense')
    
    # Initialize optimizer
    optimizer = LineOptimizer()
    
    # Get suggested lines
    suggested_lines = optimizer.suggest_lines(
        team_name, 
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
        'team': team_name,
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
        
    # Get team name if provided
    team_name = request.json.get('team_name')
    
    # Train player prediction model
    player_predictor = PlayerPerformancePredictor()
    player_success = player_predictor.train(team_name)
    
    # Train line optimizer model
    line_optimizer = LineOptimizer()
    line_success = line_optimizer.train(team_name)
    
    return jsonify({
        'player_prediction_trained': player_success,
        'line_optimizer_trained': line_success
    })

@bp.route('/player-predictions', methods=['GET'])
@login_required
def player_predictions_view():
    """
    Display the player predictions page
    """
    # Get all players for the current user's team
    players = Player.query.filter_by(team=current_user.team).all()
    
    # Get upcoming games
    upcoming_games = Game.query.filter(
        Game.team == current_user.team,
        Game.date >= datetime.now()
    ).order_by(Game.date).all()
    
    return render_template('ml/player_prediction.html', 
                          players=players, 
                          upcoming_games=upcoming_games)

@bp.route('/line-optimizer', methods=['GET'])
@login_required
def line_optimizer_view():
    """
    Display the line optimizer page
    """
    return render_template('ml/line_optimizer.html')