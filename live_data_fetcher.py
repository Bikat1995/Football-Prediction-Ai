import os
import requests
import json
import time
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# KEY 1 (API_FOOTBALL_KEY)  → Fixtures, Live, Predictions  (real-time data)
# KEY 2 (API_FOOTBALL_KEY_2) → Team stats, Top scorers, Top assists (deep stats)
# Each key = 100 requests/day on free tier → 200 total
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://v3.football.api-sports.io"
CACHE_DIR = "cache/api_football"
os.makedirs(CACHE_DIR, exist_ok=True)

LIVE_STATUSES    = {'1H', '2H', 'HT', 'ET', 'P', 'BT', 'LIVE', 'INT'}
FINISHED_STATUSES = {'FT', 'AET', 'PEN', 'CANC', 'PST', 'ABD', 'AWD', 'WO'}
UPCOMING_STATUSES = {'NS', 'TBD'}


def _headers(key: str) -> dict:
    return {
        'x-rapidapi-key': key,
        'x-rapidapi-host': 'v3.football.api-sports.io'
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


def _get(endpoint: str, params: dict, api_key: str, ttl: int = 1800):
    ck = _cache_key(endpoint, params)
    cached = _read_cache(ck, ttl)
    if cached:
        return cached

    try:
        r = requests.get(f"{BASE_URL}/{endpoint}",
                         headers=_headers(api_key),
                         params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        _write_cache(ck, data)
        return data
    except Exception as e:
        print(f"[API] {endpoint} failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# KEY 1 FUNCTIONS — Fixtures · Live · Predictions
# ─────────────────────────────────────────────────────────────────────────────

KEY1 = os.getenv('API_FOOTBALL_KEY', '')


def get_fixtures_for_date(target_date: str, leagues=None) -> list:
    """All fixtures for a given date (ISO string). No status filtering."""
    data = _get('fixtures', {'date': target_date}, KEY1, ttl=300)
    if not data or 'response' not in data:
        return []
    items = data['response']
    if leagues:
        items = [i for i in items if i['league']['id'] in leagues]
    return items


def get_upcoming_fixtures(leagues=None) -> list:
    """Today + Tomorrow upcoming (NS/TBD) fixtures."""
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    today_fix    = get_fixtures_for_date(today, leagues)
    tomorrow_fix = get_fixtures_for_date(tomorrow, leagues)

    all_fix = today_fix + tomorrow_fix
    return [f for f in all_fix
            if f['fixture']['status']['short'] in UPCOMING_STATUSES]


def get_live_fixtures(leagues=None) -> list:
    """Currently in-play matches."""
    # Live endpoint — very short TTL (30 seconds)
    ck = _cache_key('fixtures_live', {'live': 'all'})
    cached = _read_cache(ck, ttl=30)
    if cached:
        data = cached
    else:
        try:
            r = requests.get(f"{BASE_URL}/fixtures",
                             headers=_headers(KEY1),
                             params={'live': 'all'}, timeout=15)
            r.raise_for_status()
            data = r.json()
            _write_cache(ck, data)
        except Exception as e:
            print(f"[API] live fixtures failed: {e}")
            return []

    if not data or 'response' not in data:
        return []
    items = data['response']
    if leagues:
        items = [i for i in items if i['league']['id'] in leagues]
    return items


def get_fixture_predictions(fixture_id: int) -> dict | None:
    """Deep prediction data for a fixture."""
    data = _get('predictions', {'fixture': fixture_id}, KEY1, ttl=3600)
    if data and 'response' in data and data['response']:
        return data['response'][0]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# KEY 2 FUNCTIONS — Team Stats · Top Players
# ─────────────────────────────────────────────────────────────────────────────

KEY2 = os.getenv('API_FOOTBALL_KEY_2', '')


def get_team_season_stats(team_id: int, league_id: int, season: int) -> dict:
    """Season statistics for a team — used for Poisson model."""
    data = _get('teams/statistics',
                {'team': team_id, 'league': league_id, 'season': season},
                KEY2, ttl=86400)   # cache 24h — stats don't change mid-day
    return data.get('response', {}) if data else {}


def get_league_top_scorers(league_id: int, season: int) -> list:
    data = _get('players/topscorers',
                {'league': league_id, 'season': season},
                KEY2, ttl=86400)
    return data.get('response', []) if data else []


def get_league_top_assists(league_id: int, season: int) -> list:
    data = _get('players/topassists',
                {'league': league_id, 'season': season},
                KEY2, ttl=86400)
    return data.get('response', []) if data else []


# ─────────────────────────────────────────────────────────────────────────────
# POISSON MODEL — Real AI predictions from actual team stats
# ─────────────────────────────────────────────────────────────────────────────

import math
import pickle
import numpy as np

# Load ML Model once
ML_MODEL_DATA = None
try:
    with open('models/xgb_classifier.pkl', 'rb') as f:
        ML_MODEL_DATA = pickle.load(f)
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
                            max_goals: int = 6) -> dict:
    """
    Compute all major betting markets from Poisson + ML ensemble.
    Always returns a prediction. Tracks data confidence per team.
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

    if ML_MODEL_DATA:
        team_stats = ML_MODEL_DATA['team_stats']
        model      = ML_MODEL_DATA['model']
        lg         = ML_MODEL_DATA.get('league_avg', {})
        fallback   = [lg.get('scored', 1.3), lg.get('conceded', 1.1), lg.get('ppg', 1.5)]

        def get_team_feat(name):
            if name in team_stats and team_stats[name]['games'] >= 3:
                g = team_stats[name]['games']
                return [team_stats[name]['scored']/g, team_stats[name]['conceded']/g,
                        team_stats[name]['points']/g], True
            return fallback, False

        h_feat, home_known = get_team_feat(home_team_name)
        a_feat, away_known = get_team_feat(away_team_name)

        ml_weight   = 0.65 if (home_known and away_known) else (0.35 if (home_known or away_known) else 0.0)
        stat_weight = 1.0 - ml_weight

        if ml_weight > 0:
            features = np.array([h_feat + a_feat + [1]], dtype=np.float32)
            try:
                ml_probs = model.predict_proba(features)[0]
                ml_away, ml_draw, ml_home = float(ml_probs[0]), float(ml_probs[1]), float(ml_probs[2])
                p_home = p_home * stat_weight + ml_home * ml_weight
                p_draw = p_draw * stat_weight + ml_draw * ml_weight
                p_away = p_away * stat_weight + ml_away * ml_weight
                # Renormalize so sum == 1.0  (fixes the 41.2000007... bug)
                _s = p_home + p_draw + p_away
                p_home /= _s; p_draw /= _s; p_away /= _s
                ml_confidence = round(ml_weight * 100)
            except Exception:
                pass

        # Build low-data warning + confidence penalty
        if not home_known and not away_known:
            low_data_warning = (f"Limited historical data for both "
                                f"{home_team_name} and {away_team_name}. "
                                f"Prediction is statistical only — treat with caution.")
            # Shrink toward 33.3% base (increases uncertainty signal)
            p_home = p_home * 0.72 + 0.333 * 0.28
            p_draw = p_draw * 0.72 + 0.333 * 0.28
            p_away = p_away * 0.72 + 0.333 * 0.28
            _s = p_home + p_draw + p_away
            p_home /= _s; p_draw /= _s; p_away /= _s
        elif not home_known:
            low_data_warning = (f"Limited historical data for {home_team_name}. "
                                f"Prediction partially estimated.")
        elif not away_known:
            low_data_warning = (f"Limited historical data for {away_team_name}. "
                                f"Prediction partially estimated.")

    # Derived markets from Poisson matrix
    p_btts    = sum(v for (h, a), v in matrix.items() if h >= 1 and a >= 1) / total
    p_over_15 = sum(v for (h, a), v in matrix.items() if h + a > 1) / total
    p_over_25 = sum(v for (h, a), v in matrix.items() if h + a > 2) / total
    p_over_35 = sum(v for (h, a), v in matrix.items() if h + a > 3) / total
    p_dc_home_draw = p_home + p_draw
    p_dc_away_draw = p_away + p_draw

    # Most likely correct scores (top 5) from Poisson baseline
    sorted_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)
    top_scores = [(f"{h}-{a}", round(v / total * 100, 1)) for (h, a), v in sorted_scores[:5]]

    return {
        'home_win':    round(p_home * 100, 1),
        'draw':        round(p_draw * 100, 1),
        'away_win':    round(p_away * 100, 1),
        'btts':        round(p_btts * 100, 1),
        'over_1_5':    round(p_over_15 * 100, 1),
        'over_2_5':    round(p_over_25 * 100, 1),
        'over_3_5':    round(p_over_35 * 100, 1),
        'dc_home_draw': round(p_dc_home_draw * 100, 1),
        'dc_away_draw': round(p_dc_away_draw * 100, 1),
        'top_scores':  top_scores,
        'xg_home':     round(lam_h, 2),
        'xg_away':     round(lam_a, 2),
        'ml_blend':    ml_confidence
    }


# ─────────────────────────────────────────────────────────────────────────────
# Legacy class wrapper (keeps predict_today.py etc working)
# ─────────────────────────────────────────────────────────────────────────────

class APIFootballClient:
    """Thin wrapper around the module-level functions for backward compatibility."""

    def get_todays_fixtures(self, leagues=None, status_filter='upcoming'):
        today = date.today().isoformat()
        items = get_fixtures_for_date(today, leagues)
        if status_filter == 'upcoming':
            return [i for i in items if i['fixture']['status']['short'] in UPCOMING_STATUSES]
        if status_filter == 'ongoing':
            return [i for i in items if i['fixture']['status']['short'] in LIVE_STATUSES]
        return items

    def get_fixture_predictions(self, fixture_id):
        return get_fixture_predictions(fixture_id)

    def get_team_season_stats(self, league_id, team_id, season=2025):
        return get_team_season_stats(team_id, league_id, season)

    def get_league_top_scorers(self, league_id, season=2024):
        return get_league_top_scorers(league_id, season)

    def get_league_top_assists(self, league_id, season=2024):
        return get_league_top_assists(league_id, season)

    def get_team_last_matches(self, team_id, last=6, season=2024):
        data = _get('fixtures', {'team': team_id, 'season': season}, KEY1, ttl=3600)
        if not data or 'response' not in data:
            return []
        finished = [m for m in data['response']
                    if m['fixture']['status']['short'] in FINISHED_STATUSES]
        finished.sort(key=lambda x: x['fixture']['timestamp'], reverse=True)
        return finished[:last]

    def get_league_standings(self, league_id, season=2025):
        data = _get('standings', {'league': league_id, 'season': season}, KEY1, ttl=3600)
        if data and 'response' in data and data['response']:
            return data['response'][0]['league']['standings'][0]
        return []
