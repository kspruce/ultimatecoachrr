# app/ml/player_prediction.py

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib
import os
from datetime import datetime
from app.ml.data_processor import DataProcessor
from app.models.player import Player
from app.models.game import Game
from flask import current_app

class PlayerPerformancePredictor:
    def __init__(self):
        self.model_dir = os.path.join(current_app.root_path, 'ml', 'models')
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = os.path.join(self.model_dir, 'player_performance_model.joblib')
        
        # Create a pipeline with preprocessing and model
        self.pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('model', RandomForestRegressor(n_estimators=100, random_state=42))
        ])
        
        # Load model if it exists
        if os.path.exists(self.model_path):
            try:
                self.pipeline = joblib.load(self.model_path)
                self.trained = True
            except:
                self.trained = False
        else:
            self.trained = False
            
    def _prepare_features(self, player_data):
        """
        Prepare features from player data
        
        Args:
            player_data: DataFrame with player stats
            
        Returns:
            X: Feature matrix
            y: Target values (dict of different performance metrics)
        """
        if player_data is None or len(player_data) < 3:  # Need minimum data
            return None, None
            
        # Calculate rolling averages
        player_data = player_data.sort_values('game_date')
        
        # Add rolling averages for key stats (last 3 games)
        for stat in ['goals', 'assists', 'completions', 'throwaways', 'blocks']:
            player_data[f'{stat}_rolling_avg'] = player_data[stat].rolling(window=3, min_periods=1).mean()
            
        # Calculate completion percentage
        player_data['completion_pct'] = (player_data['completions'] / 
                                        (player_data['completions'] + player_data['throwaways'])) * 100
        player_data['completion_pct'] = player_data['completion_pct'].fillna(0)
        
        # Calculate points per game
        player_data['points_per_game'] = (player_data['goals'] + player_data['assists'])
        
        # Feature engineering
        player_data['days_since_practice'] = (player_data['game_date'] - 
                                             player_data['recent_practices_attended']).dt.days
        
        # Drop non-feature columns
        X = player_data.drop(['game_id', 'game_date', 'opponent'], axis=1)
        
        # Convert categorical variables to dummy variables
        X = pd.get_dummies(X, columns=['is_home', 'tournament_game'])
        
        # Define target variables
        y = {
            'goals': player_data['goals'],
            'assists': player_data['assists'],
            'blocks': player_data['blocks'],
            'points_per_game': player_data['points_per_game']
        }
        
        return X, y
        
    def train(self, team_id=None):
        """
        Train the model using historical player data
        
        Args:
            team_id: Optional team ID to filter players
            
        Returns:
            True if training was successful, False otherwise
        """
        # Get all players (optionally filtered by team)
        if team_id:
            players = Player.query.filter_by(team_id=team_id).all()
        else:
            players = Player.query.all()
            
        if not players:
            return False
            
        # Collect data for all players
        all_player_data = []
        for player in players:
            player_data = DataProcessor.get_player_historical_data(player.id)
            if player_data is not None and len(player_data) >= 3:  # Need minimum data
                all_player_data.append(player_data)
                
        if not all_player_data:
            return False
            
        # Combine all player data
        combined_data = pd.concat(all_player_data, ignore_index=True)
        
        # Prepare features
        X, y_dict = self._prepare_features(combined_data)
        
        if X is None:
            return False
            
        # Train a model for each target variable
        self.models = {}
        for target_name, y in y_dict.items():
            # Create a pipeline with preprocessing and model
            pipeline = Pipeline([
                ('scaler', StandardScaler()),
                ('model', RandomForestRegressor(n_estimators=100, random_state=42))
            ])
            
            # Train the model
            pipeline.fit(X, y)
            
            # Save the model
            self.models[target_name] = pipeline
            
        # Save all models
        joblib.dump(self.models, self.model_path)
        self.trained = True
        
        return True
        
    def predict(self, player_id, upcoming_game_id=None):
        """
        Predict performance for a player in an upcoming game
        
        Args:
            player_id: ID of the player
            upcoming_game_id: ID of the upcoming game (optional)
            
        Returns:
            Dictionary with predicted performance metrics
        """
        if not self.trained:
            success = self.train()
            if not success:
                return None
                
        # Get player's historical data
        player_data = DataProcessor.get_player_historical_data(player_id)
        
        if player_data is None or len(player_data) < 3:  # Need minimum data
            return None
            
        # Prepare features for the most recent game
        latest_data = player_data.iloc[-1:].copy()
        
        # If we have info about the upcoming game, use it
        if upcoming_game_id:
            upcoming_game = Game.query.get(upcoming_game_id)
            if upcoming_game:
                latest_data['opponent'] = upcoming_game.opponent
                latest_data['is_home'] = upcoming_game.is_home if hasattr(upcoming_game, 'is_home') else True
                latest_data['tournament_game'] = upcoming_game.tournament_id is not None
                
        # Prepare features
        X, _ = self._prepare_features(player_data)
        if X is None:
            return None
            
        # Get the last row as the prediction input
        X_pred = X.iloc[-1:].copy()
        
        # Make predictions for each target
        predictions = {}
        for target_name, model in self.models.items():
            pred_value = model.predict(X_pred)[0]
            predictions[target_name] = round(max(0, pred_value), 2)  # Ensure non-negative and round
            
        return predictions