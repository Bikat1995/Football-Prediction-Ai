import requests, json

KEY = 'fapi_ZM9fesS1w3dEHYjLsfcFHJ8CJPmNlTb8'
headers = {'Authorization': f'Bearer {KEY}'}
base = 'https://api.thestatsapi.com/api/football'

# 1. Find all competitions including Europa/Conference
print("=== ALL COMPETITIONS ===")
comps = []
page = 1
while True:
    r = requests.get(f'{base}/competitions', headers=headers, params={'page': page})
    data = r.json().get('data', [])
    if not data:
        break
    comps.extend(data)
    page += 1

print(f"Total competitions: {len(comps)}")
for c in comps:
    name = c['name']
    country = c.get('country', 'None')
    cid = c['id']
    flags = []
    if c.get('has_team_stats'): flags.append('team_stats')
    if c.get('has_player_stats'): flags.append('player_stats')
    if c.get('odds_available'): flags.append('odds')
    if c.get('xg_available'): flags.append('xG')
    if c.get('live_odds_available'): flags.append('live_odds')
    if any(t in name for t in ['Premier League', 'LaLiga', 'Serie A', 'Bundesliga', 'Ligue 1', 
                                 'Champions', 'Europa', 'Conference', 'Eredivisie', 'Championship',
                                 'Liga Portugal', 'Super Lig', 'Scottish', 'MLS', 'Copa']):
        print(f"  {name} ({country}) = {cid}  [{', '.join(flags)}]")

# 2. Test match stats endpoint
print("\n=== MATCH STATS TEST ===")
r = requests.get(f'{base}/matches', headers=headers, params={'competition_id': 'comp_3039', 'status': 'finished', 'limit': 1})
if r.status_code == 200 and r.json().get('data'):
    match = r.json()['data'][0]
    match_id = match['id']
    print(f"Match: {match['home_team']['name']} vs {match['away_team']['name']} (ID: {match_id})")
    
    # Try stats
    r2 = requests.get(f'{base}/matches/{match_id}/stats', headers=headers)
    print(f"Stats endpoint: {r2.status_code}")
    if r2.status_code == 200:
        stats = r2.json()
        print(json.dumps(stats, indent=2)[:600])
    
    # Try odds
    r3 = requests.get(f'{base}/matches/{match_id}/odds', headers=headers)
    print(f"\nOdds endpoint: {r3.status_code}")
    if r3.status_code == 200:
        odds = r3.json()
        print(json.dumps(odds, indent=2)[:600])
    
    # Try lineups
    r4 = requests.get(f'{base}/matches/{match_id}/lineups', headers=headers)
    print(f"\nLineups endpoint: {r4.status_code}")
    
    # Try events/timeline
    r5 = requests.get(f'{base}/matches/{match_id}/events', headers=headers)
    print(f"Events endpoint: {r5.status_code}")

# 3. Test team stats
print("\n=== TEAM STATS TEST ===")
r = requests.get(f'{base}/competitions/comp_3039/standings', headers=headers)
print(f"Standings endpoint: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:500])

# 4. Check remaining quota
print(f"\nQuota remaining: {r.headers.get('x-monthly-quota-remaining', 'unknown')}/{r.headers.get('x-monthly-quota-limit', 'unknown')}")
