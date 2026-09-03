import sys, io
import csv
import json
import time
import live_data_fetcher as fetcher
import predict_today

# Force UTF-8 output so special chars don't crash on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

leagues_dict = predict_today.LEAGUES

# Dates to process (most recent first)
target_dates = ['2026-09-02', '2026-09-01', '2026-08-31', '2026-08-30']

# Read all matches from CSV
all_matches = []
with open('collected_training_data.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        all_matches.append(row)

# Filter for the target dates and collect ALL of them grouped by date
by_date = {}
for row in all_matches:
    d = row[1]
    if d in target_dates:
        by_date.setdefault(d, []).append(row)

print(f"Matches per date:")
for d in target_dates:
    print(f"  {d}: {len(by_date.get(d, []))} matches")

# Load existing results so we don't re-process what already finished
try:
    with open('past_predictions.json', 'r', encoding='utf-8') as f:
        output = json.load(f)
    done_keys = {f"{p['home']}-{p['away']}-{p['date']}" for p in output}
    print(f"Resuming — {len(output)} already processed.")
except:
    output = []
    done_keys = set()

for date in target_dates:
    matches = by_date.get(date, [])
    print(f"\n--- Processing {date} ({len(matches)} matches) ---")
    for i, row in enumerate(matches):
        m_id, d, comp_id, h_id, h_name, a_id, a_name, hg, ag, winner = row
        hg, ag = int(hg), int(ag)

        m_key = f"{h_name}-{a_name}-{date}"
        if m_key in done_keys:
            print(f"  [{i+1}/{len(matches)}] Skipping {h_name} vs {a_name} (already done)", flush=True)
            continue

        print(f"  [{i+1}/{len(matches)}] {h_name} vs {a_name}", flush=True)
        try:
            hf = fetcher.get_team_form(h_id, last=5)
            time.sleep(1.0)
            af = fetcher.get_team_form(a_id, last=5)
            time.sleep(1.0)

            p = fetcher.compute_poisson_markets(
                h_name, a_name,
                hf.get('avg_scored', 1.3), hf.get('avg_conceded', 1.1),
                af.get('avg_scored', 1.1), af.get('avg_conceded', 1.3)
            )

            hw, dw, aw = p['home_win'], p['draw'], p['away_win']
            if hw >= dw and hw >= aw:
                ai_pick = 'home'
            elif aw >= hw and aw >= dw:
                ai_pick = 'away'
            else:
                ai_pick = 'draw'

            actual = 'home' if hg > ag else 'away' if ag > hg else 'draw'
            league_name = leagues_dict.get(comp_id, comp_id)
            if isinstance(league_name, dict):
                league_name = league_name.get('name', comp_id)

            output.append({
                'home': h_name,
                'away': a_name,
                'score': f'{hg} - {ag}',
                'winner': actual,
                'ai_pick': ai_pick,
                'ai_prob': max(hw, dw, aw),
                'correct': ai_pick == actual,
                'date': date,
                'league': league_name
            })

            # Save after every match so progress is visible in the dashboard
            output.sort(key=lambda x: x['date'], reverse=True)
            with open('past_predictions.json', 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False)

        except Exception as e:
            print(f"    Error: {e}", flush=True)
            time.sleep(2)

total = len(output)
correct = sum(1 for p in output if p['correct'])
print(f"\nDone! {total} matches processed. Accuracy: {correct}/{total} ({correct/total*100:.1f}%)" if total else "\nDone! No matches processed.")
