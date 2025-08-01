# app/ml/line_optimizer.py

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib
import os
from itertools import combinations
from app.ml.data_processor import DataProcessor
from app.models.player import Player
from app.models.point import Point
from app.models.game import Game
from flask import current_app

class LineOptimizer:
    def __init__(self):
        self.model_dir = os.path.join(current_app.root_path, 'ml', 'models')
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = os.path.join(self.model_dir, 'line_optimizer_model.joblib')
        
        # Load model if it exists
        if os.path.exists(self.model_path):
            try:
                saved_data = joblib.load(self.model_path)
                self.model = saved_data['kmeans']
                self.scaler = saved_data['scaler']
                self.trained = True
            except:
                self.model = KMeans(n_clusters=3, random_state=42)
                self.scaler = StandardScaler()
                self.trained = False
        else:
            self.model = KMeans(n_clusters=3, random_state=42)
            self.scaler = StandardScaler()
            self.trained = False
            
    def _get_player_vectors(self, team_name):
        """
        Generate feature vectors for each player on the team
        
        Args:
            team_name: Name of the team
            
        Returns:
            DataFrame with player IDs and feature vectors
        """
        # Get all players on the team
        players = Player.query.filter_by(team=team_name).all()
        
        if not players:
            return None
            
        player_vectors = []
        for player in players:
            # Get player's historical data
            player_data = DataProcessor.get_player_historical_data(player.id)
            
            if player_data is None or len(player_data) < 3:
                continue
                
            # Calculate average stats
            avg_goals = player_data['goals'].mean()
            avg_assists = player_data['assists'].mean()
            avg_completions = player_data['completions'].mean()
            avg_throwaways = player_data['throwaways'].mean()
            avg_blocks = player_data['blocks'].mean()
            avg_points_played = player_data['points_played'].mean()
            avg_per = player_data['per'].mean()
            
            # Calculate completion percentage
            total_throws = avg_completions + avg_throwaways
            completion_pct = (avg_completions / total_throws * 100) if total_throws > 0 else 0
            
            # Calculate points per game
            points_per_game = avg_goals + avg_assists
            
            # Create player vector
            player_vector = {
                'player_id': player.id,
                'name': player.name,
                'goals': avg_goals,
                'assists': avg_assists,
                'blocks': avg_blocks,
                'completion_pct': completion_pct,
                'points_per_game': points_per_game,
                'points_played': avg_points_played,
                'per': avg_per
            }
            
            player_vectors.append(player_vector)
            
        return pd.DataFrame(player_vectors)
        
    def train(self, team_name):
        """
        Train the model using team lineup data
        
        Args:
            team_name: Name of the team
            
        Returns:
            True if training was successful, False otherwise
        """
        # Get player vectors
        player_vectors = self._get_player_vectors(team_name)
        
        if player_vectors is None or len(player_vectors) < 7:  # Need minimum players for a line
            return False
            
        # Scale the features
        features = player_vectors.drop(['player_id', 'name'], axis=1)
        scaled_features = self.scaler.fit_transform(features)
        
        # Train the clustering model
        self.model.fit(scaled_features)
        
        # Save the model
        joblib.dump({
            'kmeans': self.model,
            'scaler': self.scaler
        }, self.model_path)
        
        self.trained = True
        
        return True
        
    def _evaluate_line(self, line_players, player_vectors, situation='offense'):
        """
        Evaluate a potential line based on player stats and balance
        
        Args:
            line_players: List of player vectors for the line
            player_vectors: DataFrame with all player vectors
            situation: 'offense' or 'defense'
            
        Returns:
            Score for the line
        """
        if len(line_players) < 7:
            return 0  # Not enough players
            
        # Extract relevant stats based on situation
        if situation == 'offense':
            # For offense, prioritize goals, assists, completion percentage, PER
            total_goals = sum(p['goals'] for p in line_players)
            total_assists = sum(p['assists'] for p in line_players)
            avg_completion = np.mean([p['completion_pct'] for p in line_players])
            avg_per = np.mean([p['per'] for p in line_players])
            
            # Calculate offensive score
            score = (total_goals * 0.25) + (total_assists * 0.25) + (avg_completion * 0.25) + (avg_per * 0.25)
            
        else:  # defense
            # For defense, prioritize blocks, PER, and athletic metrics
            total_blocks = sum(p['blocks'] for p in line_players)
            avg_per = np.mean([p['per'] for p in line_players])
            
            # Calculate defensive score
            score = (total_blocks * 0.5) + (avg_per * 0.5)
            
        # Bonus for balanced line (players from different clusters)
        player_ids = [p['player_id'] for p in line_players]
        player_rows = player_vectors[player_vectors['player_id'].isin(player_ids)]
        
        if len(player_rows) < 7:
            return score
            
        features = player_rows.drop(['player_id', 'name'], axis=1)
        scaled_features = self.scaler.transform(features)
        clusters = self.model.predict(scaled_features)
        
        # Count unique clusters
        unique_clusters = len(set(clusters))
        
        # Bonus for having players from different clusters (skill diversity)
        cluster_bonus = unique_clusters / 3.0  # Normalized by max clusters
        
        return score * (1 + cluster_bonus * 0.2)  # 20% bonus for perfect diversity
        
    def suggest_lines(self, team_name, num_lines=3, players_per_line=7, situation='offense'):
        """
        Suggest optimal lines for a given situation
        
        Args:
            team_name: Name of the team
            num_lines: Number of lines to suggest
            players_per_line: Number of players per line
            situation: 'offense' or 'defense'
            
        Returns:
            List of suggested lines with player IDs and names
        """
        if not self.trained:
            success = self.train(team_name)
            if not success:
                return []
                
        # Get player vectors
        player_vectors_df = self._get_player_vectors(team_name)
        
        if player_vectors_df is None:
            return []
            
        # Convert to list of dicts for easier processing
        player_vectors = player_vectors_df.to_dict('records')
        
        # Generate all possible line combinations
        all_players = [p for p in player_vectors]
        possible_lines = list(combinations(all_players, players_per_line))
        
        if not possible_lines:
            return []
            
        # Evaluate each line
        line_scores = []
        for line in possible_lines:
            score = self._evaluate_line(line, player_vectors_df, situation)
            line_scores.append((line, score))
            
        # Sort by score and get top lines
        line_scores.sort(key=lambda x: x[1], reverse=True)
        top_lines = line_scores[:num_lines]
        
        # Format results
        results = []
        for line, score in top_lines:
            line_info = {
                'score': round(score, 2),
                'players': [{'id': p['player_id'], 'name': p['name']} for p in line]
            }
            results.append(line_info)
            
        return results