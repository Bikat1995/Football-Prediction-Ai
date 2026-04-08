import pandas as pd
import numpy as np
import joblib
import os

class FeatureBuilderLive:
    """Bridges live API data to model features"""
    
    def __init__(self, model_path='ultimate_combined_model.pkl'):
        if os.path.exists(model_path):
            model_data = joblib.load(model_path)
            self.feature_names = model_data['feature_names']
            self.scaler = model_data.get('scaler')
            print(f"Loaded model features: {len(self.feature_names)} features expected")
        else:
            self.feature_names = []
            self.scaler = None
            print(f"Model file {model_path} not found! Feature building will be limited.")

    def build_features(self, home_team_matches, away_team_matches, current_odds):
        """
        Builds feature vector for a single match
        home_team_matches: list of last N matches for home team from API-Football
        away_team_matches: list of last N matches for away team from API-Football
        current_odds: dict with 'home', 'draw', 'away' odds
        """
        
        # 1. Calculate Rolling Stats for Home Team
        home_goals = []
        home_shots = []
        home_points = []
        
        for m in home_team_matches:
            # Determine if team was home or away in that match
            is_home = m['teams']['home']['id'] == home_team_matches[0]['teams']['home']['id'] # Assuming first match defines the team
            goals = m['goals']['home'] if is_home else m['goals']['away']
            home_goals.append(goals)
            
            # Points: 3 for win, 1 for draw, 0 for loss
            result = m['teams']['home']['winner'] if is_home else m['teams']['away']['winner']
            if result is True:
                home_points.append(3)
            elif result is None:
                home_points.append(1)
            else:
                home_points.append(0)
                
            # Shots (if available in API response - usually not in basic fixture list, requires fixture statistics call)
            # For now use defaults or placeholders if not present
            home_shots.append(5) # Default/placeholder
            
        # 2. Calculate Rolling Stats for Away Team
        away_goals = []
        away_shots = []
        away_points = []
        
        for m in away_team_matches:
            is_home = m['teams']['home']['id'] == away_team_matches[0]['teams']['away']['id']
            goals = m['goals']['home'] if is_home else m['goals']['away']
            away_goals.append(goals)
            
            result = m['teams']['home']['winner'] if is_home else m['teams']['away']['winner']
            if result is True:
                away_points.append(3)
            elif result is None:
                away_points.append(1)
            else:
                away_points.append(0)
            
            away_shots.append(5) # Default/placeholder

        # 3. Create Feature Dictionary
        features = {}
        
        # Core Rolling Features
        features['home_goals_rolling'] = np.mean(home_goals) if home_goals else 0
        features['away_goals_rolling'] = np.mean(away_goals) if away_goals else 0
        features['home_shots_rolling'] = np.mean(home_shots) if home_shots else 0
        features['away_shots_rolling'] = np.mean(away_shots) if away_shots else 0
        features['home_form'] = np.mean(home_points) if home_points else 0
        features['away_form'] = np.mean(away_points) if away_points else 0
        
        # Core Odds Features
        h_odds = current_odds.get('home', 2.0)
        d_odds = current_odds.get('draw', 3.0)
        a_odds = current_odds.get('away', 3.0)
        
        features['home_odds'] = h_odds
        features['draw_odds'] = d_odds
        features['away_odds'] = a_odds
        features['odds_ratio'] = a_odds / h_odds if h_odds != 0 else 1
        features['odds_diff'] = a_odds - h_odds
        features['implied_prob_home'] = 1 / h_odds if h_odds != 0 else 0.5
        features['implied_prob_draw'] = 1 / d_odds if d_odds != 0 else 0.33
        features['implied_prob_away'] = 1 / a_odds if a_odds != 0 else 0.33
        
        # Combined Rolling Features
        features['goal_diff_rolling'] = features['home_goals_rolling'] - features['away_goals_rolling']
        features['total_goals_rolling'] = features['home_goals_rolling'] + features['away_goals_rolling']
        
        # Meta features
        features['is_scattered'] = 0
        features['is_yearly'] = 0
        features['is_extras'] = 0
        
        # 4. Align with Model's Feature Names
        # Fill all other features with 0 or reasonable defaults
        final_features = {}
        for col in self.feature_names:
            if col in features:
                final_features[col] = features[col]
            else:
                # Default for other bookmaker odds if missing
                if any(x in col for x in ['H', 'D', 'A']) and len(col) <= 5:
                    if col.endswith('H'): final_features[col] = h_odds
                    elif col.endswith('D'): final_features[col] = d_odds
                    elif col.endswith('A'): final_features[col] = a_odds
                    else: final_features[col] = 0
                else:
                    final_features[col] = 0
                    
        # Convert to DataFrame in correct order
        df = pd.DataFrame([final_features])[self.feature_names]
        
        # 5. Scale if scaler exists
        if self.scaler:
            X_scaled = self.scaler.transform(df)
            return X_scaled
        
        return df.values

if __name__ == "__main__":
    builder = FeatureBuilderLive()
    # Test with dummy data
    home_matches = [{'goals': {'home': 2, 'away': 1}, 'teams': {'home': {'id': 1, 'winner': True}, 'away': {'id': 2, 'winner': False}}}]
    away_matches = [{'goals': {'home': 0, 'away': 1}, 'teams': {'home': {'id': 3, 'winner': False}, 'away': {'id': 1, 'winner': True}}}]
    odds = {'home': 2.1, 'draw': 3.4, 'away': 3.8}
    
    vec = builder.build_features(home_matches, away_matches, odds)
    print(f"Feature vector shape: {vec.shape}")
