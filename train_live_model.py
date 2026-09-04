import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
import datetime

print("Loading historical data for live-compatible model...")
df = pd.read_csv('global_football_historical_master.csv')
df['match_date'] = pd.to_datetime(df['match_date'], format='%d/%m/%Y', errors='coerce')
df = df.dropna(subset=['match_date']).sort_values('match_date').reset_index(drop=True)

team_histories = {}
X, y = [], []

def safe_float(val, default=0.0):
    try: return float(val)
    except: return default

def get_winner(hg, ag):
    if hg > ag: return 2
    if hg == ag: return 1
    return 0

# We only track goals scored, goals conceded, and points
features_list = ['goals_scored', 'goals_conceded', 'points']

for idx, row in df.iterrows():
    home = row['home_team']
    away = row['away_team']
    
    if home not in team_histories:
        team_histories[home] = {f: [] for f in features_list}
    if away not in team_histories:
        team_histories[away] = {f: [] for f in features_list}
        
    def get_rolling(team_name, n=6):
        hist = team_histories[team_name]
        if len(hist['goals_scored']) == 0:
            return [1.2, 1.2, 1.2] # Fallback for new teams
        return [np.mean(hist[f][-n:]) for f in features_list]
        
    h_rolling = get_rolling(home)
    a_rolling = get_rolling(away)
    
    odds_h = safe_float(row['pre_match_odds_home'], 2.5)
    odds_d = safe_float(row['pre_match_odds_draw'], 3.0)
    odds_a = safe_float(row['pre_match_odds_away'], 2.8)
    
    # Cap odds to reasonable limits to avoid outliers
    odds_h = min(odds_h, 20.0)
    odds_d = min(odds_d, 10.0)
    odds_a = min(odds_a, 20.0)
    
    feature_vector = h_rolling + a_rolling + [odds_h, odds_d, odds_a]
    
    hg = safe_float(row['home_goals'])
    ag = safe_float(row['away_goals'])
    winner = get_winner(hg, ag)
    
    if len(team_histories[home]['goals_scored']) >= 3 and len(team_histories[away]['goals_scored']) >= 3:
        X.append(feature_vector)
        y.append(winner)
        
    # Update histories for next time
    team_histories[home]['goals_scored'].append(hg)
    team_histories[home]['goals_conceded'].append(ag)
    team_histories[home]['points'].append(3.0 if hg > ag else 1.0 if hg == ag else 0.0)

    team_histories[away]['goals_scored'].append(ag)
    team_histories[away]['goals_conceded'].append(hg)
    team_histories[away]['points'].append(3.0 if ag > hg else 1.0 if hg == ag else 0.0)

X = np.array(X)
y = np.array(y)

print(f"Generated {len(X)} valid training samples.")

feature_names = [
    'h_goals_scored_avg', 'h_goals_conceded_avg', 'h_pts_avg',
    'a_goals_scored_avg', 'a_goals_conceded_avg', 'a_pts_avg',
    'odds_h', 'odds_d', 'odds_a'
]

model = xgb.XGBClassifier(
    n_estimators=250, learning_rate=0.03, max_depth=4,
    objective='multi:softprob', eval_metric='mlogloss', random_state=42
)
model.fit(X, y)
acc = np.mean(model.predict(X) == y)
print(f"Training Accuracy: {acc:.2%}")

model_data = {
    'model': model,
    'feature_names': feature_names,
    'total_samples_trained': len(X),
    'last_trained_date': datetime.datetime.now().isoformat(),
    'version': 'live_compatible_v1',
    'classes': ['Away', 'Draw', 'Home'],
    'team_histories': team_histories
}
joblib.dump(model_data, 'models/live_compatible_model.pkl')
print("Saved to models/live_compatible_model.pkl")
