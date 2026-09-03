import re

with open('dashboard.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(
    """def fixture_label(f: dict) -> str:
    t = fmt_time(f['fixture']['date'])
    return f"{t}  {f['teams']['home']['name']} vs {f['teams']['away']['name']}""\",
    """def fixture_label(f: dict) -> str:
    t = fmt_time(f['utc_date'])
    return f"{t}  {f['home_team']['name']} vs {f['away_team']['name']}""\"
)

code = code.replace(
    """def build_options(fixtures: list) -> dict:
    \"\"\"Group fixtures by league, return dict keyed by league name.\"\"\"
    opts = {}
    for f in fixtures:
        lg = f['league']['name']
        if lg not in opts:
            opts[lg] = []
        opts[lg].append({
            'label':       fixture_label(f),
            'id':          f['fixture']['id'],
            'league_id':   f['league']['id'],
            'season':      f['league']['season'],
            'home_id':     f['teams']['home']['id'],
            'away_id':     f['teams']['away']['id'],
            'home_logo':   f['teams']['home']['logo'],
            'away_logo':   f['teams']['away']['logo'],
            'league_logo': f['league']['logo'],
            'home_name':   f['teams']['home']['name'],
            'away_name':   f['teams']['away']['name'],
            'date':        f['fixture']['date'],
            'status':      f['fixture']['status'],
            'goals':       f.get('goals', {}),
            'events':      f.get('events', []),
        })
    return opts""",
    """def build_options(fixtures: list) -> dict:
    \"\"\"Group fixtures by league, return dict keyed by league name.\"\"\"
    opts = {}
    for f in fixtures:
        lg = f.get('competition_name', predict_today.LEAGUES.get(f['competition_id'], {}).get('name', 'Unknown'))
        if lg not in opts:
            opts[lg] = []
        opts[lg].append({
            'label':       fixture_label(f),
            'id':          f['id'],
            'league_id':   f['competition_id'],
            'season':      f.get('season_id', ''),
            'home_id':     f['home_team']['id'],
            'away_id':     f['away_team']['id'],
            'home_logo':   '',
            'away_logo':   '',
            'league_logo': '',
            'home_name':   f['home_team']['name'],
            'away_name':   f['away_team']['name'],
            'date':        f['utc_date'],
            'status':      {'short': f['status'], 'elapsed': ''},
            'goals':       f.get('score', {}),
            'events':      [],
        })
    return opts"""
)

code = code.replace(
    "if f['fixture']['date'][:10] == TODAY",
    "if f['utc_date'][:10] == TODAY"
)
code = code.replace(
    "if f['fixture']['date'][:10] == TOMORROW",
    "if f['utc_date'][:10] == TOMORROW"
)

code = code.replace(
    "from live_data_fetcher import _get, KEY1",
    "from live_data_fetcher import _get"
)
code = code.replace(
    "if not KEY1:",
    "if not os.getenv('THESTATSAPI_KEY'):"
)
code = code.replace(
    "st.sidebar.markdown(\"<div style='color: #EF4444; font-size: 0.8rem;'>● API Error: Missing API_FOOTBALL_KEY</div>\", unsafe_allow_html=True)",
    "st.sidebar.markdown(\"<div style='color: #EF4444; font-size: 0.8rem;'>● API Error: Missing THESTATSAPI_KEY</div>\", unsafe_allow_html=True)"
)
code = code.replace(
    "api_status = _get('timezone', {}, KEY1, ttl=3600)",
    "api_status = _get('competitions', {'limit':1}, ttl=3600)"
)
code = code.replace(
    "if api_status and 'response' in api_status and len(api_status['response']) > 0:",
    "if api_status and 'data' in api_status:"
)

# And one more thing: Update image tags in dashboard to not render if there's no logo
code = code.replace('<img src="{selected_fixture[\'home_logo\']}">', '')
code = code.replace('<img src="{selected_fixture[\'away_logo\']}">', '')

with open('dashboard.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Dashboard patch completed")
