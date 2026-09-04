import streamlit as st

# Start background tasks (auto-trainer and keep-alive)
try:
    import background_tasks
    background_tasks.start_background_tasks()
except Exception as e:
    print("Could not start background tasks:", e)

from datetime import datetime, date, timedelta
from dotenv import load_dotenv
load_dotenv()

import predict_today
from live_data_fetcher import (
    get_live_fixtures, get_upcoming_fixtures, get_finished_fixtures,
    get_team_form, get_head_to_head,
    get_match_odds, compute_poisson_markets,
    LIVE_STATUSES, _get
)
import base64, os

# ─── Page config ──────────────────────────────────────────────────────────────
LOGO_B64 = ""
if os.path.exists("Better-logo.png"):
    with open("Better-logo.png", "rb") as f:
        LOGO_B64 = base64.b64encode(f.read()).decode()

st.set_page_config(
    page_title="Better · AI Football Predictions",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import zoneinfo
from streamlit_javascript import st_javascript

def get_client_timezone():
    if 'client_tz' not in st.session_state:
        # returns e.g. "Asia/Ho_Chi_Minh" or "America/Los_Angeles"
        tz = st_javascript("Intl.DateTimeFormat().resolvedOptions().timeZone")
        if tz:
            st.session_state.client_tz = tz
        else:
            return "UTC"
    return st.session_state.client_tz

def get_client_dates():
    tz_str = get_client_timezone()
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except:
        tz = zoneinfo.ZoneInfo("UTC")
    
    client_now = datetime.now(tz)
    today = client_now.date().isoformat()
    tomorrow = (client_now.date() + timedelta(days=1)).isoformat()
    return today, tomorrow

@st.cache_data(ttl=86400, show_spinner=False)
def get_league_map():
    """Dynamically fetch all valid competitions instead of hardcoding."""
    comps = []
    page = 1
    while True:
        res = _get('competitions', {'limit': 100, 'page': page}, ttl=86400)
        if not res or 'data' not in res: break
        comps.extend(res['data'])
        if page >= res.get('meta', {}).get('total_pages', 1): break
        page += 1
    return {
        c['id']: c['name']
        for c in comps
        if c.get('type') == 'league' and c.get('has_team_stats') == True
    }

def _load_css():
    base_css = ""
    if os.path.exists("style.css"):
        with open("style.css") as f:
            base_css = f.read()
    st.html(f"<style>{base_css}</style>")

_load_css()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_time(iso):
    try:    return datetime.fromisoformat(iso.replace('Z','+00:00')).strftime('%H:%M')
    except: return '??:??'

def fmt_date_short(iso):
    try:    return datetime.fromisoformat(iso.replace('Z','+00:00')).strftime('%d %b')
    except: return iso[:10]

def conf_color(pct):
    if pct >= 70: return "#10B981"   # very high — green
    if pct >= 60: return "#F59E0B"   # solid edge — amber
    return "#6b7280"                 # no clear edge — grey

def form_bubbles_html(form_arr, n=5):
    if not form_arr:
        return "<span style='color:#4a5470;font-size:11px;'>No data</span>"
    bubbles = ""
    for res in list(reversed(form_arr))[:n]:
        color = "var(--c-yes)" if res == 'W' else "var(--c-warn)" if res == 'D' else "var(--c-no)"
        bubbles += (
            f"<span style='display:inline-flex;align-items:center;justify-content:center;"
            f"width:22px;height:22px;border-radius:11px;background:{color};color:#fff;"
            f"font-size:10px;font-weight:bold;margin-right:3px;font-family:var(--f-data);'>{res}</span>"
        )
    return bubbles

def implied(v):
    try:    return 1.0 / float(v)
    except: return 0.5

def norm2(a, b):
    s = a + b
    return (round(a/s*100,1), round(b/s*100,1)) if s else (50.0, 50.0)

def norm3(a, b, c):
    s = a + b + c
    return (round(a/s*100,1), round(b/s*100,1), round(c/s*100,1)) if s else (33.3, 33.3, 33.3)

# ─── Cached data fetchers ─────────────────────────────────────────────────────
@st.cache_data(ttl=60,    show_spinner=False)
def cached_live():
    return get_live_fixtures(leagues=list(get_league_map().keys()))

@st.cache_data(ttl=300,   show_spinner=False)
def cached_upcoming():
    return get_upcoming_fixtures(leagues=list(get_league_map().keys()))

@st.cache_data(ttl=3600,  show_spinner=False)
def cached_team_form_v2(team_id):
    return get_team_form(team_id, last=8)

@st.cache_data(ttl=86400, show_spinner=False)
def cached_h2h_v2(home_id, away_id):
    return get_head_to_head(home_id, away_id, last=5)

@st.cache_data(ttl=1800,  show_spinner=False)
def cached_odds(fixture_id):
    return get_match_odds(fixture_id)

@st.cache_data(ttl=300, show_spinner=False)
def get_all_predictions(day: str, target_date: str):
    """Batch-compute Poisson predictions for all games on a given day."""
    if day == 'live':
        fixtures = cached_live()
    else:
        all_f  = cached_upcoming()
        fixtures = [f for f in all_f if f['utc_date'][:10] == target_date]

    results = []
    for f in fixtures:
        hf = cached_team_form_v2(f['home_team']['id'])
        af = cached_team_form_v2(f['away_team']['id'])
        poisson = compute_poisson_markets(
            f['home_team']['name'], f['away_team']['name'],
            hf.get('avg_scored', 1.3), hf.get('avg_conceded', 1.1),
            af.get('avg_scored', 1.1), af.get('avg_conceded', 1.3),
        )
        results.append({
            'id':          f['id'],
            'fixture':     f,
            'poisson':     poisson,
            'home_form':   hf,
            'away_form':   af,
        })

    return sorted(results, key=lambda x: x['fixture']['utc_date'])

@st.cache_data(ttl=600, show_spinner=False)
def get_past_predictions():
    league_map = get_league_map()
    valid_leagues = list(league_map.keys())
    
    finished = get_finished_fixtures(leagues=valid_leagues)
    
    # Sort descending by date and limit to 20 matches to avoid API rate limits on team form fetching
    finished = sorted(finished, key=lambda x: x.get('utc_date', ''), reverse=True)[:20]
    
    past = []
    for f in finished:
        hg = f.get('score', {}).get('home')
        ag = f.get('score', {}).get('away')
        if hg is None or ag is None: continue
        
        hf = cached_team_form_v2(f['home_team']['id'])
        af = cached_team_form_v2(f['away_team']['id'])
        poisson = compute_poisson_markets(
            f['home_team']['name'], f['away_team']['name'],
            hf.get('avg_scored', 1.3), hf.get('avg_conceded', 1.1),
            af.get('avg_scored', 1.1), af.get('avg_conceded', 1.3),
        )
        
        hw, dw, aw = poisson['home_win'], poisson['draw'], poisson['away_win']
        if hw >= dw and hw >= aw: ai_pick = 'home'
        elif aw >= hw and aw >= dw: ai_pick = 'away'
        else: ai_pick = 'draw'
        
        actual = 'home' if hg > ag else 'away' if ag > hg else 'draw'
        
        past.append({
            'home': f['home_team']['name'],
            'away': f['away_team']['name'],
            'score': f'{hg} - {ag}',
            'winner': actual,
            'ai_pick': ai_pick,
            'ai_prob': max(hw, dw, aw),
            'correct': ai_pick == actual,
            'date': fmt_date_short(f['utc_date']),
            'league': league_map.get(f['competition_id'], 'Unknown League'),
            'sort_time': f.get('utc_date', '')
        })
    
    return sorted(past, key=lambda x: x['sort_time'], reverse=True)

# ─── Session state defaults ────────────────────────────────────────────────────
if 'day' not in st.session_state:
    st.session_state.day = 'today'
if 'game_odds' not in st.session_state:
    st.session_state.game_odds = {}
if 'game_h2h' not in st.session_state:
    st.session_state.game_h2h = {}

# ─── Top bar ──────────────────────────────────────────────────────────────────
logo_html = (
    f"<img src='data:image/png;base64,{LOGO_B64}' height='34' "
    f"style='border-radius:4px;margin-right:8px;'>"
    if LOGO_B64 else ""
)

st.html(f"""
<div class="top-bar">
  <div class="top-bar-brand">
    {logo_html}
    <div>
      <div class="brand-name">better</div>
      <div class="brand-sub">AI Football Predictions</div>
    </div>
  </div>
  <div style="font-size:10px;color:#4a5470;font-family:var(--f-data);">
    Auto-refreshes every 5 min &nbsp;·&nbsp; {datetime.utcnow().strftime('%H:%M')} UTC
  </div>
</div>
""")

# ─── Day selector ─────────────────────────────────────────────────────────────
d_cols = st.columns([1, 1.3, 1, 1.5, 4.2])
for col, key, label in zip(d_cols[:4],
                            ['today', 'tomorrow', 'live', 'past'],
                            ['Today', 'Tomorrow', 'Live', 'Past Results']):
    is_active = st.session_state.day == key
    if col.button(label, use_container_width=True,
                  type='primary' if is_active else 'secondary'):
        st.session_state.day = key
        st.rerun()

# ─── Past Results ─────────────────────────────────────────────────────────────
if st.session_state.day == 'past':
    st.html("<div class='section-label' style='margin-top:0;'>Recent Model Performance</div>")
    try:
        past = get_past_predictions()
        if not past:
            st.info("No games finished recently.")
            st.stop()
            
        for p in past:
            bg = "#10b98120" if p['correct'] else "#ef444420"
            border = "#10b981" if p['correct'] else "#ef4444"
            icon = "✅ Right" if p['correct'] else "❌ Wrong"
            st.html(f"""
            <div style='background:{bg}; border:1px solid {border}; border-radius:6px; padding:16px; margin-bottom:10px;'>
                <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>
                    <span style='font-size:11px;color:var(--ink-2);letter-spacing:.05em;'>{p['date']} &middot; {p['league']}</span>
                    <span style='font-family:var(--f-ui);font-weight:700;font-size:12px;color:{border};'>{icon}</span>
                </div>
                <div style='display:flex;justify-content:space-between;align-items:center;'>
                    <div>
                        <div style='font-size:16px;font-weight:700;color:var(--ink-1);'>{p['home']} <span style='color:var(--c-home);font-family:var(--f-data);margin:0 8px;'>{p['score']}</span> {p['away']}</div>
                    </div>
                    <div style='text-align:right;'>
                        <div style='font-size:10px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.1em;'>AI Pick</div>
                        <div style='font-size:14px;font-weight:700;color:var(--ink-1);'>{p['ai_pick'].upper()} ({p['ai_prob']}%)</div>
                    </div>
                </div>
            </div>
            """)
    except Exception as e:
        import traceback
        st.error(f"Error loading past predictions: {e}")
        st.code(traceback.format_exc())
    st.stop()

# ─── Load all predictions ─────────────────────────────────────────────────# ── Load all predictions ──
with st.spinner("Loading predictions."):
    # Get dynamic timezone dates OUTSIDE the cached function to avoid Streamlit CachedWidgetWarning
    today_str, tomorrow_str = get_client_dates()
    target_date = today_str if st.session_state.day == 'today' else tomorrow_str
    if st.session_state.day == 'live':
        target_date = today_str
        
    all_games = get_all_predictions(st.session_state.day, target_date)

if not all_games:
    day_label = {'today':'today','tomorrow':'tomorrow','live':'live right now'}.get(st.session_state.day,'')
    st.html(f"<div class='cat-empty' style='padding:60px 20px;text-align:center;color:var(--ink-3);'>No games found {day_label}. Try selecting another day or checking back later.</div>")
    all_games = []

# ─── Game card renderer ───────────────────────────────────────────────────────
def render_card(game: dict, tab_key: str, pick_label: str, pick_pct: float, pick_color: str):
    f         = game['fixture']
    poisson   = game['poisson']
    home_form = game['home_form']
    away_form = game['away_form']

    home       = f['home_team']['name']
    away       = f['away_team']['name']
    kick_off   = fmt_time(f['utc_date'])
    date_str   = fmt_date_short(f['utc_date'])
    comp_id    = f.get('competition_id')
    league_map = get_league_map()
    league     = league_map.get(comp_id, 'Unknown League')
    fid        = f['id']
    is_live    = f['status'] in LIVE_STATUSES

    live_tag = "LIVE · " if is_live else ""
    score_tag = ""
    if is_live:
        sc = f.get('score', {})
        hg = sc.get('home', 0) or 0
        ag = sc.get('away', 0) or 0
        score_tag = f"  [{hg}–{ag}]"

    bar_w   = min(max(int(pick_pct), 0), 100)
    expander_label = f"{live_tag}{home}{score_tag}  vs  {away}   ·   {kick_off}  {date_str}   ·   {league}"

    with st.expander(expander_label, expanded=False):

        expert = poisson.get('expert_predictions', {})
        if expert:
            ep = expert.get('primary', {})
            mkt_cat = ep.get('market_category', 'Match Winner')
            selection = ep.get('selection', pick_label)
            conf = ep.get('confidence_score', int(pick_pct))
            risk = ep.get('risk_level', 'MEDIUM')
            
            risk_color = '#10b981' if risk == 'LOW' else ('#eab308' if risk == 'MEDIUM' else '#ef4444')
            
            st.html(f"""
            <div style='display:flex;align-items:center;justify-content:space-between;
                        padding:12px 0 14px 0;border-bottom:1px solid #1e2535;margin-bottom:14px;'>
              <div>
                <div style='font-size:17px;font-weight:700;color:#dde2ef;'>
                  {home} <span style='color:#4a5470;font-weight:400;'>vs</span> {away}
                </div>
                <div style='font-size:11px;color:#4a5470;margin-top:3px;'>
                  {league} &middot; {kick_off} UTC &middot; {date_str}
                </div>
              </div>
              
              <div style='background:#151b24; padding:10px 14px; border:1px solid #1e2535; border-radius:6px; min-width:240px;'>
                <div style='display:flex; justify-content:space-between; margin-bottom:6px;'>
                    <span style='font-size:10px; font-weight:700; color:var(--ink-2); letter-spacing:0.1em; text-transform:uppercase;'>[ PRIMARY SAFE PICK ]</span>
                    <span style='font-size:10px; font-weight:700; color:{risk_color}; padding:2px 6px; background:{risk_color}20; border-radius:4px;'>Risk: {risk}</span>
                </div>
                <div style='font-size:11px; color:#4a5470; text-transform:uppercase; margin-bottom:2px;'>Market: {mkt_cat}</div>
                <div style='font-size:16px; font-weight:700; color:{pick_color}; margin-bottom:6px;'>{selection.upper()}</div>
                <div style='display:flex; align-items:center; gap:8px;'>
                    <div class='conf-bar-wrap' style='flex-grow:1; margin:0;'>
                      <div class='conf-bar-fill' style='width:{conf}%; background:{pick_color};'></div>
                    </div>
                    <span style='font-family:var(--f-data); font-size:11px; color:{pick_color}; font-weight:700;'>{conf}%</span>
                </div>
                <div style='font-size:10px; color:#4a5470; margin-top:8px; font-style:italic;'>{ep.get('reasoning', '')}</div>
              </div>
            </div>
            """)
        else:
            # Fallback legacy card
            st.html(f"""
            <div style='display:flex;align-items:center;justify-content:space-between;
                        padding:12px 0 14px 0;border-bottom:1px solid #1e2535;margin-bottom:14px;'>
              <div>
                <div style='font-size:17px;font-weight:700;color:#dde2ef;'>
                  {home} <span style='color:#4a5470;font-weight:400;'>vs</span> {away}
                </div>
                <div style='font-size:11px;color:#4a5470;margin-top:3px;'>
                  {league} &middot; {kick_off} UTC &middot; {date_str}
                </div>
              </div>
              <div style='text-align:right;min-width:160px;'>
                <div style='font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#4a5470;margin-bottom:4px;'>AI Pick</div>
                <div style='font-size:15px;font-weight:700;color:{pick_color};'>{pick_label}</div>
                <div class='conf-bar-wrap'>
                  <div class='conf-bar-fill' style='width:{bar_w}%;background:{pick_color};'></div>
                </div>
                <div style='font-family:var(--f-data);font-size:11px;color:{pick_color};margin-top:3px;'>
                  {pick_pct}% confidence
                </div>
              </div>
            </div>
            """)

        inner = st.tabs(["Prediction", "Form & Stats", "Live Odds"])

        # ── Tab 1: Prediction ──────────────────────────────────────────────────
        with inner[0]:
            hw = poisson['home_win']
            dr = poisson['draw']
            aw = poisson['away_win']

            # Win probability bars
            for label_, pct_, color_ in [
                (home, hw, 'var(--c-home)'),
                ('Draw', dr, 'var(--c-draw)'),
                (away, aw, 'var(--c-away)'),
            ]:
                st.html(f"""
                <div style='margin-bottom:10px;'>
                  <div style='display:flex;justify-content:space-between;margin-bottom:3px;'>
                    <span style='font-size:12px;color:#dde2ef;font-weight:600;'>{label_}</span>
                    <span style='font-family:var(--f-data);font-size:12px;color:{color_};'>{pct_}%</span>
                  </div>
                  <div class='conf-bar-wrap'>
                    <div class='conf-bar-fill' style='width:{pct_}%;background:{color_};'></div>
                  </div>
                </div>
                """)

            # Extra Expert Picks
            expert = poisson.get('expert_predictions', {})
            if expert:
                v = expert.get('value', {})
                s = expert.get('stat', {})
                
                def render_subpick(title, p):
                    risk = p.get('risk_level', 'MEDIUM')
                    rc = '#10b981' if risk == 'LOW' else ('#eab308' if risk == 'MEDIUM' else '#ef4444')
                    return f"""
                    <div style='background:#111520; border:1px solid #1e2535; border-radius:6px; padding:10px; margin-bottom:12px; flex:1; min-width:200px;'>
                        <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                            <span style='font-size:9px; font-weight:700; color:var(--ink-3); text-transform:uppercase; letter-spacing:0.05em;'>{title}</span>
                            <span style='font-size:9px; color:{rc};'>{risk} RISK</span>
                        </div>
                        <div style='font-size:13px; font-weight:700; color:#dde2ef; margin-bottom:2px;'>{p.get('selection', '')}</div>
                        <div style='font-size:10px; color:#4a5470;'>{p.get('market_name', '')} &middot; {p.get('confidence_score', 0)}% Conf</div>
                        <div style='font-size:9px; color:#4a5470; margin-top:6px; font-style:italic;'>{p.get('reasoning', '')}</div>
                    </div>
                    """
                
                st.html(f"<div style='display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px;'>" + render_subpick("Value Pick", v) + render_subpick("Stat/Prop Pick", s) + "</div>")

            # xG + goals markets
            xh = poisson['xg_home']
            xa = poisson['xg_away']
            o15 = poisson['over_1_5']
            o25 = poisson['over_2_5']
            o35 = poisson['over_3_5']
            btts = poisson['btts']

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("xG Home",   str(xh))
            c2.metric("xG Away",   str(xa))
            c3.metric("Over 1.5",  f"{o15}%")
            c4.metric("Over 2.5",  f"{o25}%")
            c5.metric("Over 3.5",  f"{o35}%")
            c6.metric("BTTS",      f"{btts}%")

            # Most likely scores
            st.html("<div style='margin-top:16px;font-size:10px;color:#4a5470;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px;'>Most Likely Scores</div>")
            score_html = "".join(
                f"<span style='background:#111520;border:1px solid #1e2535;border-radius:6px;"
                f"padding:6px 14px;font-family:var(--f-data);font-size:14px;color:#dde2ef;"
                f"margin-right:8px;margin-bottom:8px;display:inline-block;'>"
                f"{sc_} <span style='font-size:9px;color:#4a5470;'>({p_}%)</span></span>"
                for sc_, p_ in poisson['top_scores']
            )
            st.html(f"<div style='display:flex;flex-wrap:wrap;'>{score_html}</div>")

            if poisson.get('low_data_warning'):
                st.html(f"<div style='font-size:11px;color:var(--c-warn);margin-top:10px;'>{poisson['low_data_warning']}</div>")

        # ── Tab 2: Form & Stats ────────────────────────────────────────────────
        with inner[1]:
            st.html(f"""
            <div style='margin-bottom:14px;'>
              <div style='display:flex;align-items:center;justify-content:space-between;
                          padding:10px 12px;background:#0d1018;border:1px solid #1e2535;
                          border-radius:7px;margin-bottom:7px;'>
                <span style='font-size:13px;font-weight:600;color:#dde2ef;'>{home}</span>
                <div>{form_bubbles_html(home_form.get('form',[]))}</div>
              </div>
              <div style='display:flex;align-items:center;justify-content:space-between;
                          padding:10px 12px;background:#0d1018;border:1px solid #1e2535;border-radius:7px;'>
                <span style='font-size:13px;font-weight:600;color:#dde2ef;'>{away}</span>
                <div>{form_bubbles_html(away_form.get('form',[]))}</div>
              </div>
            </div>
            """)

            # Comparison bars
            for lbl_, hv_, av_ in [
                ('Avg Goals Scored',   home_form.get('avg_scored', 0),   away_form.get('avg_scored', 0)),
                ('Avg Goals Conceded', home_form.get('avg_conceded', 0), away_form.get('avg_conceded', 0)),
                ('Points per Game',    home_form.get('pts_per_game', 0), away_form.get('pts_per_game', 0)),
            ]:
                total_ = abs(hv_) + abs(av_)
                hp_ = round(abs(hv_)/total_*100, 1) if total_ else 50
                ap_ = round(abs(av_)/total_*100, 1) if total_ else 50
                st.html(f"""
                <div style='margin-bottom:10px;'>
                  <div style='text-align:center;font-size:10px;color:#94a3b8;margin-bottom:4px;
                               text-transform:uppercase;letter-spacing:.05em;'>{lbl_}</div>
                  <div style='display:flex;align-items:center;gap:10px;'>
                    <div style='flex:0 0 34px;font-family:var(--f-data);font-size:12px;
                                color:var(--c-home);text-align:right;'>{hv_}</div>
                    <div style='flex:1;height:5px;background:#1e293b;border-radius:3px;
                                display:flex;overflow:hidden;'>
                      <div style='width:{hp_}%;background:var(--c-home);'></div>
                      <div style='width:{ap_}%;background:var(--c-away);'></div>
                    </div>
                    <div style='flex:0 0 34px;font-family:var(--f-data);font-size:12px;
                                color:var(--c-away);text-align:left;'>{av_}</div>
                  </div>
                </div>
                """)

            # H2H section
            st.html("<div style='margin-top:16px;font-size:10px;color:#4a5470;letter-spacing:.08em;"
                    "text-transform:uppercase;margin-bottom:8px;'>Head-to-Head</div>")

            h2h_ss_key = f'h2h_{fid}'
            if h2h_ss_key not in st.session_state.game_h2h:
                if st.button("Load H2H", key=f"h2h_{fid}_{tab_key}"):
                    with st.spinner("Fetching H2H…"):
                        st.session_state.game_h2h[h2h_ss_key] = cached_h2h_v2(
                            f['home_team']['id'], f['away_team']['id']
                        )
                    st.rerun()
            else:
                h2h = st.session_state.game_h2h[h2h_ss_key]
                matches = h2h.get('matches', [])
                if not matches:
                    st.info("No H2H data found.")
                else:
                    for m in matches[:5]:
                        try:
                            dt   = datetime.fromisoformat(m['utc_date'].replace('Z','+00:00')).strftime('%d %b %Y')
                            ht_  = m['home_team']['name']
                            at_  = m['away_team']['name']
                            hg_  = m['score'].get('home','?')
                            ag_  = m['score'].get('away','?')
                            win  = m['score'].get('winner')
                            hs_  = 'color:var(--c-home);font-weight:700;' if win=='home' else 'color:#94a3b8;'
                            as__ = 'color:var(--c-away);font-weight:700;' if win=='away' else 'color:#94a3b8;'
                            st.html(f"""
                            <div style='display:flex;align-items:center;justify-content:space-between;
                                        padding:7px 0;border-bottom:1px solid #1e2535;'>
                              <span style='font-size:10px;color:#4a5470;font-family:var(--f-data);
                                           flex:0 0 72px;'>{dt}</span>
                              <div style='flex:1;display:flex;align-items:center;justify-content:center;gap:10px;'>
                                <span style='font-size:12px;{hs_}'>{ht_}</span>
                                <span style='font-family:var(--f-data);font-size:15px;color:#dde2ef;
                                             min-width:36px;text-align:center;'>{hg_}–{ag_}</span>
                                <span style='font-size:12px;{as__}'>{at_}</span>
                              </div>
                            </div>
                            """)
                        except Exception:
                            pass

        # ── Tab 3: Live Odds ───────────────────────────────────────────────────
        with inner[2]:
            odds_ss_key = f'odds_{fid}'
            if odds_ss_key not in st.session_state.game_odds:
                btn_cols = st.columns([1, 3])
                if btn_cols[0].button("Fetch Live Odds", key=f"odds_{fid}_{tab_key}"):
                    with st.spinner("Fetching Bet365 odds…"):
                        st.session_state.game_odds[odds_ss_key] = cached_odds(fid)
                    st.rerun()
                st.html("<div style='font-size:11px;color:#4a5470;margin-top:6px;'>Loads Bet365 odds for this match.</div>")
            else:
                odds = st.session_state.game_odds.get(odds_ss_key) or {}

                if not odds:
                    st.info("No Bet365 odds available for this match.")
                else:
                    # Match odds
                    if 'match_odds' in odds:
                        o = odds['match_odds']
                        oh_ = float(o['home']['last_seen'])
                        od_ = float(o['draw']['last_seen'])
                        oa_ = float(o['away']['last_seen'])
                        hp_, dp_, ap_ = norm3(implied(oh_), implied(od_), implied(oa_))
                        st.html(f"""
                        <div style='margin-bottom:14px;'>
                          <div style='font-size:10px;color:#4a5470;text-transform:uppercase;
                                      letter-spacing:.08em;margin-bottom:8px;'>Match Odds (Bet365)</div>
                          <div style='display:flex;gap:8px;'>
                            <div style='flex:1;background:#0d1018;border:1px solid #1e2535;border-radius:7px;
                                        padding:10px;text-align:center;'>
                              <div style='font-size:10px;color:#4a5470;margin-bottom:4px;'>{home}</div>
                              <div style='font-family:var(--f-data);font-size:22px;color:var(--c-home);'>{oh_}</div>
                              <div style='font-size:10px;color:#4a5470;'>{hp_}%</div>
                            </div>
                            <div style='flex:1;background:#0d1018;border:1px solid #1e2535;border-radius:7px;
                                        padding:10px;text-align:center;'>
                              <div style='font-size:10px;color:#4a5470;margin-bottom:4px;'>Draw</div>
                              <div style='font-family:var(--f-data);font-size:22px;color:var(--c-draw);'>{od_}</div>
                              <div style='font-size:10px;color:#4a5470;'>{dp_}%</div>
                            </div>
                            <div style='flex:1;background:#0d1018;border:1px solid #1e2535;border-radius:7px;
                                        padding:10px;text-align:center;'>
                              <div style='font-size:10px;color:#4a5470;margin-bottom:4px;'>{away}</div>
                              <div style='font-family:var(--f-data);font-size:22px;color:var(--c-away);'>{oa_}</div>
                              <div style='font-size:10px;color:#4a5470;'>{ap_}%</div>
                            </div>
                          </div>
                        </div>
                        """)

                    def _market_row(title, items):
                        """items = list of (label, odd, color)"""
                        cards = ""
                        for lbl_, odd_, col_ in items:
                            p_ = round(implied(odd_)*100, 1)
                            cards += (
                                f"<div style='flex:1;background:#0d1018;border:1px solid #1e2535;"
                                f"border-radius:7px;padding:10px;text-align:center;'>"
                                f"<div style='font-size:10px;color:#4a5470;margin-bottom:4px;'>{lbl_}</div>"
                                f"<div style='font-family:var(--f-data);font-size:18px;color:{col_};'>{odd_}</div>"
                                f"<div style='font-size:10px;color:#4a5470;'>{p_}% implied</div>"
                                f"</div>"
                            )
                        return (
                            f"<div style='margin-bottom:12px;'>"
                            f"<div style='font-size:10px;color:#4a5470;text-transform:uppercase;"
                            f"letter-spacing:.08em;margin-bottom:6px;'>{title}</div>"
                            f"<div style='display:flex;gap:8px;'>{cards}</div></div>"
                        )

                    # BTTS
                    if 'btts' in odds:
                        try:
                            oy = odds['btts']['yes']['last_seen']
                            on_ = odds['btts']['no']['last_seen']
                            st.html(_market_row("BTTS", [("Yes", oy, "var(--c-yes)"), ("No", on_, "var(--c-no)")]))
                        except Exception: pass

                    # Total Goals 1.5 / 2.5 / 3.5
                    if 'total_goals' in odds:
                        tg = odds['total_goals']
                        for line in ['1.5','2.5','3.5']:
                            if line in tg:
                                try:
                                    ov_ = tg[line]['over']['last_seen']
                                    un_ = tg[line]['under']['last_seen']
                                    st.html(_market_row(f"Total Goals {line}",
                                        [(f"Over {line}", ov_, "var(--c-yes)"), (f"Under {line}", un_, "var(--c-no)")]))
                                except Exception: pass

                    # Corners
                    if 'match_corners' in odds:
                        lines = list(odds['match_corners'].keys())
                        mid = lines[len(lines)//2] if lines else None
                        if mid:
                            try:
                                ov_ = odds['match_corners'][mid]['over']['last_seen']
                                un_ = odds['match_corners'][mid]['under']['last_seen']
                                st.html(_market_row(f"Corners {mid}",
                                    [(f"Over {mid}", ov_, "var(--c-yes)"), (f"Under {mid}", un_, "var(--c-no)")]))
                            except Exception: pass

                    # Asian Handicap
                    if 'asian_handicap' in odds:
                        ah = odds['asian_handicap']
                        try:
                            hl = list(ah.get('home',{}).keys())[0]
                            al = list(ah.get('away',{}).keys())[0]
                            oh_ = ah['home'][hl]['last_seen']
                            oa_ = ah['away'][al]['last_seen']
                            st.html(_market_row("Asian Handicap",
                                [(f"{home} ({hl})", oh_, "var(--c-home)"),
                                 (f"{away} ({al})", oa_, "var(--c-away)")]))
                        except Exception: pass

                    # Draw No Bet
                    if 'draw_no_bet' in odds:
                        try:
                            oh_ = odds['draw_no_bet']['home']['last_seen']
                            oa_ = odds['draw_no_bet']['away']['last_seen']
                            st.html(_market_row("Draw No Bet",
                                [(home, oh_, "var(--c-home)"), (away, oa_, "var(--c-away)")]))
                        except Exception: pass

# ─── Unified AI Predictions ───────────────────────────────────────────────────
st.html("""<div style='font-size:10px;color:#4a5470;letter-spacing:.1em;text-transform:uppercase;
        margin-bottom:14px;'>AI Market Scanner — Safest prediction per game across all markets</div>""")

# Group by league first
from collections import defaultdict
grouped_games = defaultdict(list)
for game in all_games:
    comp_id = game['fixture'].get('competition_id')
    league = "Unknown League"
    if comp_id:
        league_map = get_league_map()
        league = league_map.get(comp_id, 'Unknown League')
    grouped_games[league].append(game)

# ── League priority ordering ──────────────────────────────────────────────────
LEAGUE_PRIORITY = [
    "Premier League",      # England
    "LaLiga",              # Spain
    "Serie A",             # Italy
    "Bundesliga",          # Germany
    "Ligue 1",             # France
    "UEFA Champions League",
    "UEFA Europa League",
    "Championship",        # England 2nd
    "Liga Portugal Betclic",  # Portugal
    "Eredivisie",          # Netherlands
    "Scottish Premiership",
    "LaLiga 2",
    "2. Bundesliga",
    "Serie B",
    "Ligue 2",
    "Russian Premier League",
    "Ukrainian Premier League",
    "Turkish Super Lig",
    "MLS",
    "Brasileirao Serie A",
]

def league_sort_key(name):
    if name in LEAGUE_PRIORITY:
        return LEAGUE_PRIORITY.index(name)
    return len(LEAGUE_PRIORITY) + 1  # Push unknown leagues to the bottom

for league in sorted(grouped_games.keys(), key=league_sort_key):
    # Display the league name as a distinct header
    st.html(f"""
    <div style='margin-top: 24px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
        <div style='width: 4px; height: 16px; background: var(--c-home); border-radius: 2px;'></div>
        <div style='font-size: 15px; font-weight: 700; color: #ffffff; letter-spacing: 0.05em; text-transform: uppercase;'>
            {league}
        </div>
    </div>
    """)
    
    # Sort games within this league by confidence
    league_games = sorted(grouped_games[league], key=lambda g: g['poisson'].get('expert_predictions', {}).get('primary', {}).get('confidence_score', 0), reverse=True)
    
    for game in league_games:
        p  = game['poisson']
        ep = p.get('expert_predictions', {})
        pr = ep.get('primary', {})

        if pr:
            pick = pr.get('selection', 'N/A')
            pct  = pr.get('confidence_score', 50)
        else:
            hw_, dr_, aw_ = p['home_win'], p['draw'], p['away_win']
            if hw_ >= dr_ and hw_ >= aw_:
                pick, pct = f"{game['fixture']['home_team']['name']} Win", hw_
            elif aw_ >= hw_ and aw_ >= dr_:
                pick, pct = f"{game['fixture']['away_team']['name']} Win", aw_
            else:
                pick, pct = "Draw", dr_

        # Only surface picks where we have genuine edge (>= 60% confidence).
        # Below that threshold, label it as no clear edge to avoid bad calls.
        if pct < 60:
            pick_display = "No Clear Edge"
            color_display = "#6b7280"  # grey
        else:
            pick_display = pick
            color_display = conf_color(pct)
        render_card(game, 'unified', pick_display, pct, color_display)

