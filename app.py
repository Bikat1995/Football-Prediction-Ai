import os
import json
import base64
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request
from cachetools import TTLCache, cached
from live_data_fetcher import (
    get_upcoming_fixtures,
    get_live_fixtures,
    compute_poisson_markets,
    get_team_form,
)

app = Flask(__name__)

# Load logo - try all possible filenames
LOGO_B64 = ''
for _logo_name in ['Better-logo.png', 'logo.png', 'Logo.png']:
    try:
        with open(_logo_name, 'rb') as _lf:
            LOGO_B64 = base64.b64encode(_lf.read()).decode()
        break
    except Exception:
        continue

form_cache = TTLCache(maxsize=500, ttl=3600)

from live_data_fetcher import _get

@cached(TTLCache(maxsize=1, ttl=86400))
def get_dynamic_leagues():
    """Dynamically fetch all competitions that are 'league' type and have team stats."""
    comps = []
    page = 1
    while True:
        res = _get('competitions', {'limit': 100, 'page': page}, ttl=86400)
        if not res or 'data' not in res: break
        comps.extend(res['data'])
        if page >= res.get('meta', {}).get('total_pages', 1): break
        page += 1
    
    return [c['id'] for c in comps if c.get('type') == 'league' and c.get('has_team_stats') == True]

@cached(form_cache)
def cached_team_form(team_id):
    try:
        return get_team_form(team_id)
    except Exception:
        return {'avg_scored': 1.2, 'avg_conceded': 1.2, 'form': []}

def get_client_dates():
    today = datetime.utcnow().date()
    return today.isoformat(), (today + timedelta(days=1)).isoformat()

def get_predictions(day_key):
    today_str, tomorrow_str = get_client_dates()
    target_date = today_str if day_key == 'today' else tomorrow_str
    
    dyn_leagues = get_dynamic_leagues()
    
    try:
        if day_key == 'live':
            fixtures = get_live_fixtures(leagues=dyn_leagues)
        else:
            all_f = get_upcoming_fixtures(leagues=dyn_leagues)
            fixtures = [f for f in all_f if f.get('utc_date', '')[:10] == target_date]
    except Exception as e:
        print(f"[ERROR] Fetching fixtures: {e}")
        return []

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
            results.append({'id': f['id'], 'fixture': f, 'poisson': poisson,
                            'home_form': hf, 'away_form': af})
        except Exception as e:
            print(f"[ERROR] Processing fixture: {e}")

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

@app.route('/debug')
def debug():
    from live_data_fetcher import _headers, get_upcoming_fixtures
    import requests as req
    key = os.getenv('THESTATSAPI_KEY', '')
    today_str, _ = get_client_dates()
    info = {
        'api_key_set': bool(key),
        'api_key_prefix': key[:8] + '...' if key else 'MISSING',
        'today': today_str,
        'logo_loaded': bool(LOGO_B64),
    }
    try:
        dyn_leagues = get_dynamic_leagues()
        info['dynamic_leagues_count'] = len(dyn_leagues)
        all_f = get_upcoming_fixtures(leagues=dyn_leagues)
        info['total_fixtures_fetched'] = len(all_f)
        info['fixtures_today'] = len([f for f in all_f if f.get('utc_date','')[:10] == today_str])
        if all_f:
            info['sample_fixture'] = {
                'id': all_f[0].get('id'),
                'home': all_f[0].get('home_team',{}).get('name'),
                'away': all_f[0].get('away_team',{}).get('name'),
                'utc_date': all_f[0].get('utc_date'),
            }
    except Exception as e:
        info['fetch_error'] = str(e)
    return info

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))

    app.run(host='0.0.0.0', port=port)
