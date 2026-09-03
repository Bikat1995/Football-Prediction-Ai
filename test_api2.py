import requests, json

KEY = 'fapi_ZM9fesS1w3dEHYjLsfcFHJ8CJPmNlTb8'
headers = {'Authorization': f'Bearer {KEY}'}
base = 'https://api.thestatsapi.com/api/football'

# Test odds on a finished PL match
r = requests.get(f'{base}/matches', headers=headers, params={'competition_id': 'comp_3039', 'status': 'finished', 'limit': 3})
matches = r.json().get('data', [])
for m in matches:
    mid = m['id']
    print(f"Match: {m['home_team']['name']} vs {m['away_team']['name']} ({mid})")
    
    # odds
    r2 = requests.get(f'{base}/matches/{mid}/odds', headers=headers)
    print(f"  Odds: {r2.status_code}")
    if r2.status_code == 200:
        print(json.dumps(r2.json(), indent=2)[:400])
    
    # standings
    break

# Test team season stats
print("\n=== TEAM SEASON STATS ===")
r = requests.get(f'{base}/competitions/comp_3039/standings', headers=headers)
print(f"Standings: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:800])

# Test team stats
print("\n=== TEAM STATS ENDPOINT ===")
# First get a team from PL
r = requests.get(f'{base}/competitions/comp_3039/teams', headers=headers)
print(f"Teams: {r.status_code}")
if r.status_code == 200:
    teams = r.json().get('data', [])
    print(f"Found {len(teams)} teams")
    if teams:
        tid = teams[0]['id']
        print(f"Testing stats for {teams[0]['name']} ({tid})")
        r2 = requests.get(f'{base}/teams/{tid}/stats', headers=headers)
        print(f"Team stats: {r2.status_code}")
        if r2.status_code == 200:
            print(json.dumps(r2.json(), indent=2)[:600])

print(f"\nQuota remaining: {r.headers.get('x-monthly-quota-remaining', '?')}/{r.headers.get('x-monthly-quota-limit', '?')}")
