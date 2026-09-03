import json
import time
from datetime import datetime, timedelta
import live_data_fetcher as fetcher
import predict_today

leagues = list(predict_today.LEAGUES.keys())

# Let's check Aug 31 and Sep 1
dates = [(datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d'), 
         (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')]

correct = 0
wrong = 0
results_log = []

for d in dates:
    print(f"Checking date: {d}")
    try:
        fixtures = fetcher.get_fixtures_for_date(d, leagues=leagues)
    except Exception as e:
        print(f"Error fetching {d}: {e}")
        continue
        
    for f in fixtures:
        if f['status'] == 'finished':
            home_id = f['home_team']['id']
            away_id = f['away_team']['id']
            home_name = f['home_team']['name']
            away_name = f['away_team']['name']
            
            # Actual score
            hg = f['score'].get('home', 0) or 0
            ag = f['score'].get('away', 0) or 0
            if hg > ag: actual_res = 'home'
            elif ag > hg: actual_res = 'away'
            else: actual_res = 'draw'
            
            # AI Prediction
            try:
                hf = fetcher.get_team_form(home_id, last=8)
                af = fetcher.get_team_form(away_id, last=8)
                p = fetcher.compute_poisson_markets(
                    home_name, away_name,
                    hf.get('avg_scored', 1.3), hf.get('avg_conceded', 1.1),
                    af.get('avg_scored', 1.1), af.get('avg_conceded', 1.3)
                )
                
                hw = p['home_win']
                dw = p['draw']
                aw = p['away_win']
                
                if hw >= dw and hw >= aw: ai_pick = 'home'
                elif aw >= hw and aw >= dw: ai_pick = 'away'
                else: ai_pick = 'draw'
                
                is_correct = (ai_pick == actual_res)
                if is_correct: correct += 1
                else: wrong += 1
                
                # BTTS market eval
                actual_btts = (hg > 0 and ag > 0)
                ai_btts = p['btts'] >= 50
                
                results_log.append({
                    'match': f"{home_name} {hg}-{ag} {away_name}",
                    'actual': actual_res,
                    'ai_pick': ai_pick,
                    'correct': is_correct,
                    'ai_prob': max(hw, dw, aw)
                })
                print(f"Match: {home_name} {hg}-{ag} {away_name} | AI Pick: {ai_pick.upper()} ({max(hw,dw,aw)}%) | Result: {actual_res.upper()} | {'✅' if is_correct else '❌'}")
                time.sleep(1.5)
            except Exception as e:
                pass

print(f"\nTotal: {correct + wrong}, Correct: {correct}, Wrong: {wrong}")
if correct + wrong > 0:
    print(f"Accuracy: {correct/(correct+wrong)*100:.1f}%")
