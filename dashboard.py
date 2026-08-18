import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
load_dotenv()

import predict_today
from live_data_fetcher import (
    get_live_fixtures, get_upcoming_fixtures,
    get_fixture_predictions, get_team_season_stats,
    get_team_form, get_head_to_head, get_api_prediction_probs,
    get_league_top_scorers, get_league_top_assists,
    compute_poisson_markets,
    LIVE_STATUSES, UPCOMING_STATUSES, CURRENT_SEASON
)
import base64
import os

LOGO_B64 = ""
if os.path.exists("Better-logo.png"):
    with open("Better-logo.png", "rb") as f:
        LOGO_B64 = base64.b64encode(f.read()).decode()

st.set_page_config(page_title="Better", layout="wide", initial_sidebar_state="expanded")

# ── CSS loader ────────────────────────────────────────────────────────────────
def _load_css():
    with open("style.css") as f:
        css = f.read()
    st.html(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>{css}</style>
    """)

_load_css()

LEAGUES = list(predict_today.LEAGUES.keys())
TODAY    = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).strftime('%H:%M')
    except:
        return '??:??'

def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).strftime('%A %d %b')
    except:
        return iso[:10]

def fixture_label(f: dict) -> str:
    t = fmt_time(f['fixture']['date'])
    return f"{t}  {f['teams']['home']['name']} vs {f['teams']['away']['name']}"

def build_options(fixtures: list) -> dict:
    """Group fixtures by league, return dict keyed by league name."""
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
    return opts

# ── Cached data fetchers ───────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def cached_live():
    return get_live_fixtures(leagues=LEAGUES)

@st.cache_data(ttl=120)
def cached_upcoming():
    return get_upcoming_fixtures(leagues=LEAGUES)

@st.cache_data(ttl=3600)
def cached_predictions(fixture_id):
    return get_fixture_predictions(fixture_id)

@st.cache_data(ttl=86400)
def cached_team_stats(team_id, league_id, season):
    return get_team_season_stats(team_id, league_id, season)

@st.cache_data(ttl=3600)
def cached_team_form(team_id):
    return get_team_form(team_id, last=8)

@st.cache_data(ttl=86400)
def cached_h2h(home_id, away_id):
    return get_head_to_head(home_id, away_id, last=10)

@st.cache_data(ttl=3600)
def cached_api_probs(fixture_id):
    return get_api_prediction_probs(fixture_id)

@st.cache_data(ttl=86400)
def cached_top_players(league_id, season):
    return get_league_top_scorers(league_id, season), get_league_top_assists(league_id, season)

# ── SIDEBAR (auto-refreshes every 60s) ───────────────────────────────────────
st.sidebar.image("Better-logo.png", width=96)
st.sidebar.html("<div style='font-family:DM Mono,monospace;font-size:9.5px;letter-spacing:0.12em;text-transform:uppercase;color:#4a5470;margin:6px 0 12px 0;'>AI Prediction Engine</div>")
st.sidebar.divider()

if st.sidebar.button("Refresh All Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
    
# Quick API Health Check — test Sofascore connectivity
try:
    import esd as _esd
    _test_client = _esd.SofascoreClient()
    _test_result = _test_client.get_events(live=True)
    st.sidebar.markdown("<div style='color: #10B981; font-size: 0.8rem;'>● Data Connected (Sofascore)</div>", unsafe_allow_html=True)
except Exception as _e:
    st.sidebar.markdown(f"<div style='color: #EF4444; font-size: 0.8rem;'>● Data Error: {str(_e)[:60]}</div>", unsafe_allow_html=True)

st.sidebar.markdown(f"<div class='last-update'>Auto-refreshes · Last check {datetime.utcnow().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

live_raw     = cached_live()
upcoming_raw = cached_upcoming()

live_opts     = build_options(live_raw)
upcoming_opts = build_options(upcoming_raw)

# Split upcoming into today vs tomorrow
today_opts    = build_options([f for f in upcoming_raw
                               if f['fixture']['date'][:10] == TODAY])
tomorrow_opts = build_options([f for f in upcoming_raw
                               if f['fixture']['date'][:10] == TOMORROW])

selected_fixture = None

def _sidebar_section(title: str, color: str, opts: dict):
    global selected_fixture
    if not opts:
        return
    st.sidebar.html(
        f"<div style='font-size:11px;font-weight:700;letter-spacing:0.1em;"
        f"text-transform:uppercase;color:{color};margin:10px 0 6px 0;'>"
        f"{title}</div>")
    for league, matches in opts.items():
        lg_logo = matches[0]['league_logo']
        st.sidebar.html(
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
            f"<img src='{lg_logo}' width='18' height='18' style='object-fit:contain;'>"
            f"<span style='font-size:12px;font-weight:700;color:#94a3b8;'>{league}</span>"
            f"</div>")
        for m in matches:
            label = m['label']
            # For live games, prepend score
            if m['status']['short'] in LIVE_STATUSES:
                hg = m['goals'].get('home', '?')
                ag = m['goals'].get('away', '?')
                elapsed = m['status'].get('elapsed', '')
                label = f"{hg}–{ag} ({elapsed}')  {m['home_name']} vs {m['away_name']}"
            if st.sidebar.button(label, key=f"btn_{m['id']}", width='stretch'):
                selected_fixture = m
        st.sidebar.html("<div style='margin-bottom:8px;'></div>")

_sidebar_section("Live Now",  "#d94040", live_opts)
_sidebar_section("Today",     "#8a90a6", today_opts)
_sidebar_section("Tomorrow",  "#4a5470", tomorrow_opts)

# Removed logo_ph logic
st.sidebar.divider()
st.sidebar.caption(f"Auto-refreshes · Last check {datetime.now().strftime('%H:%M:%S')}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if not selected_fixture:
    total = len(live_raw) + len(upcoming_raw)
    st.html(f"""
    <div style='max-width:480px;margin:100px auto;text-align:center;'>
      <img src='data:image/png;base64,{LOGO_B64}' width='60' style='margin-bottom:20px;border-radius:4px;'>
      <div style='font-family:DM Mono,monospace;font-size:10px;letter-spacing:.12em;
                  text-transform:uppercase;color:#4a5470;margin-bottom:18px;'>Better AI Prediction Engine</div>
      <div style='font-size:28px;font-weight:700;color:#dde2ef;margin-bottom:10px;
                  line-height:1.25;'>Select a match<br>to load the analysis.</div>
      <div style='font-size:13px;color:#8491b0;line-height:1.8;'>
        {len(live_raw)} live &nbsp;&middot;&nbsp; {len(upcoming_raw)} upcoming &mdash; choose from the sidebar.
      </div>
    </div>""")
    st.stop()

# ── MAIN HEADER (Visible when match selected) ─────────────────────────────────
st.html(f"""
<div style='display:flex;align-items:center;gap:12px;margin-bottom:24px;'>
  <img src='data:image/png;base64,{LOGO_B64}' width='32' style='border-radius:4px;'>
  <div style='font-family:DM Mono,monospace;font-size:10px;letter-spacing:.12em;
              text-transform:uppercase;color:#4a5470;'>Better AI Prediction Engine</div>
</div>
""")

# ── MATCH HEADER ──────────────────────────────────────────────────────────────
is_live = selected_fixture['status']['short'] in LIVE_STATUSES
match_date = fmt_date(selected_fixture['date'])
match_time = fmt_time(selected_fixture['date'])

if is_live:
    elapsed = selected_fixture['status'].get('elapsed', '')
    hg = selected_fixture['goals'].get('home', 0)
    ag = selected_fixture['goals'].get('away', 0)
    score_block = f"""
    <div style='display:flex;flex-direction:column;align-items:center;gap:8px;'>
      <div class='live-pill'>LIVE {elapsed}'</div>
      <div style='font-family:DM Mono,monospace;font-size:40px;font-weight:500;color:#dde2ef;letter-spacing:-.5px;'>{hg} &ndash; {ag}</div>
    </div>"""
else:
    score_block = f"""
    <div style='display:flex;flex-direction:column;align-items:center;gap:6px;'>
      <div class='match-vs'>vs</div>
      <div style='font-family:DM Mono,monospace;font-size:11px;color:#4a5470;letter-spacing:.06em;'>{match_date} &middot; {match_time}</div>
    </div>"""

st.html(f"""
<div class="match-header">
  <div class="match-team">
    <img src="{selected_fixture['home_logo']}">
    <div class="name">{selected_fixture['home_name']}</div>
  </div>
  {score_block}
  <div class="match-team">
    <img src="{selected_fixture['away_logo']}">
    <div class="name">{selected_fixture['away_name']}</div>
  </div>
</div>
""")

# ── FETCH DATA ────────────────────────────────────────────────────────────────
with st.spinner("Crunching numbers…"):
    pred_data   = cached_predictions(selected_fixture['id'])
    # Real form: last 8 games for each team across all comps
    home_form   = cached_team_form(selected_fixture['home_id'])
    away_form   = cached_team_form(selected_fixture['away_id'])
    # Head-to-head history
    h2h         = cached_h2h(selected_fixture['home_id'], selected_fixture['away_id'])
    # API-Football's own probability estimates
    api_probs   = cached_api_probs(selected_fixture['id'])
    # Season stats still fetched as a tertiary fallback
    home_stats  = cached_team_stats(
        selected_fixture['home_id'],
        selected_fixture['league_id'],
        selected_fixture['season']
    )
    away_stats  = cached_team_stats(
        selected_fixture['away_id'],
        selected_fixture['league_id'],
        selected_fixture['season']
    )
    top_scorers, top_assists = cached_top_players(
        selected_fixture['league_id'], CURRENT_SEASON
    )

# ── POISSON MARKETS (real AI) ─────────────────────────────────────────────────
import live_data_fetcher
import difflib

LEAGUE_AVG_SCORED    = 1.35
LEAGUE_AVG_CONCEDED  = 1.35

def _best_avg(form: dict, stats: dict, team_name: str, direction: str) -> float:
    """
    Priority order:
    1. Real form from last 8 games (always recent, cross-season)
    2. Current season stats from API (only if games > 3)
    3. ML historical team data (fuzzy matched)
    4. League average
    """
    key = 'avg_scored' if direction == 'for' else 'avg_conceded'
    # 1. Real recent form
    if form and form.get('games', 0) >= 3:
        return form[key]
    # 2. Current season API stats
    try:
        val = stats['goals'][direction]['average']['total']
        if val and float(val) > 0:
            games_played = stats['fixtures']['played']['total']
            if games_played >= 3:
                return float(val)
    except Exception:
        pass
    # 3. ML historical
    if live_data_fetcher.ML_MODEL_DATA:
        ts = live_data_fetcher.ML_MODEL_DATA['team_stats']
        matches = difflib.get_close_matches(team_name, ts.keys(), n=1, cutoff=0.6)
        if matches:
            m = matches[0]
            g = ts[m]['games']
            if g > 0:
                return ts[m]['scored'] / g if direction == 'for' else ts[m]['conceded'] / g
    # 4. League average
    return LEAGUE_AVG_SCORED

home_scored   = _best_avg(home_form, home_stats, selected_fixture['home_name'], 'for')
home_conceded = _best_avg(home_form, home_stats, selected_fixture['home_name'], 'against')
away_scored   = _best_avg(away_form, away_stats, selected_fixture['away_name'], 'for')
away_conceded = _best_avg(away_form, away_stats, selected_fixture['away_name'], 'against')

# Blend with H2H if available (25% weight)
if h2h and h2h.get('games', 0) >= 3:
    home_scored   = home_scored   * 0.75 + h2h['home_avg'] * 0.25
    away_scored   = away_scored   * 0.75 + h2h['away_avg'] * 0.25
    home_conceded = home_conceded * 0.75 + h2h['away_avg'] * 0.25
    away_conceded = away_conceded * 0.75 + h2h['home_avg'] * 0.25

markets = compute_poisson_markets(
    selected_fixture['home_name'], selected_fixture['away_name'],
    home_scored, home_conceded, away_scored, away_conceded
)

# If API-Football gives us their own probabilities, blend them in (40% weight)
if api_probs:
    blend = 0.40
    hw = markets['home_win'] * (1 - blend) + api_probs['home'] * blend
    dw = markets['draw']     * (1 - blend) + api_probs['draw'] * blend
    aw = markets['away_win'] * (1 - blend) + api_probs['away'] * blend
    total = hw + dw + aw
    markets['home_win'] = round(hw / total * 100, 1)
    markets['draw']     = round(dw / total * 100, 1)
    markets['away_win'] = round(aw / total * 100, 1)

# API advice string
api_advice = ''
if pred_data:
    api_advice = pred_data.get('predictions', {}).get('advice', '')

# ── AI PREDICTION BANNER ──────────────────────────────────────────────────────
# Always pick the best bet — never show "No prediction available"
hw  = markets['home_win']
dw  = markets['draw']
aw  = markets['away_win']
bt  = markets['btts']
o25 = markets['over_2_5']
o15 = markets['over_1_5']
dc_hd = markets['dc_home_draw']
dc_ad = markets['dc_away_draw']

# Ranked picks: highest probability market wins
candidates = [
    (hw,   f"Home Win — {selected_fixture['home_name']} ({hw:.1f}%)"),
    (aw,   f"Away Win — {selected_fixture['away_name']} ({aw:.1f}%)"),
    (dc_hd,f"{selected_fixture['home_name']} or Draw ({dc_hd:.1f}%)"),
    (dc_ad,f"{selected_fixture['away_name']} or Draw ({dc_ad:.1f}%)"),
    (bt,   f"Both Teams to Score ({bt:.1f}%)"),
    (o25,  f"Over 2.5 Goals ({o25:.1f}%)"),
    (o15,  f"Over 1.5 Goals ({o15:.1f}%)"),
]
best_prob, ai_rec = max(candidates, key=lambda x: x[0])

low_warn = markets.get('low_data_warning')
ml_blend = markets.get('ml_blend', 0)

if low_warn:
    banner_label = "Statistical Baseline"
    banner_style = "border-color: #6b4000;"
else:
    banner_label = "AI Recommendation"
    banner_style = ""

st.html(f"""
<div class="pred-banner" style="{banner_style}">
  <div class="label">{banner_label}</div>
  <div class="value">{ai_rec}</div>
  {f'<div style="font-family:DM Mono,monospace;font-size:11px;color:#8491b0;margin-top:8px;">{low_warn}</div>' if low_warn else ''}
</div>
""")

# ── STAT CARDS ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
cards_data = [
    (c1, "Home Win",  f"{markets['home_win']:.1f}%",  "blue"),
    (c2, "Draw",      f"{markets['draw']:.1f}%",       "amber"),
    (c3, "Away Win",  f"{markets['away_win']:.1f}%",   "red"),
    (c4, "BTTS",      f"{markets['btts']:.1f}%",       "green"),
]
for col, label, val, cls in cards_data:
    col.html(f"""
    <div class="stat-box">
      <div class="stat-label">{label}</div>
      <div class="stat-value {cls}">{val}</div>
    </div>""")

st.html("<div style='margin:20px 0;border-bottom:1px solid #1e2535;'></div>")


# ── LIVE EVENTS PANEL ─────────────────────────────────────────────────────────
if is_live and selected_fixture.get('events'):
    st.html('<div class="section-title">Live Events</div>')
    for ev in selected_fixture['events'][:10]:
        t    = ev.get('time', {}).get('elapsed', '?')
        evtype = ev.get('type', '')
        detail = ev.get('detail', '')
        player = ev.get('player', {}).get('name', '')
        team   = ev.get('team', {}).get('name', '')
        icon = {'Goal': '⚽', 'Card': '🟨' if 'Yellow' in detail else '🟥', 'subst': '🔄'}.get(evtype, '·')
        st.html(
            f"<div style='font-size:13px;color:#94a3b8;padding:4px 0;'>"
            f"<span style='color:#e2e8f0;font-weight:700;width:32px;display:inline-block;'>{t}'</span>"
            f" {icon} <b>{player}</b> · {team} <span style='color:#475569;'>({detail})</span>"
            f"</div>")
    st.html("<div style='margin:16px 0;border-bottom:1px solid #1e2535;'></div>")

# ── TABS ──────────────────────────────────────────────────────────────────────
t_markets, t_edge, t_goals, t_cards, t_form, t_players, t_h2h = st.tabs([
    "Betting Markets",
    "Edge Comparison",
    "Goals",
    "Cards & Discipline",
    "Formations",
    "Top Players",
    "Head-to-Head",
])

# ── TAB: BETTING MARKETS ──────────────────────────────────────────────────────
with t_markets:
    st.html('<div class="section-title">All Computed Markets · AI Hybrid Model</div>')

    # ── Row 1: 1X2 + BTTS ────────────────────────────────────────────────────
    r1 = st.columns(4)
    main_m = [
        ("Home Win",         f"{markets['home_win']:.1f}%",  "blue"),
        ("Draw",             f"{markets['draw']:.1f}%",       "amber"),
        ("Away Win",         f"{markets['away_win']:.1f}%",   "red"),
        ("Both Teams Score", f"{markets['btts']:.1f}%",       "green"),
    ]
    for col, (lbl, val, cls) in zip(r1, main_m):
        col.html(f'<div class="ou-card" style="padding:12px 16px;">'
                 f'<div class="ou-row" style="border:none;padding:0;">'
                 f'<div class="ou-team">{lbl}</div>'
                 f'<div class="ou-vals {cls}">{val}</div>'
                 f'</div></div>')

    st.html("<div style='margin-top:10px;'></div>")

    # ── Row 2: Over / Under ───────────────────────────────────────────────────
    r2 = st.columns(3)
    ou_m = [
        ("Over 1.5 Goals", f"{markets['over_1_5']:.1f}%", "blue"),
        ("Over 2.5 Goals", f"{markets['over_2_5']:.1f}%", "blue"),
        ("Over 3.5 Goals", f"{markets['over_3_5']:.1f}%", "blue"),
    ]
    for col, (lbl, val, cls) in zip(r2, ou_m):
        col.html(f'<div class="ou-card" style="padding:12px 16px;">'
                 f'<div class="ou-row" style="border:none;padding:0;">'
                 f'<div class="ou-team">{lbl}</div>'
                 f'<div class="ou-vals {cls}">{val}</div>'
                 f'</div></div>')

    st.html("<div style='margin-top:10px;'></div>")

    # ── Row 3: Double Chance + xG ─────────────────────────────────────────────
    r3 = st.columns(4)
    dc_m = [
        (f"{selected_fixture['home_name'][:10]} or Draw",  f"{markets['dc_home_draw']:.1f}%", "green"),
        (f"{selected_fixture['away_name'][:10]} or Draw",  f"{markets['dc_away_draw']:.1f}%", "green"),
        (f"xG {selected_fixture['home_name'][:10]}",        f"{markets['xg_home']:.2f}",       "amber"),
        (f"xG {selected_fixture['away_name'][:10]}",        f"{markets['xg_away']:.2f}",       "amber"),
    ]
    for col, (lbl, val, cls) in zip(r3, dc_m):
        col.html(f'<div class="ou-card" style="padding:12px 16px;">'
                 f'<div class="ou-row" style="border:none;padding:0;">'
                 f'<div class="ou-team" style="font-size:11px;">{lbl}</div>'
                 f'<div class="ou-vals {cls}">{val}</div>'
                 f'</div></div>')

    # ── Correct Scores ────────────────────────────────────────────────────────
    st.html('<div class="section-title" style="margin-top:24px;">Most Likely Correct Scores</div>')
    score_cols = st.columns(5)
    for col, (score, prob) in zip(score_cols, markets['top_scores']):
        col.html(
            f'<div class="ou-card" style="padding:12px 16px;">'
            f'<div class="ou-row" style="border:none;padding:0;">'
            f'<div class="ou-vals blue" style="font-size:15px;">{score}</div>'
            f'<div class="ou-team">{prob:.1f}%</div>'
            f'</div></div>')


# ── TAB: EDGE COMPARISON ──────────────────────────────────────────────────────
with t_edge:
    comparison = pred_data.get('comparison', {}) if pred_data else {}
    if comparison:
        ml_conf = markets.get('ml_blend', 0)
        # Only show a notice when data is INSUFFICIENT (no ML blend)
        if ml_conf == 0:
            st.html(f"""
            <div style='background:rgba(255,179,0,0.08); border:1px solid rgba(255,179,0,0.35);
                        border-radius:12px; padding:14px 18px; margin-bottom:18px;'>
                <div style='color:#FFB300; font-weight:800; font-size:12px;
                            letter-spacing:.1em; text-transform:uppercase; margin-bottom:4px;'>Statistical Baseline</div>
                <div style='color:#7B8DB0; font-size:12px; line-height:1.6;'>ML historical data insufficient for these teams.
                Falling back to 100% current season Poisson distribution.</div>
            </div>
            """)
            
        st.html('<div class="section-title">Mathematical Advantage Comparison</div>')
        metrics = [
            ('Recent Form',         comparison.get('form', {})),
            ('Attack Rating',       comparison.get('att', {})),
            ('Defense Rating',      comparison.get('def', {})),
            ('Poisson Distribution',comparison.get('poisson_distribution', {})),
            ('H2H Historical Edge', comparison.get('h2h', {})),
        ]
        comp_df = pd.DataFrame([{
            'Metric':    m,
            'Home_val':  float(d.get('home','0%').replace('%','') or 0),
            'Away_val':  float(d.get('away','0%').replace('%','') or 0),
        } for m, d in metrics])

        fig = go.Figure()
        fig.add_trace(go.Bar(y=comp_df['Metric'], x=comp_df['Home_val'],
                             name=selected_fixture['home_name'], orientation='h',
                             marker=dict(color='#0ea5e9'), width=0.35))
        fig.add_trace(go.Bar(y=comp_df['Metric'], x=comp_df['Away_val'],
                             name=selected_fixture['away_name'], orientation='h',
                             marker=dict(color='#f43f5e'), width=0.35))
        fig.update_layout(barmode='group', template='plotly_dark',
                          plot_bgcolor='#1a2035', paper_bgcolor='#1a2035',
                          height=320, margin=dict(l=0,r=0,t=10,b=0),
                          legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
                          font=dict(family='Inter',size=12,color='#94a3b8'),
                          xaxis=dict(gridcolor='#252d42'), yaxis=dict(gridcolor='#252d42'))
        st.plotly_chart(fig, width='stretch')

    # Poisson score probability heatmap
    st.html('<div class="section-title">Score Probability Heatmap</div>')
    import math
    def _pmf(lam, k):
        return (lam**k)*math.exp(-lam)/math.factorial(k) if lam > 0 else (1.0 if k==0 else 0.0)
    lam_h = markets['xg_home']; lam_a = markets['xg_away']
    n = 6
    z = [[round(_pmf(lam_h,h)*_pmf(lam_a,a)*100,1) for a in range(n)] for h in range(n)]
    fig_h = go.Figure(go.Heatmap(
        z=z, x=[f"Away {i}" for i in range(n)], y=[f"Home {i}" for i in range(n)],
        colorscale='Blues', showscale=True,
        text=[[f"{v}%" for v in row] for row in z], texttemplate="%{text}",
    ))
    fig_h.update_layout(template='plotly_dark', plot_bgcolor='#1a2035', paper_bgcolor='#1a2035',
                        height=340, margin=dict(l=0,r=0,t=10,b=0),
                        font=dict(family='Inter',size=12,color='#94a3b8'))
    st.plotly_chart(fig_h, width='stretch')

# ── TAB: GOALS ────────────────────────────────────────────────────────────────
with t_goals:
    teams_data = pred_data.get('teams', {}) if pred_data else {}

    def extract_ou(team_key, ou_val):
        try:
            return teams_data[team_key]['league']['goals']['for']['under_over'][ou_val]
        except:
            return {'over':0,'under':0}

    ou_15_h = extract_ou('home','1.5'); ou_15_a = extract_ou('away','1.5')
    ou_25_h = extract_ou('home','2.5'); ou_25_a = extract_ou('away','2.5')

    st.html('<div class="section-title">Over / Under — Historical Season Record</div>')
    oc1, oc2 = st.columns(2)
    with oc1:
        st.html(f"""<div class="ou-card">
          <div class="ou-title">Over / Under 1.5 Goals</div>
          <div class="ou-row"><span class="ou-team">{selected_fixture['home_name']}</span>
            <span class="ou-vals"><span class="ou-over">O {ou_15_h['over']}</span> &nbsp; <span class="ou-under">U {ou_15_h['under']}</span></span></div>
          <div class="ou-row"><span class="ou-team">{selected_fixture['away_name']}</span>
            <span class="ou-vals"><span class="ou-over">O {ou_15_a['over']}</span> &nbsp; <span class="ou-under">U {ou_15_a['under']}</span></span></div>
        </div>""")
    with oc2:
        st.html(f"""<div class="ou-card">
          <div class="ou-title">Over / Under 2.5 Goals</div>
          <div class="ou-row"><span class="ou-team">{selected_fixture['home_name']}</span>
            <span class="ou-vals"><span class="ou-over">O {ou_25_h['over']}</span> &nbsp; <span class="ou-under">U {ou_25_h['under']}</span></span></div>
          <div class="ou-row"><span class="ou-team">{selected_fixture['away_name']}</span>
            <span class="ou-vals"><span class="ou-over">O {ou_25_a['over']}</span> &nbsp; <span class="ou-under">U {ou_25_a['under']}</span></span></div>
        </div>""")

    st.html('<div class="section-title">Goal Timing — By 15-Minute Interval</div>')
    def get_intervals(team_key):
        try:
            mins = teams_data[team_key]['league']['goals']['for']['minute']
            pairs = [(k,v['total']) for k,v in mins.items() if k!='106-120' and v and v['total']]
            if pairs:
                return zip(*pairs)
        except:
            pass
        return [], []

    try:
        hl,hv = get_intervals('home'); al,av = get_intervals('away')
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=list(hl), y=list(hv), name=selected_fixture['home_name'], marker_color='#0ea5e9', opacity=0.85))
        fig2.add_trace(go.Bar(x=list(al), y=list(av), name=selected_fixture['away_name'], marker_color='#f43f5e', opacity=0.85))
        fig2.update_layout(barmode='group', template='plotly_dark', plot_bgcolor='#1a2035', paper_bgcolor='#1a2035',
                           height=280, margin=dict(l=0,r=0,t=10,b=0),
                           legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
                           font=dict(family='Inter',size=12,color='#94a3b8'),
                           xaxis=dict(gridcolor='#252d42'), yaxis=dict(gridcolor='#252d42'))
        st.plotly_chart(fig2, width='stretch')
    except:
        st.info("Goal interval data unavailable for this fixture.")

# ── TAB: CARDS ────────────────────────────────────────────────────────────────
with t_cards:
    teams_data = pred_data.get('teams', {}) if pred_data else {}
    st.html('<div class="section-title">Yellow Card Distribution by Interval</div>')

    def get_card_intervals(team_key):
        try:
            mins = teams_data[team_key]['league']['cards']['yellow']
            pairs = [(k,v['total']) for k,v in mins.items() if k!='106-120' and v and v['total']]
            if pairs:
                return zip(*pairs)
        except:
            pass
        return [], []

    try:
        hkl,hkv = get_card_intervals('home'); akl,akv = get_card_intervals('away')
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(x=list(hkl), y=list(hkv), name=selected_fixture['home_name'], marker_color='#0ea5e9'))
        fig3.add_trace(go.Bar(x=list(akl), y=list(akv), name=selected_fixture['away_name'], marker_color='#f43f5e'))
        fig3.update_layout(barmode='group', template='plotly_dark', plot_bgcolor='#1a2035', paper_bgcolor='#1a2035',
                           height=280, margin=dict(l=0,r=0,t=10,b=0),
                           legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
                           font=dict(family='Inter',size=12,color='#94a3b8'),
                           xaxis=dict(gridcolor='#252d42'), yaxis=dict(gridcolor='#252d42'))
        st.plotly_chart(fig3, width='stretch')
    except:
        st.info("Card interval data unavailable.")

    st.html('<div class="section-title">Penalty Statistics</div>')
    pc1, pc2 = st.columns(2)
    for key, col, name in [('home',pc1,selected_fixture['home_name']),('away',pc2,selected_fixture['away_name'])]:
        with col:
            try:
                pen = teams_data[key]['league']['penalty']
                st.html(f"""<div class="pen-card">
                  <div class="pen-title">{name}</div>
                  <div class="pen-stat"><span class="pen-label">Scored</span><span class="pen-val">{pen['scored']['total']} ({pen['scored']['percentage']})</span></div>
                  <div class="pen-stat"><span class="pen-label">Missed</span><span class="pen-val">{pen['missed']['total']} ({pen['missed']['percentage']})</span></div>
                </div>""")
            except:
                st.html(f'<div class="pen-card"><div class="pen-title">{name}</div><div class="pen-label">Data unavailable</div></div>')

# ── TAB: FORMATIONS ───────────────────────────────────────────────────────────
with t_form:
    teams_data = pred_data.get('teams', {}) if pred_data else {}
    st.html('<div class="section-title">Preferred Formations This Season</div>')
    fc1, fc2 = st.columns(2)
    for key, col, name in [('home',fc1,selected_fixture['home_name']),('away',fc2,selected_fixture['away_name'])]:
        with col:
            st.html(f"<div style='font-size:13px;font-weight:700;color:#94a3b8;margin-bottom:10px;'>{name}</div>")
            try:
                lineups = teams_data[key]['league']['lineups']
                if lineups:
                    df_l = pd.DataFrame(lineups).sort_values('played', ascending=False)
                    st.dataframe(df_l, width='stretch', hide_index=True)
                else:
                    st.html('<span style="color:#475569;font-size:13px;">No data.</span>')
            except:
                st.html('<span style="color:#475569;font-size:13px;">Data unavailable.</span>')

# ── TAB: TOP PLAYERS ──────────────────────────────────────────────────────────
with t_players:
    st.html('<div class="section-title">League Top Players</div>')
    with st.spinner("Loading…"):
        scorers, assists = cached_top_players(selected_fixture['league_id'], selected_fixture['season'])

    rank_cls = ['gold','silver','bronze','','']
    pc1, pc2 = st.columns(2)
    with pc1:
        st.html("<div style='font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#64748b;margin-bottom:12px;'>Top Scorers</div>")
        for i, p in enumerate(scorers[:5]):
            pl = p['player']; stat = p['statistics'][0]['goals']['total']; club = p['statistics'][0]['team']['name']
            st.html(f"""<div class="player-row">
              <div class="player-rank {rank_cls[i]}">{i+1}</div>
              <img src="{pl['photo']}">
              <div class="player-info"><div class="player-name">{pl['name']}</div><div class="player-team">{club}</div></div>
              <div class="player-stat">{stat}</div>
            </div>""")
    with pc2:
        st.html("<div style='font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#64748b;margin-bottom:12px;'>Top Assists</div>")
        for i, p in enumerate(assists[:5]):
            pl = p['player']; stat = p['statistics'][0]['goals']['assists']; club = p['statistics'][0]['team']['name']
            st.html(f"""<div class="player-row">
              <div class="player-rank {rank_cls[i]}">{i+1}</div>
              <img src="{pl['photo']}">
              <div class="player-info"><div class="player-name">{pl['name']}</div><div class="player-team">{club}</div></div>
              <div class="player-stat">{stat}</div>
            </div>""")

# ── TAB: H2H ─────────────────────────────────────────────────────────────────
with t_h2h:
    h2h = pred_data.get('h2h', []) if pred_data else []
    st.html('<div class="section-title">Head-to-Head History</div>')
    if not h2h:
        st.info("No recent H2H records found.")
    else:
        for match in h2h[:8]:
            try:
                dt  = datetime.fromisoformat(match['fixture']['date'].replace('Z','+00:00')).strftime('%d %b %Y')
                ht  = match['teams']['home']['name']
                at  = match['teams']['away']['name']
                hg  = match['goals']['home']
                ag  = match['goals']['away']
                lg  = match['league']['name']
                st.html(f"""<div class="h2h-row">
                  <div><div class="h2h-date">{dt}</div><div class="h2h-league">{lg}</div></div>
                  <div style="text-align:center;">
                    <div style="font-size:12px;color:#64748b;">{ht}</div>
                    <div class="h2h-score">{hg} &mdash; {ag}</div>
                    <div style="font-size:12px;color:#64748b;">{at}</div>
                  </div>
                  <div style="width:80px;"></div>
                </div>""")
            except:
                pass
