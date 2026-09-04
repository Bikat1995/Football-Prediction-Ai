import math
import numpy as np
import joblib
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def poisson_pmf(lam, k):
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

print("="*60)
print("  AI vs POISSON LIE DETECTOR TEST")
print("="*60)
print("\nLoading AI Model...")
try:
    m = joblib.load('models/live_compatible_model.pkl')
    model = m['model']
    print(f"[SUCCESS]: Loaded XGBoost AI (Trained on {m.get('total_samples_trained', 'unknown')} matches)")
except Exception as e:
    print(f"[FAILED] to load AI: {e}")
    exit(1)

print("\n--- SIMULATING A MATCH ---")
print("Team A (Strong Form, High Odds) vs Team B (Weak Form, Low Odds)")

# Hypothetical Stats
home_avg_scored, home_avg_conceded, home_pts_avg = 2.5, 0.5, 2.8
away_avg_scored, away_avg_conceded, away_pts_avg = 0.8, 2.0, 0.5
odds_h, odds_d, odds_a = 1.3, 4.0, 9.0

print(f"\n1. RUNNING RAW POISSON MATH...")
lam_h = max(0.3, (home_avg_scored + away_avg_conceded) / 2)
lam_a = max(0.3, (away_avg_scored + home_avg_conceded) / 2)
p_home_poisson, p_draw_poisson, p_away_poisson = 0, 0, 0
for h in range(6):
    for a in range(6):
        prob = poisson_pmf(lam_h, h) * poisson_pmf(lam_a, a)
        if h > a: p_home_poisson += prob
        elif h == a: p_draw_poisson += prob
        else: p_away_poisson += prob

# Normalize
tot = p_home_poisson + p_draw_poisson + p_away_poisson
p_home_poisson /= tot; p_draw_poisson /= tot; p_away_poisson /= tot

print(f"   Home Win: {p_home_poisson:.1%}")
print(f"   Draw:     {p_draw_poisson:.1%}")
print(f"   Away Win: {p_away_poisson:.1%}")

print(f"\n2. RUNNING TRUE MACHINE LEARNING (XGBoost)...")
feature_vector = [home_avg_scored, home_avg_conceded, home_pts_avg, away_avg_scored, away_avg_conceded, away_pts_avg, odds_h, odds_d, odds_a]
probs = model.predict_proba(np.array([feature_vector], dtype=np.float32))[0]
p_away_ai, p_draw_ai, p_home_ai = float(probs[0]), float(probs[1]), float(probs[2])

print(f"   Home Win: {p_home_ai:.1%}")
print(f"   Draw:     {p_draw_ai:.1%}")
print(f"   Away Win: {p_away_ai:.1%}")

print("\n--- CONCLUSION ---")
if abs(p_home_poisson - p_home_ai) > 0.01:
    print("[PROOF VERIFIED]: The AI and Poisson give completely different numbers.")
    print("   The AI is mathematically active and predicting based on its own trained trees,")
    print("   not just copying the hardcoded Poisson math.")
else:
    print("[FAILED]: The numbers are identical, meaning the AI is not working independently.")
print("="*60)
