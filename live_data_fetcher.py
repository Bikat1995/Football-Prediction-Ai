import os
import requests
import json
import time
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class APIFootballClient:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key=None):
        """
        Initialize API-Football v3
        Get your API key from: https://api-football.com/
        """
        self.api_key = api_key or os.getenv('API_FOOTBALL_KEY', 'YOUR_API_FOOTBALL_KEY')
        self.base_url = self.BASE_URL
        self.headers = {
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        self.cache_dir = "cache/api_football"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = {}
        self.cache_ttl = 1800  # 30 minutes

    def _get_cache_path(self, endpoint, params):
        param_str = "_".join([f"{k}_{v}" for k, v in sorted(params.items())])
        filename = f"{endpoint.replace('/', '_')}_{param_str}.json"
        return os.path.join(self.cache_dir, filename)

    def _get_cache_key(self, endpoint, params):
        param_str = "_".join([f"{k}_{v}" for k, v in sorted(params.items())])
        return f"{endpoint.replace('/', '_')}_{param_str}"

    def _is_cache_valid(self, cache_key):
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        if cache_path in self.cache:
            return True
        if os.path.exists(cache_path):
            file_mtime = os.path.getmtime(cache_path)
            if time.time() - file_mtime < 1800:
                with open(cache_path, 'r') as f:
                    self.cache[cache_key] = json.load(f)
                return True
        return False

    def _set_cache(self, cache_key, data):
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        with open(cache_path, 'w') as f:
            json.dump({'data': data}, f)
        self.cache[cache_key] = {'data': data}

    def _get(self, endpoint, params=None, ttl=None):
        params = params or {}
        cache_key = self._get_cache_key(endpoint, params)

        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]

        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            self._set_cache(cache_key, data)
            return {'data': data}
        except Exception as e:
            print(f"API-Football Request Failed: {e}")
            return None

    def get_todays_fixtures(self, leagues=None, status_filter=None):
        """Fetch fixtures for today's date with optional status filtering.
        status_filter can be 'upcoming', 'ongoing', or None for all.
        """
        today = date.today().isoformat()
        params = {'date': today}
        
        # Use cache heavily for today's overall matches to minimize API calls
        cache_key = self._get_cache_key('fixtures', params)
        if self._is_cache_valid(cache_key):
            data = self.cache[cache_key]
        else:
            data = self._get('fixtures', params)
            
        fixtures = []
        payload = data.get('data', data) if data else None
        
        if payload and 'response' in payload:
            for item in payload['response']:
                league_id = item['league']['id']
                if leagues is None or league_id in leagues:
                    status = item['fixture']['status']['short']
                    
                    if status_filter == 'upcoming':
                        if status not in ['NS', 'TBD']:
                            continue
                    elif status_filter == 'ongoing':
                        if status in ['FT', 'AET', 'PEN', 'NS', 'TBD', 'CANC', 'PST', 'ABD', 'AWD', 'WO']:
                            continue
                            
                    fixtures.append(item)
                    
        return fixtures

    def get_team_last_matches(self, team_id, last=6, season=2024):
        """Fetch last N matches for a team to calculate form (Workaround for free plan using 2024)"""
        params = {'team': team_id, 'season': season}
        data = self._get('fixtures', params)
        payload = data.get('data', data) if data else None
        if payload and 'response' in payload:
            finished = [m for m in payload['response'] if m['fixture']['status']['short'] in ['FT', 'AET', 'PEN']]
            finished.sort(key=lambda x: x['fixture']['timestamp'], reverse=True)
            return finished[:last]
        return []

    def get_league_standings(self, league_id, season=2025):
        """Fetch current league standings"""
        params = {'league': league_id, 'season': season}
        data = self._get('standings', params)
        payload = data.get('data', data) if data else None
        if payload and 'response' in payload:
            return payload['response'][0]['league']['standings'][0]
        return []

    def get_team_season_stats(self, league_id, team_id, season=2025):
        """Fetch detailed season stats for a team"""
        params = {'league': league_id, 'team': team_id, 'season': season}
        data = self._get('teams/statistics', params)
        payload = data.get('data', data) if data else None
        return payload['response'] if payload and 'response' in payload else {}

    def get_fixture_odds(self, fixture_id):
        """Fetch pre-match odds for a specific fixture."""
        data = self._get('odds', {'fixture': fixture_id})
        payload = data.get('data', data) if data else None
        return payload['response'][0] if payload and payload.get('response') else None

    def get_odds_by_date(self, date_value=None, league_id=None):
        """Fetch pre-match odds for a date and optionally filter by league."""
        params = {'date': date_value or date.today().isoformat()}
        if league_id:
            params['league'] = league_id

        data = self._get('odds', params)
        payload = data.get('data', data) if data else None
        return payload.get('response', []) if payload else []

    def extract_match_winner_odds(self, odds_data):
        """Extract best home/draw/away prices from API-Football odds response."""
        best_odds = {'home': 0.0, 'draw': 0.0, 'away': 0.0}

        if not odds_data or 'bookmakers' not in odds_data:
            return best_odds

        for bookmaker in odds_data['bookmakers']:
            for bet in bookmaker.get('bets', []):
                if bet.get('name') != 'Match Winner':
                    continue

                for value in bet.get('values', []):
                    label = value.get('value')
                    odd = value.get('odd')

                    try:
                        odd_value = float(odd)
                    except (TypeError, ValueError):
                        continue

                    if label == 'Home':
                        best_odds['home'] = max(best_odds['home'], odd_value)
                    elif label == 'Draw':
                        best_odds['draw'] = max(best_odds['draw'], odd_value)
                    elif label == 'Away':
                        best_odds['away'] = max(best_odds['away'], odd_value)

        return best_odds

class OddsAPIClient:
    """Client for odds-api.io"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('ODDS_API_IO_KEY')
        self.cache_dir = "cache/odds_api"
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, endpoint, params):
        param_str = "_".join([f"{k}_{v}" for k, v in sorted(params.items())])
        filename = f"{endpoint.replace('/', '_')}_{param_str}.json"
        return os.path.join(self.cache_dir, filename)

    def _get(self, endpoint, params=None, ttl=1800):
        cache_path = self._get_cache_path(endpoint, params or {})
        
        if os.path.exists(cache_path):
            if time.time() - os.path.getmtime(cache_path) < ttl:
                with open(cache_path, 'r') as f:
                    return json.load(f)

        url = f"{self.BASE_URL}/{endpoint}"
        p = {'apiKey': self.api_key}
        if params:
            p.update(params)
            
        try:
            response = requests.get(url, params=p)
            response.raise_for_status()
            data = response.json()
            
            with open(cache_path, 'w') as f:
                json.dump(data, f)
            return data
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", "unknown")
            print(f"Odds-API Request Failed with status {status_code}")
            return None

    def get_odds(self, league_key="soccer_italy_serie_a"):
        """Fetch odds for a specific league"""
        params = {
            'regions': 'uk,eu',
            'markets': 'h2h'
        }
        data = self._get(f'sports/{league_key}/odds', params)
        return data if data else []

if __name__ == "__main__":
    # Quick test
    client = APIFootballClient()
    print("Testing API-Football Client...")
    fixtures = client.get_todays_fixtures(leagues=[39]) # Premier League
    print(f"Found {len(fixtures)} fixtures for today.")
