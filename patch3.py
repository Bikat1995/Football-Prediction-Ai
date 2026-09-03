import os
import re

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Fix get_fixtures_for_date
old_fixtures_date = '''    for lg in leagues:
        # Cache for 12 hours since schedules rarely change
        data = _get('matches', {'competition_id': lg, 'date_from': target_date, 'date_to': target_date, 'limit': 100}, ttl=43200)
        if data and 'data' in data:
            all_items.extend(data['data'])'''
new_fixtures_date = '''    import time
    for lg in leagues:
        # Cache for 12 hours since schedules rarely change
        data = _get('matches', {'competition_id': lg, 'date_from': target_date, 'date_to': target_date, 'limit': 100}, ttl=43200)
        if data and 'data' in data:
            all_items.extend(data['data'])
        time.sleep(0.1) # Respect 12 req/sec rate limit'''
code = code.replace(old_fixtures_date, new_fixtures_date)

# Fix get_upcoming_fixtures
old_upcoming = '''    for lg in leagues:
        # Cache for 3 hours
        data = _get('matches', {'competition_id': lg, 'date_from': today, 'date_to': tomorrow, 'limit': 100}, ttl=10800)
        if data and 'data' in data:
            all_items.extend(data['data'])'''
new_upcoming = '''    import time
    for lg in leagues:
        # Cache for 3 hours
        data = _get('matches', {'competition_id': lg, 'date_from': today, 'date_to': tomorrow, 'limit': 100}, ttl=10800)
        if data and 'data' in data:
            all_items.extend(data['data'])
        time.sleep(0.1) # Respect 12 req/sec rate limit'''
code = code.replace(old_upcoming, new_upcoming)

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Added rate limit sleep")
