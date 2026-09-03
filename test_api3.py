import requests, json

KEY = 'fapi_ZM9fesS1w3dEHYjLsfcFHJ8CJPmNlTb8'
headers = {'Authorization': f'Bearer {KEY}'}
base = 'https://api.thestatsapi.com/api/football'

# Find the right endpoints for standings and teams
endpoints_to_try = [
    '/standings',
    '/standings?competition_id=comp_3039',
    '/competitions/comp_3039/seasons',
    '/seasons',
    '/teams?competition_id=comp_3039',
]

for ep in endpoints_to_try:
    r = requests.get(f'{base}{ep}', headers=headers)
    print(f"{ep}: {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2)[:300])

# Test full match detail
print("\n=== FULL MATCH DETAIL ===")
r = requests.get(f'{base}/matches/mt_511976728', headers=headers)
print(f"Match detail: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:800])

# Test lineups
print("\n=== LINEUPS ===")
r = requests.get(f'{base}/matches/mt_511976728/lineups', headers=headers)
print(f"Lineups: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:500])

# Test events
print("\n=== EVENTS ===")
r = requests.get(f'{base}/matches/mt_511976728/events', headers=headers)
print(f"Events: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:500])

# Test shotmap
print("\n=== SHOTMAP ===")
r = requests.get(f'{base}/matches/mt_511976728/shotmap', headers=headers)
print(f"Shotmap: {r.status_code}")
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:500])

print(f"\nQuota: {r.headers.get('x-monthly-quota-remaining', '?')}/{r.headers.get('x-monthly-quota-limit', '?')}")
