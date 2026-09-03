import requests
KEY = 'fapi_ZM9fesS1w3dEHYjLsfcFHJ8CJPmNlTb8'
headers = {'Authorization': f'Bearer {KEY}'}
base = 'https://api.thestatsapi.com/api/football'
# try /matches/h2h or /h2h
for ep in ['/matches/h2h', '/h2h']:
    r = requests.get(f'{base}{ep}', headers=headers, params={'team1_id': 'tm_44984', 'team2_id': 'tm_15059'})
    print(ep, r.status_code)
