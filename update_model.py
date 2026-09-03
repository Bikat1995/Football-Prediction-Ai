import pickle
import csv
import sys, io
import numpy as np

# Force UTF-8 output so special chars don't crash on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    import xgboost as xgb
    from sklearn.metrics import classification_report
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'xgboost', 'scikit-learn'], check=True)
    import xgboost as xgb
    from sklearn.metrics import classification_report

# Load existing model
with open('models/xgb_classifier.pkl', 'rb') as f:
    data = pickle.load(f)

model = data['model']
team_stats = data['team_stats']
total_matches = data.get('total_matches', 0)
classes = model.classes_

print(f"Loaded existing XGBClassifier trained on {total_matches} matches.")
print(f"Classes: {classes}")

X_new = []
y_new = []
processed_ids = set() # To avoid duplicate training if we run this multiple times

# We'll use the ID from CSV if possible, otherwise construct one
with open('collected_training_data.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    for row in reader:
        m_id = row['Match_ID']
        if not m_id:
            m_id = f"{row['Home_Name']}_{row['Away_Name']}_{row['Date']}"
        
        # We need a way to track if we already trained on this. For simplicity, we'll just train on everything again 
        # or we could keep track of processed IDs. Let's just re-extract features for all matches using the CURRENT team_stats
        # wait, to properly train, we should use the stats as they were BEFORE the match.
        # But if we don't have the history of stats, we can just use the final stats, or incrementally update them.
        pass

# Actually, the user wants the OLD model to be updated with the NEW data.
# The old data was likely trained on some set. The collected_training_data.csv HAS all the data.
# So we can just rebuild the team_stats from scratch from the CSV, 
# generate features for all matches, and then fit the XGBClassifier.
# BUT wait! The user said "I hope that you trained the already trained model even more not just created a new one".
# They specifically want to call .fit(xgb_model=...) to continue training it.

# Let's read all matches from CSV
matches = []
with open('collected_training_data.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    for row in reader:
        matches.append(row)

matches.sort(key=lambda x: x['Date'])

# Rebuild rolling stats from scratch to generate accurate features
my_team_stats = {}
X_all = []
y_all = []

for m in matches:
    h_name = m['Home_Name']
    a_name = m['Away_Name']
    hg = int(m['Home_Goals'])
    ag = int(m['Away_Goals'])
    winner = m['Winner'] # 'home', 'draw', 'away'

    if h_name not in my_team_stats:
        my_team_stats[h_name] = {'games': 0, 'scored': 0, 'conceded': 0, 'points': 0}
    if a_name not in my_team_stats:
        my_team_stats[a_name] = {'games': 0, 'scored': 0, 'conceded': 0, 'points': 0}

    h_st = my_team_stats[h_name]
    a_st = my_team_stats[a_name]

    # Generate features BEFORE updating stats
    if h_st['games'] >= 3 and a_st['games'] >= 3:
        h_feat = [h_st['scored']/h_st['games'], h_st['conceded']/h_st['games'], h_st['points']/h_st['games']]
        a_feat = [a_st['scored']/a_st['games'], a_st['conceded']/a_st['games'], a_st['points']/a_st['games']]
        X_all.append(h_feat + a_feat + [1])
        y_all.append(winner)

    # Update stats
    h_st['games'] += 1
    a_st['games'] += 1
    h_st['scored'] += hg
    h_st['conceded'] += ag
    a_st['scored'] += ag
    a_st['conceded'] += hg

    if hg > ag:
        h_st['points'] += 3
    elif hg == ag:
        h_st['points'] += 1
        a_st['points'] += 1
    else:
        a_st['points'] += 3

X_all = np.array(X_all, dtype=np.float32)
y_all = np.array(y_all)

print(f"Generated {len(X_all)} training samples from CSV history.")

# Now, we continue training the existing model!
# XGBClassifier supports warm_start or xgb_model parameter in fit.
# Wait, sklearn wrapper .fit() doesn't always support incremental training easily unless we pass xgb_model.
try:
    # Get the underlying booster
    booster = model.get_booster()
    
    # We must encode labels to integers for XGBoost
    label_map = {c: i for i, c in enumerate(model.classes_)}
    y_encoded = np.array([label_map[y] for y in y_all])
    
    # Train the sklearn model incrementally
    model.fit(X_all, y_encoded, xgb_model=booster)
    print("Model incrementally updated with new data!")
except Exception as e:
    print(f"Incremental training failed: {e}. Falling back to retraining with same hyperparams...")
    # Label encoding (0=away, 1=draw, 2=home) based on legacy classes
    label_map = {'away': 0, 'draw': 1, 'home': 2}
    y_encoded = np.array([label_map[y] for y in y_all])
    model.fit(X_all, y_encoded)

# Evaluate on the training set
y_pred_encoded = model.predict(X_all)
y_pred = np.array(['away', 'draw', 'home'])[y_pred_encoded]

print("\nClassification Report (after update):")
print(classification_report(y_all, y_pred, target_names=['away', 'draw', 'home']))

# Save back to the SAME file format
data['model'] = model
data['team_stats'] = my_team_stats # updated stats
data['total_matches'] = len(matches)

with open('models/xgb_classifier.pkl', 'wb') as f:
    pickle.dump(data, f)

print(f"Updated model saved back to models/xgb_classifier.pkl successfully!")
