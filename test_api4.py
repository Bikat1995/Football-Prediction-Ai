import requests, json

KEY = 'fapi_ZM9fesS1w3dEHYjLsfcFHJ8CJPmNlTb8'
headers = {'Authorization': f'Bearer {KEY}'}
base = 'https://api.thestatsapi.com/api/football'

# Get standings with season ID
print("=== STANDINGS ===")
for ep in [
    '/competitions/comp_3039/standings',
    '/competitions/comp_3039/standings?season_id=sn_8406098',
    '/seasons/sn_8406098/standings',
]:
    r = requests.get(f'{base}{ep}', headers=headers)
    print(f"{ep}: {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2)[:500])
        break

# Full odds structure
print("\n=== FULL ODDS STRUCTURE ===")
r = requests.get(f'{base}/matches/mt_511976728/odds', headers=headers)
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2)[:1500])

# Team stats
print("\n=== TEAM STATS ===")
for ep in [
    '/teams/tm_9145/stats',
    '/teams/tm_9145/stats?season_id=sn_8406098',
    '/teams/tm_9145/stats?competition_id=comp_3039',
    '/teams/tm_9145',
]:
    r = requests.get(f'{base}{ep}', headers=headers)
    print(f"{ep}: {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2)[:500])
        break

# Match timeline/events
print("\n=== MATCH TIMELINE ===")
for ep in [
    '/matches/mt_511976728/events',
    '/matches/mt_511976728/timeline',
    '/matches/mt_511976728/incidents',
]:
    r = requests.get(f'{base}{ep}', headers=headers)
    print(f"{ep}: {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2)[:500])
        break

print(f"\nQuota: {r.headers.get('x-monthly-quota-remaining', '?')}/{r.headers.get('x-monthly-quota-limit', '?')}")
