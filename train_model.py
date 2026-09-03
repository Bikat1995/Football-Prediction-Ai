"""
train_model.py
==============
Trains a Gradient Boosted classifier on historical match data from
collected_training_data.csv and saves it as model.pkl.

Features per match:
  - Home team rolling home avg goals scored    (last 8)
  - Home team rolling home avg goals conceded  (last 8)
  - Away team rolling away avg goals scored    (last 8)
  - Away team rolling away avg goals conceded  (last 8)
  - Home team overall avg goals scored         (last 8, all venues)
  - Away team overall avg goals scored         (last 8, all venues)
  - Attack edge  (home_scored - away_conceded)
  - Defense edge (home_conceded - away_scored)
  - Home team experience  (# games seen so far)
  - Away team experience  (# games seen so far)
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import csv
import pickle
import numpy as np
from collections import defaultdict

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    from sklearn.metrics import classification_report
except ImportError:
    print("Installing scikit-learn...")
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'scikit-learn'], check=True)
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    from sklearn.metrics import classification_report

# ─── Load & sort matches chronologically ──────────────────────────────────────
matches = []
with open('collected_training_data.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    for row in reader:
        matches.append(row)

matches.sort(key=lambda x: x['Date'])
print(f"Loaded {len(matches)} historical matches.")

# ─── Rolling team stats ────────────────────────────────────────────────────────
# We track home & away stats separately for each team (keyed by team_id)
team_home_scored    = defaultdict(list)
team_home_conceded  = defaultdict(list)
team_away_scored    = defaultdict(list)
team_away_conceded  = defaultdict(list)
team_all_scored     = defaultdict(list)
team_all_conceded   = defaultdict(list)

WINDOW = 8  # rolling window

def roll_mean(lst, n=WINDOW, default=1.2):
    vals = lst[-n:]
    return float(np.mean(vals)) if vals else default

X, y = [], []

for m in matches:
    h_id  = m['Home_ID']
    a_id  = m['Away_ID']
    hg    = int(m['Home_Goals'])
    ag    = int(m['Away_Goals'])
    label = m['Winner']   # 'home' | 'draw' | 'away'

    # ── Features using stats BEFORE this match ──
    h_hs = roll_mean(team_home_scored[h_id])     # home team home scored
    h_hc = roll_mean(team_home_conceded[h_id])   # home team home conceded
    a_as = roll_mean(team_away_scored[a_id])      # away team away scored
    a_ac = roll_mean(team_away_conceded[a_id])    # away team away conceded
    h_all = roll_mean(team_all_scored[h_id])      # home team overall scored
    a_all = roll_mean(team_all_scored[a_id])      # away team overall scored
    h_def = roll_mean(team_all_conceded[h_id])    # home team overall conceded
    a_def = roll_mean(team_all_conceded[a_id])    # away team overall conceded

    attack_edge  = h_hs  - a_ac   # home attack vs away defense
    defense_edge = a_as  - h_hc   # away attack vs home defense
    overall_edge = h_all - a_all  # overall scoring form difference

    h_exp = len(team_home_scored[h_id])
    a_exp = len(team_away_scored[a_id])

    features = [
        h_hs, h_hc,
        a_as, a_ac,
        h_all, a_all,
        h_def, a_def,
        attack_edge,
        defense_edge,
        overall_edge,
        min(h_exp, 20),   # cap at 20 to avoid scale drift
        min(a_exp, 20),
    ]

    X.append(features)
    y.append(label)

    # ── Update stats AFTER this match ──
    team_home_scored[h_id].append(hg)
    team_home_conceded[h_id].append(ag)
    team_away_scored[a_id].append(ag)
    team_away_conceded[a_id].append(hg)
    team_all_scored[h_id].append(hg)
    team_all_scored[a_id].append(ag)
    team_all_conceded[h_id].append(ag)
    team_all_conceded[a_id].append(hg)

X = np.array(X)
y = np.array(y)

classes, counts = np.unique(y, return_counts=True)
print(f"\nClass distribution: {dict(zip(classes, counts))}")

# ─── Train / evaluate ─────────────────────────────────────────────────────────
model = GradientBoostingClassifier(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    random_state=42
)

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(model, X, y, cv=cv, scoring='accuracy')
print(f"\n5-fold CV Accuracy: {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%")
print(f"Baseline (always predict home): {(y == 'home').mean()*100:.1f}%")

# ─── Fit on full dataset ───────────────────────────────────────────────────────
model.fit(X, y)

# Feature importance
feat_names = [
    'h_home_scored','h_home_conceded',
    'a_away_scored','a_away_conceded',
    'h_overall_scored','a_overall_scored',
    'h_overall_conceded','a_overall_conceded',
    'attack_edge','defense_edge','overall_edge',
    'h_experience','a_experience'
]
importances = sorted(zip(feat_names, model.feature_importances_), key=lambda x: -x[1])
print("\nTop feature importances:")
for name, imp in importances[:8]:
    bar = '█' * int(imp * 100)
    print(f"  {name:<25} {bar} {imp*100:.1f}%")

# ─── Save model + team stats for live inference ────────────────────────────────
payload = {
    'model': model,
    'team_home_scored':   dict(team_home_scored),
    'team_home_conceded': dict(team_home_conceded),
    'team_away_scored':   dict(team_away_scored),
    'team_away_conceded': dict(team_away_conceded),
    'team_all_scored':    dict(team_all_scored),
    'team_all_conceded':  dict(team_all_conceded),
    'window': WINDOW,
    'classes': list(model.classes_),
}

with open('model.pkl', 'wb') as f:
    pickle.dump(payload, f)

print("\nModel saved to model.pkl")
print("\nFull classification report (training set):")
print(classification_report(y, model.predict(X), target_names=['away','draw','home']))
