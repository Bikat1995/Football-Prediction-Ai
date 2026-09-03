import os, requests, json
from dotenv import load_dotenv
load_dotenv()
KEY = os.getenv('THESTATSAPI_KEY')
r = requests.get('https://api.thestatsapi.com/api/football/matches',
    headers={'Authorization': f'Bearer {KEY}'},
    params={'team_id': 'tm_1002', 'status': 'finished', 'limit': 100, 'page': 1})
if r.status_code == 200:
    data = r.json()
    print("Meta:", data.get('meta'))
