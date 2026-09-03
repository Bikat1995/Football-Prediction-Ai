import os

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_h2h = '''def get_head_to_head(home_id: str, away_id: str, last: int = 10) -> dict:
    """
    Fetch real head-to-head matches between two teams.
    Returns both the raw match list (for display) and summary stats (for Poisson blend).
    Strategy: fetch up to 50 recent finished matches for home_id, filter for opponent = away_id.
    """
    data = _get('matches', {'team_id': home_id, 'status': 'finished', 'limit': 50}, ttl=86400)
    if not data or 'data' not in data:
        return {'matches': [], 'home_avg': 0, 'away_avg': 0, 'games': 0}

    all_matches = data['data']
    # Filter only matches where away_id was the opponent
    h2h_matches = [
        m for m in all_matches
        if m['home_team']['id'] == away_id or m['away_team']['id'] == away_id
    ]
    h2h_matches = h2h_matches[:last]

    if not h2h_matches:
        return {'matches': [], 'home_avg': 0, 'away_avg': 0, 'games': 0}

    home_scored = 0
    away_scored = 0
    for m in h2h_matches:'''

new_h2h = '''def get_head_to_head(home_id: str, away_id: str, last: int = 5) -> dict:
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
    for m in h2h_matches:'''

if old_h2h in code:
    code = code.replace(old_h2h, new_h2h)
else:
    print("Could not find old_h2h to replace!")

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated get_head_to_head to paginate")
