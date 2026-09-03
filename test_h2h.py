import os, requests, json
from dotenv import load_dotenv
load_dotenv()
KEY = os.getenv('THESTATSAPI_KEY')
r = requests.get('https://api.thestatsapi.com/api/football/matches',
    headers={'Authorization': f'Bearer {KEY}'},
    params={'team_id': 'tm_1002,tm_9145', 'status': 'finished', 'limit': 10})
print('Status:', r.status_code)
if r.status_code == 200:
    data = r.json().get('data', [])
    print(f'Matches: {len(data)}')
    for m in data[:3]:
        print(f"{m['home_team']['name']} vs {m['away_team']['name']}")
else:
    print(r.json())
