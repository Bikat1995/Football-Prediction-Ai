import os
import re

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace get_fixtures_for_date
old_fixtures_date = '''def get_fixtures_for_date(target_date: str, leagues=None) -> list:
    """All fixtures for a given date (YYYY-MM-DD)."""
    # TheStatsAPI date_from and date_to
    data = _get('matches', {'date_from': target_date, 'date_to': target_date, 'limit': 100}, ttl=300)
    if not data or 'data' not in data:
        return []
    items = data['data']
    if leagues:
        items = [i for i in items if i['competition_id'] in leagues]
    return items'''

new_fixtures_date = '''def get_fixtures_for_date(target_date: str, leagues=None) -> list:
    """All fixtures for a given date (YYYY-MM-DD). Fetching per league to avoid pagination limits."""
    if not leagues:
        return []
    all_items = []
    for lg in leagues:
        # Cache for 12 hours since schedules rarely change
        data = _get('matches', {'competition_id': lg, 'date_from': target_date, 'date_to': target_date, 'limit': 100}, ttl=43200)
        if data and 'data' in data:
            all_items.extend(data['data'])
    return all_items'''
code = code.replace(old_fixtures_date, new_fixtures_date)

# Replace get_upcoming_fixtures
old_upcoming = '''def get_upcoming_fixtures(leagues=None) -> list:
    """Today + Tomorrow upcoming fixtures."""
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    # We can fetch date_from=today, date_to=tomorrow
    data = _get('matches', {'date_from': today, 'date_to': tomorrow, 'limit': 200}, ttl=300)
    if not data or 'data' not in data:
        return []
    items = data['data']
    if leagues:
        items = [i for i in items if i['competition_id'] in leagues]
    return [f for f in items if f['status'] in UPCOMING_STATUSES]'''

new_upcoming = '''def get_upcoming_fixtures(leagues=None) -> list:
    """Today + Tomorrow upcoming fixtures. Fetching per league to bypass the 100-match limit globally."""
    if not leagues:
        return []
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    all_items = []
    for lg in leagues:
        # Cache for 3 hours
        data = _get('matches', {'competition_id': lg, 'date_from': today, 'date_to': tomorrow, 'limit': 100}, ttl=10800)
        if data and 'data' in data:
            all_items.extend(data['data'])
    
    return [f for f in all_items if f['status'] in UPCOMING_STATUSES]'''
code = code.replace(old_upcoming, new_upcoming)

# Replace get_live_fixtures
old_live = '''def get_live_fixtures(leagues=None) -> list:
    """Currently in-play matches."""
    today = date.today().isoformat()
    data = _get('matches', {'date_from': today, 'date_to': today, 'limit': 100}, ttl=60)
    if not data or 'data' not in data:
        return []
    items = data['data']
    if leagues:
        items = [i for i in items if i['competition_id'] in leagues]
    
    # Check for anything not finished or scheduled
    return [f for f in items if f['status'] not in UPCOMING_STATUSES and f['status'] not in FINISHED_STATUSES]'''

new_live = '''def get_live_fixtures(leagues=None) -> list:
    """Currently in-play matches globally, filtered by leagues."""
    # Using status=live fetches all live games
    # Pagination might be needed if > 100 games are live, but usually 100 is enough.
    data = _get('matches', {'status': 'live', 'limit': 100}, ttl=60)
    if not data or 'data' not in data:
        return []
    items = data['data']
    if leagues:
        items = [i for i in items if i['competition_id'] in leagues]
    return items'''
code = code.replace(old_live, new_live)

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Replaced functions")
