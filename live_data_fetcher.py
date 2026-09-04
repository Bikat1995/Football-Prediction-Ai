import os
import requests
import json
import time
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import math
import pickle
import numpy as np

load_dotenv()

BASE_URL = "https://api.thestatsapi.com/api/football"
CACHE_DIR = "cache/thestatsapi"
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
    test_path = os.path.join(CACHE_DIR, '.write_test')
    with open(test_path, 'w') as f:
        f.write('ok')
    os.remove(test_path)
except Exception:
    import tempfile
    CACHE_DIR = os.path.join(tempfile.gettempdir(), 'thestatsapi_cache')
    os.makedirs(CACHE_DIR, exist_ok=True)

LIVE_STATUSES     = {'in_play', 'paused', 'live', 'halftime', 'extra_time', 'penalties'}
FINISHED_STATUSES = {'finished', 'awarded'}
UPCOMING_STATUSES = {'scheduled', 'timed', 'in_play', 'paused', 'halftime', 'extra_time', 'postponed'}

def _headers() -> dict:
    # Try env var first (local .env), then Streamlit secrets (Streamlit Cloud)
    key = os.getenv('THESTATSAPI_KEY', '')
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get('THESTATSAPI_KEY', '')
        except Exception:
            pass
    return {
        'Authorization': f'Bearer {key}'
    }

def _cache_key(endpoint: str, params: dict) -> str:
    parts = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
    return f"{endpoint.replace('/', '_')}_{parts}"

def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")

def _read_cache(key: str, ttl: int = 1800):
    p = _cache_path(key)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        with open(p) as f:
            return json.load(f)
    return None

def _write_cache(key: str, data: dict):
    with open(_cache_path(key), 'w') as f:
        json.dump(data, f)



def _log_everything_to_datalake(endpoint, params, data):
    """Appends ALL raw API responses into a master CSV data lake."""
    import csv
    import os
    import json
    from datetime import datetime
    
    csv_file = 'api_master_datalake.csv'
    file_exists = os.path.isfile(csv_file)
    
    # We dump the data dict into a json string so it fits in one CSV column
    row = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'endpoint': endpoint,
        'params': json.dumps(params),
        'raw_json_data': json.dumps(data)
    }
    
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'endpoint', 'params', 'raw_json_data'])
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def _log_matches_to_csv(matches_data):
    """Appends finished match data to a CSV for future model training."""
    import csv
    import os
    if not isinstance(matches_data, list):
        return
        
    csv_file = 'collected_training_data.csv'
    file_exists = os.path.isfile(csv_file)
    
    headers = ['Match_ID', 'Date', 'Competition_ID', 'Home_ID', 'Home_Name', 'Away_ID', 'Away_Name', 
               'Home_Goals', 'Away_Goals', 'Winner']
               
    rows_to_write = []
    
    # We may have already written some matches, read IDs to prevent duplicates
    existing_ids = set()
    if file_exists:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None) # skip header
                for row in reader:
                    if row:
                        existing_ids.add(row[0])
        except Exception:
            pass
            
    for m in matches_data:
        # Only log finished matches with a valid score object
        if not isinstance(m, dict) or m.get('status') not in FINISHED_STATUSES:
            continue
            
        m_id = m.get('id')
        if not m_id or m_id in existing_ids:
            continue
            
        score = m.get('score', {})
        if score:
            h_g = score.get('home')
            a_g = score.get('away')
            if h_g is not None and a_g is not None:
                rows_to_write.append({
                    'Match_ID': m_id,
                    'Date': m.get('utc_date', '')[:10],
                    'Competition_ID': m.get('competition_id', ''),
                    'Home_ID': m.get('home_team', {}).get('id', ''),
                    'Home_Name': m.get('home_team', {}).get('name', ''),
                    'Away_ID': m.get('away_team', {}).get('id', ''),
                    'Away_Name': m.get('away_team', {}).get('name', ''),
                    'Home_Goals': h_g,
                    'Away_Goals': a_g,
                    'Winner': score.get('winner', '')
                })
                existing_ids.add(m_id)
                
    if rows_to_write:
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows_to_write)

def _get(endpoint: str, params: dict, ttl: int = 1800, retries=2):
    ck = _cache_key(endpoint, params)
    cached = _read_cache(ck, ttl)
    if cached:
        return cached

    import time
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{BASE_URL}/{endpoint}",
                             headers=_headers(),
                             params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            _write_cache(ck, data)
            
            # --- AUTO-LOGGING FOR FUTURE TRAINING ---
            try:
                # Log literally everything fetched (stats, odds, matches) to a master data lake
                _log_everything_to_datalake(endpoint, params, data)
            except Exception:
                pass

            try:
                if 'matches' in endpoint and 'data' in data:
                    _log_matches_to_csv(data['data'])
            except Exception as e:
                pass
                
            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < retries:
                # Rate limited, wait and retry
                time.sleep(1.0)
                continue
            
            print(f"[API] {endpoint} HTTP Error: {e.response.status_code} - {e.response.text[:100]}")
            try:
                return e.response.json()
            except:
                return {"errors": {"access": f"HTTP {e.response.status_code} Forbidden"}}
        except Exception as e:
            print(f"[API] {endpoint} failed: {e}")
            return {"errors": {"access": f"Connection Error: {str(e)[:50]}"}}
    return {}

# ─────────────────────────────────────────────────────────────────────────────
# NEW ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

def get_fixtures_for_date(target_date: str, leagues=None) -> list:
    """All fixtures for a given date (YYYY-MM-DD). Fetches globally and filters to avoid rate limits."""
    if not leagues:
        return []
    all_items = []
    import time
    page = 1
    while True:
        data = _get('matches', {'date_from': target_date, 'date_to': target_date, 'limit': 100, 'page': page}, ttl=43200)
        if not data or 'data' not in data:
            break
        all_items.extend(data['data'])
        meta = data.get('meta', {})
        if page >= meta.get('total_pages', 1):
            break
        page += 1
        time.sleep(0.5)

    return [f for f in all_items if f.get('status') in UPCOMING_STATUSES and f.get('competition_id') in leagues]

def get_upcoming_fixtures(leagues=None) -> list:
    """Today + Tomorrow upcoming fixtures. Fetches globally and filters to avoid rate limits."""
    if not leagues:
        return []
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    all_items = []
    import time
    page = 1
    while True:
        # Cache for 15 minutes — short enough to pick up new leagues/config without stale data
        data = _get('matches', {'date_from': today, 'date_to': tomorrow, 'limit': 100, 'page': page}, ttl=900)
        if not data or 'data' not in data:
            break
        all_items.extend(data['data'])
        meta = data.get('meta', {})
        if page >= meta.get('total_pages', 1):
            break
        page += 1
        time.sleep(0.5)
    
    return [f for f in all_items if f.get('status') in UPCOMING_STATUSES and f.get('competition_id') in leagues]

def get_finished_fixtures(leagues=None) -> list:
    """Today + Yesterday finished fixtures. Fetches globally and filters."""
    if not leagues:
        return []
    today    = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    
    all_items = []
    import time
    page = 1
    while True:
        data = _get('matches', {'date_from': yesterday, 'date_to': today, 'limit': 100, 'page': page}, ttl=600)
        if not data or 'data' not in data:
            break
        all_items.extend(data['data'])
        meta = data.get('meta', {})
        if page >= meta.get('total_pages', 1):
            break
        page += 1
        time.sleep(0.5)
    
    return [f for f in all_items if f.get('status') in ['finished', 'awarded'] and f.get('competition_id') in leagues]

def get_live_fixtures(leagues=None) -> list:
    """Currently in-play matches globally, filtered by leagues."""
    # Using status=live fetches all live games
    # Pagination might be needed if > 100 games are live, but usually 100 is enough.
    data = _get('matches', {'status': 'live', 'limit': 100}, ttl=60)
    if not data or 'data' not in data:
        return []
    items = data['data']
    if leagues:
        items = [i for i in items if i['competition_id'] in leagues]
    return items

def get_team_form(team_id: str, last: int = 8) -> dict:
    """Real team form from last N FINISHED games across ALL competitions."""
    data = _get('matches', {'team_id': team_id, 'limit': last, 'status': 'finished'}, ttl=43200)
    if not data or 'data' not in data:
        return {}
    matches = data['data']
    if not matches:
        return {}
    scored = 0
    conceded = 0
    points = 0
    form = []
    
    # Matches are usually returned newest first
    for m in matches:
        is_home = (m['home_team']['id'] == team_id)
        sc = m['score']
        hg = sc.get('home') or 0
        ag = sc.get('away') or 0
        if is_home:
            scored += hg
            conceded += ag
            if hg > ag: points += 3; form.append('W')
            elif hg == ag: points += 1; form.append('D')
            else: form.append('L')
        else:
            scored += ag
            conceded += hg
            if ag > hg: points += 3; form.append('W')
            elif ag == hg: points += 1; form.append('D')
            else: form.append('L')
            
    n = len(matches)
    return {
        'avg_scored': round(scored / n, 3), 
        'avg_conceded': round(conceded / n, 3), 
        'pts_per_game': round(points / n, 3),
        'games': n,
        'form': form
    }

def get_head_to_head(home_id: str, away_id: str, last: int = 5) -> dict:
    """
    Fetch real head-to-head matches between two teams.
    Returns both the raw match list (for display) and summary stats (for Poisson blend).
    Strategy: Paginate through recent finished matches for home_id until we find `last` matches against away_id.
    """
    import time
    h2h_matches = []
    
    for page in range(1, 6): # Search up to 5 pages (500 matches)
        data = _get('matches', {'team_id': home_id, 'status': 'finished', 'limit': 100, 'page': page}, ttl=86400)
        if not data or 'data' not in data:
            break
            
        all_matches = data['data']
        if not all_matches:
            break
            
        # Filter matches where away_id was the opponent
        for m in all_matches:
            if m['home_team']['id'] == away_id or m['away_team']['id'] == away_id:
                h2h_matches.append(m)
                
        if len(h2h_matches) >= last:
            break
            
        # If we need to fetch another page, sleep briefly to avoid 429
        time.sleep(0.2)
        
    h2h_matches = h2h_matches[:last]

    if not h2h_matches:
        return {'matches': [], 'home_avg': 0, 'away_avg': 0, 'games': 0}

    home_scored = 0
    away_scored = 0
    for m in h2h_matches:
        is_home = (m['home_team']['id'] == home_id)
        sc = m['score']
        hg = sc.get('home') or 0
        ag = sc.get('away') or 0
        if is_home:
            home_scored += hg
            away_scored += ag
        else:
            home_scored += ag
            away_scored += hg

    n = len(h2h_matches)
    return {
        'matches': h2h_matches,
        'home_avg': round(home_scored / n, 3),
        'away_avg': round(away_scored / n, 3),
        'games': n
    }


def get_match_odds(match_id: str) -> dict:
    """Fetch odds and return Bet365 if available."""
    data = _get(f'matches/{match_id}/odds', {}, ttl=10800)
    if not data or 'data' not in data:
        return {}
    bookmakers = data['data'].get('bookmakers', [])
    for b in bookmakers:
        if b['bookmaker'] == 'Bet365':
            return b['markets']
    # Fallback to the first one if Bet365 not found
    if bookmakers:
        return bookmakers[0]['markets']
    return {}

def get_team_season_stats(team_id: str, season_id: str) -> dict:
    """Get stats for a team in a specific season."""
    data = _get(f'teams/{team_id}/stats', {'season_id': season_id}, ttl=86400)
    if not data or 'data' not in data:
        return {}
    return data['data']


# ─────────────────────────────────────────────────────────────────────────────
# POISSON + ML + ODDS ENSEMBLE
# ─────────────────────────────────────────────────────────────────────────────

# Load ML Model once
ML_MODEL_DATA = None
try:
    import joblib
    ML_MODEL_DATA = joblib.load('models/live_compatible_model.pkl')
    print(f"[ML] Live compatible model loaded. Samples trained: {ML_MODEL_DATA.get('total_samples_trained')}")
except Exception as e:
    print(f"Warning: ML model not found or failed to load - {e}")

def _poisson_pmf(lam: float, k: int) -> float:
    """P(X = k) for Poisson(λ)"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def compute_poisson_markets(home_team_name: str, away_team_name: str,
                            home_avg_scored: float, home_avg_conceded: float,
                            away_avg_scored: float, away_avg_conceded: float,
                            match_odds: dict = None,
                            max_goals: int = 6,
                            home_pts_avg: float = 1.5, away_pts_avg: float = 1.5) -> dict:
    """
    Compute all major betting markets from Poisson + ML + Real Betting Odds ensemble.
    Always returns a prediction.
    """
    lam_h = max(0.3, (home_avg_scored + away_avg_conceded) / 2)
    lam_a = max(0.3, (away_avg_scored + home_avg_conceded) / 2)

    # Score probability matrix (Poisson)
    matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            matrix[(h, a)] = _poisson_pmf(lam_h, h) * _poisson_pmf(lam_a, a)

    total = sum(matrix.values())
    p_home = sum(v for (h, a), v in matrix.items() if h > a)  / total
    p_draw = sum(v for (h, a), v in matrix.items() if h == a) / total
    p_away = sum(v for (h, a), v in matrix.items() if h < a)  / total

    ml_confidence = 0
    home_known = False
    away_known = False
    low_data_warning = None
    ml_used = False
    model_version = "None"
    total_trained = 0
    blend_explanation = "Pure Poisson logic used."

    # ENSEMBLE BLEND: Real Betting Odds
    odds_h = 2.5
    odds_d = 3.0
    odds_a = 2.8
    if match_odds and 'match_odds' in match_odds:
        try:
            o = match_odds['match_odds']
            odds_h = float(o['home']['last_seen'])
            odds_d = float(o['draw']['last_seen'])
            odds_a = float(o['away']['last_seen'])
        except Exception: pass

    if ML_MODEL_DATA and 'model' in ML_MODEL_DATA:
        model_version = ML_MODEL_DATA.get('version', 'v1')
        total_trained = ML_MODEL_DATA.get('total_samples_trained', 0)
        
        # Check if teams have sufficient live API form to use the ML model confidently
        # (home_pts_avg is computed from real recent games fetched via API)
        if home_avg_scored > 0 or home_pts_avg != 1.5: home_known = True
        if away_avg_scored > 0 or away_pts_avg != 1.5: away_known = True
        
        if home_known and away_known:
            ml_weight = 0.70 # Strong AI usage
            blend_explanation = "70% AI Model / 30% Poisson (Rich data available)"
        elif home_known or away_known:
            ml_weight = 0.30 # Weak AI usage
            blend_explanation = "30% AI Model / 70% Poisson (Limited data for one team)"
            low_data_warning = "Limited historical data for one team. Relying heavily on Poisson estimates."
        else:
            ml_weight = 0.10 # Almost pure Poisson
            blend_explanation = "10% AI Model / 90% Poisson (New teams, statistical estimate)"
            low_data_warning = "Unknown teams. Using pure statistical distribution."

        stat_weight = 1.0 - ml_weight
        
        feature_vector = [
            home_avg_scored, home_avg_conceded, home_pts_avg,
            away_avg_scored, away_avg_conceded, away_pts_avg,
            min(odds_h, 20.0), min(odds_d, 10.0), min(odds_a, 20.0)
        ]
        
        try:
            model = ML_MODEL_DATA['model']
            # XGBClassifier returns probabilities for [Away(0), Draw(1), Home(2)]
            import numpy as np
            probs = model.predict_proba(np.array([feature_vector], dtype=np.float32))[0]
            ml_away, ml_draw, ml_home = float(probs[0]), float(probs[1]), float(probs[2])
            
            p_home = p_home * stat_weight + ml_home * ml_weight
            p_draw = p_draw * stat_weight + ml_draw * ml_weight
            p_away = p_away * stat_weight + ml_away * ml_weight
            
            _s = p_home + p_draw + p_away
            p_home /= _s; p_draw /= _s; p_away /= _s
            
            ml_confidence = round(ml_weight * 100)
            ml_used = True
        except Exception as e:
            print(f"ML Inference failed: {e}")
            pass

    if not home_known and not away_known:
        low_data_warning = f"Limited historical data for both {home_team_name} and {away_team_name}. Prediction is statistical only."
    elif not home_known or not away_known:
        low_data_warning = "Limited historical data for one team. Prediction partially estimated."

    # ENSEMBLE BLEND: Real Betting Odds (30% weight)
    if match_odds and 'match_odds' in match_odds:
        try:
            o = match_odds['match_odds']
            oh = float(o['home']['last_seen'])
            od = float(o['draw']['last_seen'])
            oa = float(o['away']['last_seen'])
            
            ih = 1.0 / oh
            idr = 1.0 / od
            ia = 1.0 / oa
            overround = ih + idr + ia
            
            if overround > 0:
                ih /= overround
                idr /= overround
                ia /= overround
                
                odds_w = 0.30
                p_home = p_home * (1 - odds_w) + ih * odds_w
                p_draw = p_draw * (1 - odds_w) + idr * odds_w
                p_away = p_away * (1 - odds_w) + ia * odds_w
                
                _s = p_home + p_draw + p_away
                p_home /= _s; p_draw /= _s; p_away /= _s
        except Exception:
            pass

    # Derived markets from Poisson matrix
    p_btts    = sum(v for (h, a), v in matrix.items() if h >= 1 and a >= 1) / total
    p_over_15 = sum(v for (h, a), v in matrix.items() if h + a > 1) / total
    p_over_25 = sum(v for (h, a), v in matrix.items() if h + a > 2) / total
    p_over_35 = sum(v for (h, a), v in matrix.items() if h + a > 3) / total
    
    # Blend derived markets with odds if available
    if match_odds:
        try:
            if 'btts' in match_odds:
                o_yes = float(match_odds['btts']['yes']['last_seen'])
                o_no = float(match_odds['btts']['no']['last_seen'])
                implied_yes = (1.0/o_yes) / ((1.0/o_yes) + (1.0/o_no))
                p_btts = p_btts * 0.6 + implied_yes * 0.4
                
            if 'total_goals' in match_odds:
                if '2.5' in match_odds['total_goals']:
                    o_over = float(match_odds['total_goals']['2.5']['over']['last_seen'])
                    o_under = float(match_odds['total_goals']['2.5']['under']['last_seen'])
                    implied_over = (1.0/o_over) / ((1.0/o_over) + (1.0/o_under))
                    p_over_25 = p_over_25 * 0.6 + implied_over * 0.4
                    
                if '1.5' in match_odds['total_goals']:
                    o_over = float(match_odds['total_goals']['1.5']['over']['last_seen'])
                    o_under = float(match_odds['total_goals']['1.5']['under']['last_seen'])
                    implied_over = (1.0/o_over) / ((1.0/o_over) + (1.0/o_under))
                    p_over_15 = p_over_15 * 0.6 + implied_over * 0.4
        except:
            pass

    p_dc_home_draw = p_home + p_draw
    p_dc_away_draw = p_away + p_draw

    sorted_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)
    top_scores = [(f"{h}-{a}", round(v / total * 100, 1)) for (h, a), v in sorted_scores[:5]]

    # ─────────────────────────────────────────────────────────────────────────
    # FULL-SPECTRUM MARKET SCANNER
    # Evaluates 40+ betting markets from Poisson matrix, picks the safest ones
    # ─────────────────────────────────────────────────────────────────────────

    # ── Core probabilities from Poisson matrix ──
    p_over_0_5 = sum(v for (h, a), v in matrix.items() if h + a >= 1) / total
    p_over_1_5 = sum(v for (h, a), v in matrix.items() if h + a >= 2) / total
    p_over_2_5 = sum(v for (h, a), v in matrix.items() if h + a >= 3) / total
    p_over_3_5 = sum(v for (h, a), v in matrix.items() if h + a >= 4) / total
    p_over_4_5 = sum(v for (h, a), v in matrix.items() if h + a >= 5) / total
    p_over_5_5 = sum(v for (h, a), v in matrix.items() if h + a >= 6) / total

    p_under_0_5 = 1.0 - p_over_0_5
    p_under_1_5 = 1.0 - p_over_1_5
    p_under_2_5 = 1.0 - p_over_2_5
    p_under_3_5 = 1.0 - p_over_3_5
    p_under_4_5 = 1.0 - p_over_4_5

    p_btts_yes = sum(v for (h, a), v in matrix.items() if h > 0 and a > 0) / total
    p_btts_no  = 1.0 - p_btts_yes

    # Double Chance
    p_1X = p_home + p_draw
    p_X2 = p_away + p_draw
    p_12 = p_home + p_away

    # Draw No Bet
    p_dnb_home = p_home / (p_home + p_away) if (p_home + p_away) > 0 else 0.5
    p_dnb_away = p_away / (p_home + p_away) if (p_home + p_away) > 0 else 0.5

    # Home/Away team total goals
    p_home_over_0_5 = sum(v for (h, a), v in matrix.items() if h >= 1) / total
    p_home_over_1_5 = sum(v for (h, a), v in matrix.items() if h >= 2) / total
    p_away_over_0_5 = sum(v for (h, a), v in matrix.items() if a >= 1) / total
    p_away_over_1_5 = sum(v for (h, a), v in matrix.items() if a >= 2) / total

    # Clean sheets
    p_home_cs = sum(v for (h, a), v in matrix.items() if a == 0) / total
    p_away_cs = sum(v for (h, a), v in matrix.items() if h == 0) / total

    # Win to nil
    p_home_wtn = sum(v for (h, a), v in matrix.items() if h > a and a == 0) / total
    p_away_wtn = sum(v for (h, a), v in matrix.items() if a > h and h == 0) / total

    # Exact total goals
    p_exact = {}
    for g in range(7):
        p_exact[g] = sum(v for (h, a), v in matrix.items() if h + a == g) / total

    # Odd / Even total goals
    p_odd_total  = sum(v for (h, a), v in matrix.items() if (h + a) % 2 == 1) / total
    p_even_total = 1.0 - p_odd_total

    # Goal bands
    p_band_0_1 = sum(v for (h, a), v in matrix.items() if h + a <= 1) / total
    p_band_2_3 = sum(v for (h, a), v in matrix.items() if 2 <= h + a <= 3) / total
    p_band_4_6 = sum(v for (h, a), v in matrix.items() if h + a >= 4) / total

    # HT/FT approximation (assume goals distributed uniformly across halves)
    # P(home leads at HT and wins FT) ~ p_home^2 (rough approximation)
    p_htft_hh = p_home * p_home * 0.85  # home/home
    p_htft_aa = p_away * p_away * 0.85  # away/away
    p_htft_dd = p_draw * 0.55           # draw/draw

    # First half goals (approximate: ~42% of goals scored in 1st half)
    fh_lam_h = lam_h * 0.42
    fh_lam_a = lam_a * 0.42
    fh_total = fh_lam_h + fh_lam_a
    p_fh_over_0_5 = 1.0 - math.exp(-fh_total)
    p_fh_over_1_5 = 1.0 - math.exp(-fh_total) * (1 + fh_total)
    p_fh_btts = (1.0 - math.exp(-fh_lam_h)) * (1.0 - math.exp(-fh_lam_a))

    # Winning margin
    p_home_by_1 = sum(v for (h, a), v in matrix.items() if h - a == 1) / total
    p_home_by_2 = sum(v for (h, a), v in matrix.items() if h - a == 2) / total
    p_away_by_1 = sum(v for (h, a), v in matrix.items() if a - h == 1) / total
    p_away_by_2 = sum(v for (h, a), v in matrix.items() if a - h == 2) / total
    p_score_draw = sum(v for (h, a), v in matrix.items() if h == a and h > 0) / total

    # Team to score in both halves (approx)
    p_home_both_halves = (1.0 - math.exp(-fh_lam_h)) * (1.0 - math.exp(-lam_h * 0.58))
    p_away_both_halves = (1.0 - math.exp(-fh_lam_a)) * (1.0 - math.exp(-lam_a * 0.58))

    # Highest scoring half
    p_1st_half_higher = 0.35 if fh_total > lam_h * 0.58 + lam_a * 0.58 else 0.28
    p_2nd_half_higher = 0.45  # 2nd half typically has more goals
    p_equal_halves = 1.0 - p_1st_half_higher - p_2nd_half_higher

    # Combo: BTTS & Match Result
    p_btts_home_win = sum(v for (h, a), v in matrix.items() if h > a and h > 0 and a > 0) / total
    p_btts_away_win = sum(v for (h, a), v in matrix.items() if a > h and h > 0 and a > 0) / total
    p_btts_draw     = sum(v for (h, a), v in matrix.items() if h == a and h > 0 and a > 0) / total

    # Combo: Double Chance & Over 2.5
    p_dc1x_o25 = sum(v for (h, a), v in matrix.items() if h >= a and h + a >= 3) / total
    p_dcx2_o25 = sum(v for (h, a), v in matrix.items() if a >= h and h + a >= 3) / total

    # Corners estimation (from xG: ~3.5 corners per expected goal as industry proxy)
    est_corners = (lam_h + lam_a) * 3.5
    # Cards estimation (~0.18 cards per foul, ~22 fouls per game avg, scaled by intensity)
    intensity = (lam_h + lam_a) / 2.6  # 2.6 is avg total goals
    est_cards = 4.2 * intensity
    est_fouls = 22 * intensity

    # ── Build candidate pool: (market_category, market_name, selection, probability, risk, reasoning) ──
    candidates = []
    HN = home_team_name
    AN = away_team_name

    # ── Derive real betting odds implied probs if available ──
    odds_home_implied = None
    odds_draw_implied = None
    odds_away_implied = None
    odds_over25_implied = None
    odds_btts_implied = None
    if match_odds and 'match_odds' in match_odds:
        try:
            o = match_odds['match_odds']
            oh = float(o['home']['last_seen'])
            od = float(o['draw']['last_seen'])
            oa = float(o['away']['last_seen'])
            ov = oh * od * oa
            odds_home_implied = round(1/oh * 100, 1)
            odds_draw_implied = round(1/od * 100, 1)
            odds_away_implied = round(1/oa * 100, 1)
        except Exception: pass
    if match_odds and 'total_goals' in match_odds:
        try:
            o25 = match_odds['total_goals']['2.5']
            odds_over25_implied = round(1/float(o25['over']['last_seen']) * 100, 1)
        except Exception: pass
    if match_odds and 'btts' in match_odds:
        try:
            odds_btts_implied = round(1/float(match_odds['btts']['yes']['last_seen']) * 100, 1)
        except Exception: pass

    # ── Helper to add odds context to reasoning ──
    def odds_context(implied_pct, label=""):
        if implied_pct is None:
            return ""
        return f" Market implies {implied_pct}% — {'aligned' if abs(implied_pct - 0) < 10 else 'model sees edge'}."

    # Dominant attacker?
    h_dominant = lam_h > lam_a * 1.3
    a_dominant = lam_a > lam_h * 1.3
    balanced = not h_dominant and not a_dominant
    xg_line = f"{HN} xG {round(lam_h,2)} vs {AN} xG {round(lam_a,2)}"

    # === MATCH OUTCOME & CORE ===
    if h_dominant:
        hw_reason = f"{HN} generating {round(lam_h,2)} xG — 30% higher than {AN}'s {round(lam_a,2)}. Clear statistical advantage. {odds_context(odds_home_implied)}"
    elif a_dominant:
        hw_reason = f"{HN} xG of {round(lam_h,2)} falls short of {AN}'s {round(lam_a,2)} xG output — difficult home win."
    else:
        hw_reason = f"Even contest. {xg_line}. Home advantage nudges {HN} ahead slightly. {odds_context(odds_home_implied)}"

    if a_dominant:
        aw_reason = f"{AN} generating {round(lam_a,2)} xG on the road — dominant output. {HN} at risk. {odds_context(odds_away_implied)}"
    elif h_dominant:
        aw_reason = f"{AN} xG of {round(lam_a,2)} makes an away win difficult against {HN}'s {round(lam_h,2)} xG."
    else:
        aw_reason = f"Tight match. {AN} in form away from home based on xG data. {odds_context(odds_away_implied)}"

    draw_gap = abs(lam_h - lam_a)
    dr_reason = f"xG gap is only {round(draw_gap,2)} — {'very evenly matched, draw is a live outcome' if draw_gap < 0.3 else 'some gap between sides but draw still possible at {round(p_draw*100)}%'}."

    candidates.append(('MATCH_RESULT', '1X2 Full Time', f'{HN} Win', p_home, 'MEDIUM', hw_reason))
    candidates.append(('MATCH_RESULT', '1X2 Full Time', f'{AN} Win', p_away, 'MEDIUM', aw_reason))
    candidates.append(('MATCH_RESULT', '1X2 Full Time', 'Draw', p_draw, 'HIGH', dr_reason))

    dc1x_reason = f"{HN} covers both win and draw. Only {round(p_away*100,1)}% chance they lose outright based on {xg_line}."
    dcx2_reason = f"{AN} covers both win and draw. Only {round(p_home*100,1)}% chance {HN} wins outright."
    dc12_reason = f"Neither side sees draw as the likeliest scenario. Draw probability is only {round(p_draw*100,1)}%."
    candidates.append(('DOUBLE_CHANCE', 'Double Chance FT', f'{HN} or Draw (1X)', p_1X, 'LOW', dc1x_reason))
    candidates.append(('DOUBLE_CHANCE', 'Double Chance FT', f'{AN} or Draw (X2)', p_X2, 'LOW', dcx2_reason))
    candidates.append(('DOUBLE_CHANCE', 'Double Chance FT', f'{HN} or {AN} (12)', p_12, 'MEDIUM', dc12_reason))

    candidates.append(('DRAW_NO_BET', 'Draw No Bet FT', f'{HN} DNB', p_dnb_home, 'LOW', f"Removes draw risk. Pure win probability: {round(p_dnb_home*100,1)}% in favour of {HN}."))
    candidates.append(('DRAW_NO_BET', 'Draw No Bet FT', f'{AN} DNB', p_dnb_away, 'LOW', f"Removes draw risk. Pure win probability: {round(p_dnb_away*100,1)}% in favour of {AN}."))

    # === GOAL TOTALS ===
    total_xg = round(lam_h + lam_a, 2)
    o05_reason = f"Combined xG of {total_xg} — goalless draws occur in only {round((1-p_over_0_5)*100,1)}% of games at this xG level."
    o15_reason = f"xG of {total_xg} puts 2+ goals at {round(p_over_1_5*100,1)}% probability. {odds_context(None)}"
    o25_reason = f"xG {total_xg} — Over 2.5 at {round(p_over_2_5*100,1)}%. {'Attacking game expected.' if lam_h+lam_a>2.5 else 'Tight, defensive match projected.'} {odds_context(odds_over25_implied)}"
    u25_reason = f"Only {round(p_over_2_5*100,1)}% chance of 3+ goals. xG of {total_xg} favors a tight contest."
    o35_reason = f"High-scoring fixture required. xG {total_xg} — probability is {round(p_over_3_5*100,1)}%, risky."
    u35_reason = f"{round(p_under_3_5*100,1)}% chance of 3 goals or fewer. Low xG of {total_xg} backs this."

    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Over 0.5 Goals', p_over_0_5, 'LOW', o05_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Over 1.5 Goals', p_over_1_5, 'LOW', o15_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Over 2.5 Goals', p_over_2_5, 'MEDIUM', o25_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Under 2.5 Goals', p_under_2_5, 'MEDIUM', u25_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Over 3.5 Goals', p_over_3_5, 'HIGH', o35_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Under 3.5 Goals', p_under_3_5, 'LOW', u35_reason))
    candidates.append(('GOAL_TOTALS', 'Total Goals O/U', 'Under 4.5 Goals', p_under_4_5, 'LOW', f"Extreme score unlikely. {round(p_under_4_5*100,1)}% chance of 4 or fewer goals at this xG level."))

    # === BTTS ===
    btts_yes_reason = f"{HN} xG {round(lam_h,2)} & {AN} xG {round(lam_a,2)} — both sides project to score in {round(p_btts_yes*100,1)}% of scenarios. {odds_context(odds_btts_implied)}"
    btts_no_reason = f"At least one team ({HN if lam_h < lam_a else AN}, xG {round(min(lam_h,lam_a),2)}) projected to be kept scoreless {round(p_btts_no*100,1)}% of the time."
    candidates.append(('BTTS', 'Both Teams To Score FT', 'BTTS: Yes', p_btts_yes, 'MEDIUM', btts_yes_reason))
    candidates.append(('BTTS', 'Both Teams To Score FT', 'BTTS: No', p_btts_no, 'MEDIUM', btts_no_reason))

    # === FIRST HALF ===
    fh_xg = round(fh_lam_h + fh_lam_a, 2)
    candidates.append(('FIRST_HALF', '1st Half Over/Under', '1H Over 0.5 Goals', p_fh_over_0_5, 'LOW', f"1st half projected xG of {fh_xg}. {round(p_fh_over_0_5*100,1)}% chance of at least one goal before break."))
    candidates.append(('FIRST_HALF', '1st Half Over/Under', '1H Over 1.5 Goals', p_fh_over_1_5, 'MEDIUM', f"1st half xG {fh_xg} — two goals before break at {round(p_fh_over_1_5*100,1)}% probability."))
    candidates.append(('FIRST_HALF', '1st Half BTTS', '1H BTTS: Yes', p_fh_btts, 'HIGH', f"Both teams score in the 1st half — {round(p_fh_btts*100,1)}% probability. High risk bet."))

    # === HOME/AWAY TEAM GOALS ===
    candidates.append(('TEAM_GOALS', f'{HN} Total Goals', f'{HN} Over 0.5 Goals', p_home_over_0_5, 'LOW', f"{HN} xG of {round(lam_h,2)} — {round(p_home_over_0_5*100,1)}% chance they score at least once."))
    candidates.append(('TEAM_GOALS', f'{HN} Total Goals', f'{HN} Over 1.5 Goals', p_home_over_1_5, 'MEDIUM', f"{HN} xG {round(lam_h,2)} — multi-goal output at {round(p_home_over_1_5*100,1)}%. {'Strong attack.' if lam_h > 1.5 else 'Modest attack.'}"))
    candidates.append(('TEAM_GOALS', f'{AN} Total Goals', f'{AN} Over 0.5 Goals', p_away_over_0_5, 'LOW', f"{AN} xG of {round(lam_a,2)} — {round(p_away_over_0_5*100,1)}% chance they find the net."))
    candidates.append(('TEAM_GOALS', f'{AN} Total Goals', f'{AN} Over 1.5 Goals', p_away_over_1_5, 'MEDIUM', f"{AN} xG {round(lam_a,2)} — scoring 2+ goals on the road at {round(p_away_over_1_5*100,1)}%."))

    # === CLEAN SHEETS ===
    candidates.append(('CLEAN_SHEET', f'{HN} Clean Sheet', f'{HN} Clean Sheet: Yes', p_home_cs, 'HIGH', f"{AN} xG {round(lam_a,2)} is projected — clean sheet probability {round(p_home_cs*100,1)}%. {'Possible with low away xG.' if lam_a < 1.0 else 'Difficult with that away xG.'}"))
    candidates.append(('CLEAN_SHEET', f'{AN} Clean Sheet', f'{AN} Clean Sheet: Yes', p_away_cs, 'HIGH', f"{HN} xG {round(lam_h,2)} — keeping a clean sheet away at {round(p_away_cs*100,1)}%. {'Feasible.' if lam_h < 1.0 else 'Tough ask.'}"))
    candidates.append(('CLEAN_SHEET', f'{HN} Clean Sheet', f'{HN} Clean Sheet: No', 1-p_home_cs, 'LOW', f"{AN} projects to score in {round((1-p_home_cs)*100,1)}% of scenarios given their {round(lam_a,2)} xG."))
    candidates.append(('CLEAN_SHEET', f'{AN} Clean Sheet', f'{AN} Clean Sheet: No', 1-p_away_cs, 'LOW', f"{HN} projects to score in {round((1-p_away_cs)*100,1)}% of scenarios with their {round(lam_h,2)} xG."))

    # === WIN TO NIL ===
    candidates.append(('WIN_TO_NIL', 'Home Win To Nil', f'{HN} Win To Nil', p_home_wtn, 'HIGH', f"{HN} wins without conceding — {round(p_home_wtn*100,1)}%. Requires both {round(lam_h,2)} attack and {round(lam_a,2)} xG suppressed to 0."))
    candidates.append(('WIN_TO_NIL', 'Away Win To Nil', f'{AN} Win To Nil', p_away_wtn, 'HIGH', f"{AN} shuts out the home side and wins — {round(p_away_wtn*100,1)}%. Rare away clean sheet scenario."))

    # === ODD/EVEN ===
    candidates.append(('ODD_EVEN', 'Odd/Even Total Goals', 'Odd Total Goals', p_odd_total, 'MEDIUM', f"Poisson distribution at xG {total_xg} gives {round(p_odd_total*100,1)}% probability of an odd goal count."))
    candidates.append(('ODD_EVEN', 'Odd/Even Total Goals', 'Even Total Goals', p_even_total, 'MEDIUM', f"Even total goals probability is {round(p_even_total*100,1)}% based on xG {total_xg}."))

    # === GOAL BANDS ===
    candidates.append(('GOAL_BANDS', 'Goal Band', '0-1 Total Goals', p_band_0_1, 'HIGH', f"Very low-scoring affair — {round(p_band_0_1*100,1)}% chance of 0 or 1 goal given xG {total_xg}."))
    candidates.append(('GOAL_BANDS', 'Goal Band', '2-3 Total Goals', p_band_2_3, 'MEDIUM', f"Standard scoring range — {round(p_band_2_3*100,1)}% probability. Most likely goal band for xG {total_xg}."))
    candidates.append(('GOAL_BANDS', 'Goal Band', '4-6 Total Goals', p_band_4_6, 'HIGH', f"High-scoring fixture — {round(p_band_4_6*100,1)}% chance. Requires both sides to outperform xG of {total_xg}."))

    # === HALFTIME/FULLTIME ===
    candidates.append(('HT_FT', 'HT/FT Result', f'{HN}/{HN} (HT/FT)', p_htft_hh, 'HIGH', f"{HN} leads at both intervals — {round(p_htft_hh*100,1)}%. Requires consistent dominance across 90 mins."))
    candidates.append(('HT_FT', 'HT/FT Result', f'{AN}/{AN} (HT/FT)', p_htft_aa, 'HIGH', f"{AN} controls from kick-off — {round(p_htft_aa*100,1)}%. Away dominance scenario."))
    candidates.append(('HT_FT', 'HT/FT Result', 'Draw/Draw (HT/FT)', p_htft_dd, 'HIGH', f"Locked at half and full time — {round(p_htft_dd*100,1)}%. Both sides failing to separate."))

    # === HIGHEST SCORING HALF ===
    candidates.append(('SCORING_HALF', 'Highest Scoring Half', '2nd Half', p_2nd_half_higher, 'MEDIUM', f"Statistically, {round(p_2nd_half_higher*100,1)}% of matches produce more goals in the 2nd half as teams open up."))

    # === WINNING MARGIN ===
    candidates.append(('WINNING_MARGIN', 'Winning Margin', f'{HN} by 1 Goal', p_home_by_1, 'HIGH', f"Most likely specific outcome if {HN} win — {round(p_home_by_1*100,1)}% from Poisson matrix."))
    candidates.append(('WINNING_MARGIN', 'Winning Margin', f'{AN} by 1 Goal', p_away_by_1, 'HIGH', f"Narrow away win — {round(p_away_by_1*100,1)}% probability from score distribution."))

    # === COMBO: BTTS & RESULT ===
    candidates.append(('COMBO', 'BTTS & Result', f'{HN} Win & BTTS', p_btts_home_win, 'HIGH', f"{HN} wins while conceding — {round(p_btts_home_win*100,1)}%. Requires {round(lam_h,2)} attack to outshine {round(lam_a,2)} in open game."))
    candidates.append(('COMBO', 'BTTS & Result', f'{AN} Win & BTTS', p_btts_away_win, 'HIGH', f"{AN} wins in an open game — {round(p_btts_away_win*100,1)}%. Both teams score but {AN} edge it."))

    # === COMBO: DC & O2.5 ===
    candidates.append(('COMBO', 'DC & Over 2.5', f'{HN} or Draw & Over 2.5', p_dc1x_o25, 'MEDIUM', f"{HN} avoids loss + 3 goals — {round(p_dc1x_o25*100,1)}%. Requires attacking game with xG {total_xg}."))
    candidates.append(('COMBO', 'DC & Over 2.5', f'{AN} or Draw & Over 2.5', p_dcx2_o25, 'MEDIUM', f"{AN} avoids loss + 3 goals — {round(p_dcx2_o25*100,1)}%."))

    # === TEAM TO SCORE BOTH HALVES ===
    candidates.append(('TEAM_BOTH_HALVES', f'{HN} Score Both Halves', f'{HN} Score in Both Halves', p_home_both_halves, 'HIGH', f"{HN} xG {round(lam_h,2)} spread across 90 mins — {round(p_home_both_halves*100,1)}% chance they score in both halves."))
    candidates.append(('TEAM_BOTH_HALVES', f'{AN} Score Both Halves', f'{AN} Score in Both Halves', p_away_both_halves, 'HIGH', f"{AN} xG {round(lam_a,2)} — {round(p_away_both_halves*100,1)}% chance of scoring in both halves."))

    # === CORNERS (estimated) ===
    p_corners_over_8_5 = max(0.0, min(1.0, 0.5 + (est_corners - 9.5) * 0.12))
    p_corners_over_9_5 = max(0.0, min(1.0, 0.5 + (est_corners - 10.5) * 0.12))
    p_corners_over_10_5 = max(0.0, min(1.0, 0.5 + (est_corners - 11.5) * 0.12))
    candidates.append(('CORNERS', 'Total Corners O/U', f'Over 8.5 Corners', p_corners_over_8_5, 'MEDIUM', f"Projected {round(est_corners,1)} corners (3.5x xG proxy). Over 8.5 at {round(p_corners_over_8_5*100,1)}%."))
    candidates.append(('CORNERS', 'Total Corners O/U', f'Under 9.5 Corners', 1.0-p_corners_over_9_5, 'MEDIUM', f"Under 9.5 corners — {round((1-p_corners_over_9_5)*100,1)}% from {round(est_corners,1)} projected."))
    candidates.append(('CORNERS', 'Total Corners O/U', f'Over 10.5 Corners', p_corners_over_10_5, 'HIGH', f"Over 10.5 corners — {round(p_corners_over_10_5*100,1)}%. Requires high-pressing tactics."))

    # === CARDS (estimated) ===
    p_cards_over_3_5 = max(0.0, min(1.0, 0.5 + (est_cards - 4.0) * 0.15))
    p_cards_over_4_5 = max(0.0, min(1.0, 0.5 + (est_cards - 5.0) * 0.15))
    candidates.append(('CARDS', 'Total Cards O/U', f'Over 3.5 Cards', p_cards_over_3_5, 'MEDIUM', f"Estimated {round(est_cards,1)} cards from match intensity (xG {total_xg}). Over 3.5 at {round(p_cards_over_3_5*100,1)}%."))
    candidates.append(('CARDS', 'Total Cards O/U', f'Over 4.5 Cards', p_cards_over_4_5, 'HIGH', f"Heated contest projection — over 4.5 cards at {round(p_cards_over_4_5*100,1)}%."))

    # ── Calculate Implied Odds & Dynamic Value Score ──
    # The AI adjusts risk appetite based on ML confidence.
    # Score = prob * (implied_odds^1.5) but penalize 'too safe' (prob > 80% / odds < 1.25)
    
    scored_candidates = []
    for c in candidates:
        cat, m_name, sel, p, risk, reason = c
        if p <= 0: continue
        
        implied_odds = 1.0 / p
        
        # AI Dynamic Value Score:
        # We want the HIGHEST probability, but we heavily penalize "useless" bets (odds < 1.20 / prob > 82%)
        # This forces the AI to find the "Safe but Valuable" sweet spot.
        value_score = p
        if p > 0.90:
            value_score = p * 0.2  # Extreme penalty for things like Over 0.5 Goals
        elif p > 0.82:
            value_score = p * 0.6  # Moderate penalty
        elif p < 0.50:
            value_score = p * 0.8  # Slight penalty for risky bets to keep the Primary Pick safe
            
        scored_candidates.append({
            'cat': cat, 'm_name': m_name, 'sel': sel, 'p': p, 'risk': risk, 'reason': reason,
            'implied_odds': implied_odds, 'score': value_score
        })

    # Sort by the AI's Value Score
    scored_candidates.sort(key=lambda x: x['score'], reverse=True)

    # Determine match volatility
    max_1x2 = max(p_home, p_draw, p_away)
    volatility = "HIGH" if max_1x2 < 0.40 else ("MEDIUM" if max_1x2 < 0.55 else "LOW")

    # Pick the top 3 unique market categories
    used_cats = set()
    top_picks = []
    for c in scored_candidates:
        if c['cat'] not in used_cats and c['p'] >= 0.45:  # still maintain a baseline of 45% probability
            top_picks.append(c)
            used_cats.add(c['cat'])
        if len(top_picks) >= 3:
            break

    # If we couldn't find 3, relax and fill
    if len(top_picks) < 3:
        for c in scored_candidates:
            if c not in top_picks:
                top_picks.append(c)
            if len(top_picks) >= 3:
                break

    def _make_pick(c):
        return {
            'market_category': c['cat'],
            'market_name': c['m_name'],
            'selection': c['sel'],
            'confidence_score': round(c['p'] * 100),
            'risk_level': c['risk'],
            'reasoning': c['reason']
        }

    primary = _make_pick(top_picks[0]) if len(top_picks) > 0 else {}
    value   = _make_pick(top_picks[1]) if len(top_picks) > 1 else {}
    stat    = _make_pick(top_picks[2]) if len(top_picks) > 2 else {}

    # Build full market scan for dashboard (all candidates above 45%)
    all_markets = [_make_pick(c) for c in scored_candidates if c['p'] >= 0.45]

    return {
        'home_win':    round(p_home * 100, 1),
        'draw':        round(p_draw * 100, 1),
        'away_win':    round(p_away * 100, 1),
        'btts':        round(p_btts_yes * 100, 1),
        'over_1_5':    round(p_over_1_5 * 100, 1),
        'over_2_5':    round(p_over_2_5 * 100, 1),
        'over_3_5':    round(p_over_3_5 * 100, 1),
        'dc_home_draw': round(p_dc_home_draw * 100, 1),
        'dc_away_draw': round(p_dc_away_draw * 100, 1),
        'top_scores':  top_scores,
        'xg_home':     round(lam_h, 2),
        'xg_away':     round(lam_a, 2),
        'ml_blend':    ml_confidence,
        'low_data_warning': low_data_warning,
        'expert_predictions': {
            'volatility': volatility,
            'primary': primary,
            'value': value,
            'stat': stat,
            'all_markets': all_markets
        }
    }

class APIFootballClient:
    """Thin wrapper for backward compatibility with predict_today.py"""
    def get_todays_fixtures(self, leagues=None, status_filter='upcoming'):
        items = get_fixtures_for_date(date.today().isoformat(), leagues)
        if status_filter == 'upcoming':
            return [i for i in items if i['status'] in UPCOMING_STATUSES]
        if status_filter == 'ongoing':
            return [i for i in items if i['status'] not in UPCOMING_STATUSES and i['status'] not in FINISHED_STATUSES]
        return items

    def get_team_last_matches(self, team_id, last=6, season=2024):
        # We don't need season here, just last 6 finished matches
        data = _get('matches', {'team_id': team_id, 'limit': last, 'status': 'finished'}, ttl=3600)
        if not data or 'data' not in data:
            return []
        # Return format expected by FeatureBuilderLive: list of matches with 'teams': {'home': {'id', 'winner'}}
        res = []
        for m in data['data']:
            hg = m['score'].get('home') or 0
            ag = m['score'].get('away') or 0
            res.append({
                'fixture': {'timestamp': int(datetime.fromisoformat(m['utc_date'].replace('Z', '+00:00')).timestamp())},
                'teams': {
                    'home': {'id': m['home_team']['id'], 'winner': True if hg > ag else (False if hg < ag else None)},
                    'away': {'id': m['away_team']['id'], 'winner': True if ag > hg else (False if ag < hg else None)},
                },
                'goals': {'home': hg, 'away': ag}
            })
        return res

    def get_fixture_odds(self, fixture_id):
        return get_match_odds(fixture_id)
        
    def extract_match_winner_odds(self, fixture_odds):
        try:
            if fixture_odds and 'match_odds' in fixture_odds:
                o = fixture_odds['match_odds']
                return {
                    'home': float(o['home']['last_seen']),
                    'draw': float(o['draw']['last_seen']),
                    'away': float(o['away']['last_seen'])
                }
        except:
            pass
        return None
