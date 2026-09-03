import os
import json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request
from cachetools import TTLCache, cached
from live_data_fetcher import (
    get_upcoming_fixtures,
    get_live_fixtures,
    compute_poisson_markets,
    get_team_form,
    LOGO_B64
)

app = Flask(__name__)

form_cache = TTLCache(maxsize=500, ttl=3600)
pred_cache = TTLCache(maxsize=20, ttl=300)

LEAGUES = [
    5242, 6088, 5971, 6061, 6223, 5240, 6171, 6245, 6192, 5966, 
    5972, 6301, 6089, 5236, 6032, 5968, 6013, 6204, 6203, 6184, 
    5970, 6035, 6039, 6248, 6228, 6205, 5961, 5960, 6157, 5969, 
    6081, 6033, 6220, 6065, 6214, 5978
]

@cached(form_cache)
def cached_team_form(team_id):
    return get_team_form(team_id)

def get_client_dates():
    today = datetime.utcnow().date()
    return today.isoformat(), (today + timedelta(days=1)).isoformat()

@cached(pred_cache)
def get_predictions(day_key):
    today_str, tomorrow_str = get_client_dates()
    target_date = today_str if day_key == 'today' else tomorrow_str
    
    if day_key == 'live':
        fixtures = get_live_fixtures(leagues=LEAGUES)
    else:
        all_f = get_upcoming_fixtures(leagues=LEAGUES)
        fixtures = [f for f in all_f if f.get('utc_date', '')[:10] == target_date]
        
    results = []
    for f in fixtures:
        try:
            hf = cached_team_form(f['home_team']['id'])
            af = cached_team_form(f['away_team']['id'])
            poisson = compute_poisson_markets(
                f['home_team']['name'], f['away_team']['name'],
                hf.get('avg_scored', 1.3), hf.get('avg_conceded', 1.1),
                af.get('avg_scored', 1.1), af.get('avg_conceded', 1.3),
            )
            results.append({
                'id': f['id'],
                'fixture': f,
                'poisson': poisson,
                'home_form': hf,
                'away_form': af,
            })
        except Exception:
            pass
            
    return sorted(results, key=lambda x: x['fixture'].get('utc_date', ''))

@app.route('/')
def index():
    day = request.args.get('nav', 'today')
    if day not in ['today', 'tomorrow', 'live', 'past']:
        day = 'today'
        
    context = {
        'day': day,
        'logo_b64': LOGO_B64,
        'utc_time': datetime.utcnow().strftime('%H:%M UTC')
    }
    
    if day == 'past':
        try:
            with open('past_predictions.json') as f:
                context['past_results'] = json.load(f)
        except Exception:
            context['past_results'] = []
    else:
        games = get_predictions(day)
        grouped = {}
        for g in games:
            lname = g['fixture']['competition']['name']
            if lname not in grouped:
                grouped[lname] = []
            grouped[lname].append(g)
            
        context['grouped_games'] = grouped
        context['has_games'] = len(games) > 0
        
    return render_template('index.html', **context)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port)
