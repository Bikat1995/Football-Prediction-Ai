import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
import datetime
import csv

print("=== DAILY INCREMENTAL TRAINING ===")
MODEL_PATH = 'models/live_compatible_model.pkl'

if not os.path.exists(MODEL_PATH):
    print("Base model not found! Please run train_live_model.py first.")
    exit(1)

model_data = joblib.load(MODEL_PATH)
model = model_data['model']
team_histories = model_data['team_histories']
total_trained = model_data.get('total_samples_trained', 0)

print(f"Loaded base model. Currently trained on {total_trained} samples.")

# Load collected live data
if not os.path.exists('collected_training_data.csv'):
    print("No new data to train on.")
    exit(0)

df = pd.read_csv('collected_training_data.csv')
if 'Trained' not in df.columns:
    df['Trained'] = False

# Filter untrained matches
new_matches = df[df['Trained'] == False]
if len(new_matches) == 0:
    print("No new matches to train on today.")
    exit(0)

print(f"Found {len(new_matches)} new matches for incremental training.")

def get_winner(hg, ag):
    if hg > ag: return 2
    if hg == ag: return 1
    return 0

features_list = ['goals_scored', 'goals_conceded', 'points']
X_new, y_new = [], []

for idx, row in new_matches.iterrows():
    home = row['Home_Name']
    away = row['Away_Name']
    hg = float(row['Home_Goals'])
    ag = float(row['Away_Goals'])
    
    if home not in team_histories:
        team_histories[home] = {f: [] for f in features_list}
    if away not in team_histories:
        team_histories[away] = {f: [] for f in features_list}
        
    def get_rolling(team_name, n=6):
        hist = team_histories[team_name]
        if len(hist['goals_scored']) == 0:
            return [1.2, 1.2, 1.2]
        return [np.mean(hist[f][-n:]) for f in features_list]
        
    h_rolling = get_rolling(home)
    a_rolling = get_rolling(away)
    
    # We don't have odds stored in collected_training_data.csv, use neutral fallback for training
    # to avoid biasing the model
    odds_h, odds_d, odds_a = 2.5, 3.0, 2.8 
    
    feature_vector = h_rolling + a_rolling + [odds_h, odds_d, odds_a]
    winner = get_winner(hg, ag)
    
    if len(team_histories[home]['goals_scored']) >= 3 and len(team_histories[away]['goals_scored']) >= 3:
        X_new.append(feature_vector)
        y_new.append(winner)
        
    # Update histories with actual match result for future matches
    team_histories[home]['goals_scored'].append(hg)
    team_histories[home]['goals_conceded'].append(ag)
    team_histories[home]['points'].append(3.0 if hg > ag else 1.0 if hg == ag else 0.0)

    team_histories[away]['goals_scored'].append(ag)
    team_histories[away]['goals_conceded'].append(hg)
    team_histories[away]['points'].append(3.0 if ag > hg else 1.0 if hg == ag else 0.0)

    # Mark as trained
    df.at[idx, 'Trained'] = True

if len(X_new) > 0:
    X_new = np.array(X_new)
    y_new = np.array(y_new)
    
    print(f"Training incrementally on {len(X_new)} valid samples...")
    
    # INCREMENTAL TRAINING (This makes the existing model smarter!)
    booster = model.get_booster()
    model.fit(X_new, y_new, xgb_model=booster)
    
    new_total = total_trained + len(X_new)
    model_data['model'] = model
    model_data['team_histories'] = team_histories
    model_data['total_samples_trained'] = new_total
    model_data['last_trained_date'] = datetime.datetime.now().isoformat()
    
    joblib.dump(model_data, MODEL_PATH)
    print(f"Success! Model incrementally updated. Now trained on {new_total} total samples.")
    
    # Save the CSV so we don't train on these again
    df.to_csv('collected_training_data.csv', index=False)
else:
    print("No matches had enough history to train on yet.")
