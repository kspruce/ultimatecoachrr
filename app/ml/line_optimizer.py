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
from app.models.stats import Stats
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
                self.model = joblib.load(self.model_path)
                self.trained = True
            except:
                self.model = KMeans(n_clusters=3, random_state=42)
                self.trained = False
        else:
            self.model = KMeans(n_clusters=3, random_state=42)
            self.trained = False
            
        self.scaler = StandardScaler()
            
    def _get_player_vectors(self, team_id):
        """
        Generate feature vectors for each player on the team
        
        Args:
            team_id: ID of the team
            
        Returns:
            DataFrame with player IDs and feature vectors
        """
        # Get all players on the team
        players = Player.query.filter_by(team_id=team_id).all()
        
        if not players:
            return None
            
        player_vectors = []
        for player in players:
            # Get player's average stats
            avg_stats = Stats.query.filter_by(player_id=player.id)\
                .join(Game, Stats.game_id == Game.id)\
                .order_by(Game.date.desc())\
                .limit(10).all()
                
            if not avg_stats:
                continue
                
            # Calculate average stats
            goals = np.mean([s.goals if hasattr(s, 'goals') else 0 for s in avg_stats])
            assists = np.mean([s.assists if hasattr(s, 'assists') else 0 for s in avg_stats])
            completions = np.mean([s.completions if hasattr(s, 'completions') else 0 for s in avg_stats])
            throwaways = np.mean([s.throwaways if hasattr(s, 'throwaways') else 0 for s in avg_stats])
            blocks = np.mean([s.blocks if hasattr(s, 'blocks') else 0 for s in avg_stats])
            points_played = np.mean([s.points_played if hasattr(s, 'points_played') else 0 for s in avg_stats])
            
            # Calculate derived metrics
            completion_pct = completions / (completions + throwaways) if (completions + throwaways) > 0 else 0
            points_per_game = goals + assists
            
            # Create player vector
            player_vector = {
                'player_id': player.id,
                'name': f"{player.first_name} {player.last_name}",
                'goals': goals,
                'assists': assists,
                'blocks': blocks,
                'completion_pct': completion_pct,
                'points_per_game': points_per_game,
                'points_played': points_played
            }
            
            player_vectors.append(player_vector)
            
        return pd.DataFrame(player_vectors)
        
    def train(self, team_id):
        """
        Train the model using team lineup data
        
        Args:
            team_id: ID of the team
            
        Returns:
            True if training was successful, False otherwise
        """
        # Get team lineup data
        lineup_data = DataProcessor.get_team_lineup_data(team_id)
        
        if lineup_data is None or len(lineup_data) < 10:  # Need minimum data
            return False
            
        # Get player vectors
        player_vectors = self._get_player_vectors(team_id)
        
        if player_vectors is None:
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
            # For offense, prioritize goals, assists, completion percentage
            total_goals = sum(p['goals'] for p in line_players)
            total_assists = sum(p['assists'] for p in line_players)
            avg_completion = np.mean([p['completion_pct'] for p in line_players])
            
            # Calculate offensive score
            score = (total_goals * 0.3) + (total_assists * 0.3) + (avg_completion * 0.4)
            
        else:  # defense
            # For defense, prioritize blocks and athletic metrics
            total_blocks = sum(p['blocks'] for p in line_players)
            
            # Calculate defensive score
            score = total_blocks
            
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
        
    def suggest_lines(self, team_id, num_lines=3, players_per_line=7, situation='offense'):
        """
        Suggest optimal lines for a given situation
        
        Args:
            team_id: ID of the team
            num_lines: Number of lines to suggest
            players_per_line: Number of players per line
            situation: 'offense' or 'defense'
            
        Returns:
            List of suggested lines with player IDs and names
        """
        if not self.trained:
            success = self.train(team_id)
            if not success:
                return []
                
        # Get player vectors
        player_vectors_df = self._get_player_vectors(team_id)
        
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