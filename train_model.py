"""
Comprehensive AI Training Script
Ingests:
  - Local datasets (Big 5, UCL CSVs, UCL Knockouts Excel)
  - openfootball repos: champions-league, belgium, italy, europe
  - Kaggle: johntocci/champions-league-matches-2025-2026
  - Kaggle: emirhansevinc/ucl-all-knockout-games-1992-2026
Outputs:
  - models/xgb_classifier.pkl  (match outcome: 0=Away, 1=Draw, 2=Home)
  - models/team_stats.pkl       (historical per-team stats dict)
"""

import os, re, pickle, warnings
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import kagglehub

warnings.filterwarnings('ignore')

REPOS = [
    'cache/champions-league-repo',
    'cache/belgium-repo',
    'cache/italy-repo',
    'cache/europe-repo',
]

LOCAL_FILES = {
    'new datasets/Big_Five_2025_26_Database-w6nvhi.xlsx': 'big5',
    'new datasets/UCL_Eleme_Turlar_Verisi.xlsx':          'ucl_ko',
    'new datasets/champions_league_matches.csv':          'ucl_csv',
}

# ─── 1. Parse openfootball .txt files ─────────────────────────────────────────
# Line format: "  18:45  Team A  v  Team B  3-1 (2-0)"
# or without time:  "  Team A  v  Team B  2-1"
MATCH_RE = re.compile(
    r'\b(\d+)-(\d+)\b',        # score: goals-goals (last occurrence wins)
)
TEAM_SCORE_RE = re.compile(
    r'^\s+(?:\d{2}:\d{2}\s+)?'       # optional time
    r'(.+?)\s+v\s+(.+?)\s+'           # home v away
    r'(\d+)-(\d+)'                    # score
    r'(?:\s*\(\d+-\d+\))?',           # optional halftime
    re.IGNORECASE
)

def _clean_team(name: str) -> str:
    """Strip country codes like (ENG) and extra whitespace."""
    return re.sub(r'\s*\([A-Z]{2,3}\)\s*', '', name).strip()

def parse_openfootball_txt(path: str, competition: str) -> list:
    rows = []
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = TEAM_SCORE_RE.match(line)
            if not m:
                continue
            home = _clean_team(m.group(1))
            away = _clean_team(m.group(2))
            hg, ag = int(m.group(3)), int(m.group(4))
            if not home or not away or home == away:
                continue
            if hg > ag:
                res = 2
            elif hg == ag:
                res = 1
            else:
                res = 0
            rows.append({'home_team': home, 'away_team': away,
                         'home_goals': hg, 'away_goals': ag,
                         'result': res, 'competition': competition})
    return rows

print("=== Step 1: Parsing openfootball repos ===")
all_rows = []
for repo in REPOS:
    for root, _, files in os.walk(repo):
        for fn in files:
            if not fn.endswith('.txt'):
                continue
            comp = 'CL' if fn.startswith('cl') else \
                   'EL' if fn.startswith('el') else \
                   'CONF' if fn.startswith('conf') else \
                   'LEAGUE'
            parsed = parse_openfootball_txt(os.path.join(root, fn), comp)
            all_rows.extend(parsed)

print(f"  Parsed {len(all_rows)} matches from openfootball repos")

# ─── 2. Local datasets ────────────────────────────────────────────────────────
print("=== Step 2: Loading local datasets ===")

# Big 5 Excel
try:
    df_big5 = pd.read_excel('new datasets/Big_Five_2025_26_Database-w6nvhi.xlsx')
    for _, row in df_big5.iterrows():
        if pd.isna(row.get('home_goals_ft')) or pd.isna(row.get('away_goals_ft')):
            continue
        hg, ag = int(row['home_goals_ft']), int(row['away_goals_ft'])
        res = 2 if hg > ag else (1 if hg == ag else 0)
        all_rows.append({'home_team': str(row['home_team']).strip(),
                         'away_team': str(row['away_team']).strip(),
                         'home_goals': hg, 'away_goals': ag,
                         'result': res, 'competition': 'LEAGUE'})
    print(f"  Big 5: {len(df_big5)} rows")
except Exception as e:
    print(f"  Big 5 failed: {e}")

# UCL Knockout CSV
try:
    df_ucl = pd.read_csv('new datasets/champions_league_matches.csv')
    for _, row in df_ucl.iterrows():
        score_str = str(row.get('score', ''))
        if '-' not in score_str:
            continue
        parts = score_str.split('-')
        try:
            hg, ag = int(parts[0].strip()), int(parts[1].strip())
        except:
            continue
        res = 2 if hg > ag else (1 if hg == ag else 0)
        all_rows.append({'home_team': str(row['home_team']).strip(),
                         'away_team': str(row['away_team']).strip(),
                         'home_goals': hg, 'away_goals': ag,
                         'result': res, 'competition': 'CL'})
    print(f"  UCL CSV: {len(df_ucl)} rows")
except Exception as e:
    print(f"  UCL CSV failed: {e}")

# UCL Knockouts Excel (Turkish columns)
try:
    df_ko = pd.read_excel('new datasets/UCL_Eleme_Turlar_Verisi.xlsx')
    # Auto-detect home/away goal columns
    goal_cols = [c for c in df_ko.columns if 'gol' in str(c).lower() or 'goal' in str(c).lower() or 'skor' in str(c).lower()]
    print(f"  UCL KO cols: {list(df_ko.columns[:8])} | goal candidates: {goal_cols}")
    # Use first two numeric columns after team cols as goals if available
    numeric_cols = df_ko.select_dtypes(include='number').columns.tolist()
    if len(numeric_cols) >= 2:
        g1, g2 = numeric_cols[0], numeric_cols[1]
        for _, row in df_ko.iterrows():
            try:
                hg, ag = int(row[g1]), int(row[g2])
                res = 2 if hg > ag else (1 if hg == ag else 0)
                # try to get team names from first two string cols
                str_cols = df_ko.select_dtypes(include='object').columns
                ht = str(row[str_cols[0]]).strip() if len(str_cols) > 0 else 'TeamA'
                at = str(row[str_cols[1]]).strip() if len(str_cols) > 1 else 'TeamB'
                if ht and at and ht != at:
                    all_rows.append({'home_team': ht, 'away_team': at,
                                     'home_goals': hg, 'away_goals': ag,
                                     'result': res, 'competition': 'CL'})
            except:
                pass
    print(f"  UCL KO Excel: rows added")
except Exception as e:
    print(f"  UCL KO Excel failed: {e}")

# ─── 3. Kaggle datasets ───────────────────────────────────────────────────────
print("=== Step 3: Pulling Kaggle datasets ===")
try:
    from kagglehub import KaggleDatasetAdapter
    df_k = kagglehub.load_dataset(KaggleDatasetAdapter.PANDAS,
                                  "johntocci/champions-league-matches-2025-2026", "")
    for _, row in df_k.iterrows():
        score_str = str(row.get('score', ''))
        if '-' not in score_str:
            continue
        parts = score_str.split('-')
        try:
            hg, ag = int(parts[0].strip()), int(parts[1].strip())
        except:
            continue
        res = 2 if hg > ag else (1 if hg == ag else 0)
        all_rows.append({'home_team': str(row['home_team']).strip(),
                         'away_team': str(row['away_team']).strip(),
                         'home_goals': hg, 'away_goals': ag,
                         'result': res, 'competition': 'CL'})
    print(f"  Kaggle UCL 2025-26: {len(df_k)} rows")
except Exception as e:
    print(f"  Kaggle UCL 2025-26 failed: {e}")

# ─── 4. soccerdata skipped (FBref uses CAPTCHA in headless environments) ──────
print("=== Step 4: soccerdata FBref — skipped (CAPTCHA protection) ===")
print("  Using openfootball repos + local datasets instead (sufficient data)")


# ─── 5. Build unified DataFrame ───────────────────────────────────────────────
print(f"\n=== Step 5: Building unified DataFrame ===")
df = pd.DataFrame(all_rows).dropna(subset=['home_team','away_team','result'])
df = df[df['home_team'] != df['away_team']]
print(f"  Total training matches: {len(df)}")
print(f"  Competition breakdown:\n{df['competition'].value_counts()}")

# ─── 6. Build historical team stats ───────────────────────────────────────────
print("=== Step 6: Computing team stats ===")
team_stats = {}
for _, row in df.iterrows():
    for role, opp_role, pts_if_win, pts_if_loss in [
        ('home_team', 'away_team', 3 if row['result']==2 else (1 if row['result']==1 else 0),
         3 if row['result']==0 else (1 if row['result']==1 else 0)),
    ]:
        ht = row['home_team']; at = row['away_team']
        for team, scored, conceded, pts in [
            (ht, row['home_goals'], row['away_goals'],
             3 if row['result']==2 else (1 if row['result']==1 else 0)),
            (at, row['away_goals'], row['home_goals'],
             3 if row['result']==0 else (1 if row['result']==1 else 0)),
        ]:
            if team not in team_stats:
                team_stats[team] = {'games': 0, 'scored': 0, 'conceded': 0, 'points': 0}
            team_stats[team]['games']    += 1
            team_stats[team]['scored']   += scored
            team_stats[team]['conceded'] += conceded
            team_stats[team]['points']   += pts
        break  # only iterate once per row

print(f"  Unique teams in model: {len(team_stats)}")

# ─── 7. Feature engineering ───────────────────────────────────────────────────
LEAGUE_AVG_SCORED    = df['home_goals'].mean()
LEAGUE_AVG_CONCEDED  = df['away_goals'].mean()
LEAGUE_AVG_PPG       = 1.5

def team_features(name):
    if name in team_stats and team_stats[name]['games'] >= 3:
        g = team_stats[name]['games']
        return [
            team_stats[name]['scored']   / g,
            team_stats[name]['conceded'] / g,
            team_stats[name]['points']   / g,
        ], True   # known team
    # Fallback: use league averages
    return [LEAGUE_AVG_SCORED, LEAGUE_AVG_CONCEDED, LEAGUE_AVG_PPG], False

X, y = [], []
for _, row in df.iterrows():
    h_feat, h_known = team_features(row['home_team'])
    a_feat, a_known = team_features(row['away_team'])
    is_europe = 1 if row['competition'] in ('CL', 'EL', 'CONF') else 0
    X.append(h_feat + a_feat + [is_europe])
    y.append(row['result'])

X = np.array(X, dtype=np.float32)
y = np.array(y)

# ─── 8. Train XGBoost ─────────────────────────────────────────────────────────
print("=== Step 7: Training XGBoost Classifier ===")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)

model = xgb.XGBClassifier(
    n_estimators=500,
    learning_rate=0.04,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    objective='multi:softprob',
    num_class=3,
    eval_metric='mlogloss',
    use_label_encoder=False,
    verbosity=0,
)
model.fit(X_train, y_train,
          eval_set=[(X_test, y_test)],
          verbose=False)

y_pred = model.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"  Accuracy: {acc*100:.2f}%")

# ─── 9. Save ──────────────────────────────────────────────────────────────────
os.makedirs('models', exist_ok=True)
with open('models/xgb_classifier.pkl', 'wb') as f:
    pickle.dump({'model': model, 'team_stats': team_stats,
                 'league_avg': {'scored': LEAGUE_AVG_SCORED,
                                'conceded': LEAGUE_AVG_CONCEDED,
                                'ppg': LEAGUE_AVG_PPG},
                 'total_matches': len(df)}, f)

print(f"\n✓ Model saved to models/xgb_classifier.pkl")
print(f"✓ Total teams known to AI: {len(team_stats)}")
print(f"✓ Total training matches:  {len(df)}")
print("Training complete!")
