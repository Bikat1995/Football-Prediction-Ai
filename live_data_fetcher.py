"""
live_data_fetcher.py — EasySoccerData (Sofascore) backend. No API keys required.
"""
from __future__ import annotations
import os, json, time, math, pickle, tempfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import esd

# Cache setup
try:
    CACHE_DIR = "cache/sofascore"
    os.makedirs(CACHE_DIR, exist_ok=True)
    _t = os.path.join(CACHE_DIR, ".w")
    open(_t, "w").close(); os.remove(_t)
except Exception:
    CACHE_DIR = os.path.join(tempfile.gettempdir(), "sfc_cache")
    os.makedirs(CACHE_DIR, exist_ok=True)

def _cp(k): return os.path.join(CACHE_DIR, f"{k}.json")
def _rc(k, ttl=1800):
    p = _cp(k)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return None
def _wc(k, d):
    try: json.dump(d, open(_cp(k), "w", encoding="utf-8"))
    except Exception: pass

_sc = esd.SofascoreClient()
LIVE_STATUSES     = {"inprogress"}
FINISHED_STATUSES = {"finished"}
UPCOMING_STATUSES = {"notstarted"}
CURRENT_SEASON    = 2026

LEAGUES = {
    17:  {"name": "Premier League",    "country": "England"},
    8:   {"name": "La Liga",           "country": "Spain"},
    23:  {"name": "Serie A",           "country": "Italy"},
    35:  {"name": "Bundesliga",        "country": "Germany"},
    34:  {"name": "Ligue 1",           "country": "France"},
    7:   {"name": "Champions League",  "country": "Europe"},
    679: {"name": "Europa League",     "country": "Europe"},
    44:  {"name": "Championship",      "country": "England"},
    52:  {"name": "Eredivisie",        "country": "Netherlands"},
    60:  {"name": "Primeira Liga",     "country": "Portugal"},
    10:  {"name": "Super Lig",         "country": "Turkey"},
}

def get_season_id(tid: int) -> Optional[int]:
    ck = f"season_id_{tid}"
    c = _rc(ck, 86400)
    if c: return c.get("season_id")
    try:
        ss = _sc.get_tournament_seasons(tid)
        if ss:
            sid = ss[0].id
            _wc(ck, {"season_id": sid})
            return sid
    except Exception as e:
        print(f"[ESD] season_id {tid}: {e}")
    return None

def _logo(tid): return f"https://api.sofascore.app/api/v1/team/{tid}/image"
def _lleague(tid): return f"https://api.sofascore.app/api/v1/unique-tournament/{tid}/image"
def _stype(e):
    st = e.status.type
    return st.value if hasattr(st, "value") else str(st)
def _short(s):
    return {"inprogress": "1H", "finished": "FT", "notstarted": "NS",
            "postponed": "PST", "canceled": "CANC", "halftime": "HT"}.get(s, s.upper()[:4])

def _e2d(event, tid, sid):
    li = LEAGUES.get(tid, {})
    st = _stype(event)
    hs = getattr(getattr(event, "home_score", None), "current", None)
    aws = getattr(getattr(event, "away_score", None), "current", None)
    dt = datetime.fromtimestamp(event.start_timestamp, tz=timezone.utc)
    return {
        "fixture": {"id": event.id, "date": dt.isoformat(),
                    "status": {"short": _short(st), "long": event.status.description, "elapsed": None}},
        "league":  {"id": tid, "season": sid, "name": li.get("name", "Unknown"),
                    "country": li.get("country", ""), "logo": _lleague(tid)},
        "teams":   {"home": {"id": event.home_team.id, "name": event.home_team.name, "logo": _logo(event.home_team.id)},
                    "away": {"id": event.away_team.id, "name": event.away_team.name, "logo": _logo(event.away_team.id)}},
        "goals":   {"home": hs, "away": aws},
        "events":  [],
    }

def get_upcoming_fixtures(leagues=None) -> list:
    ck = "upcoming_fixtures"
    c = _rc(ck, 300)
    if c is not None: return c
    today = date.today(); tmrw = today + timedelta(days=1)
    win = {today.isoformat(), tmrw.isoformat()}
    out = []
    for tid in LEAGUES:
        sid = get_season_id(tid)
        if not sid: continue
        try:
            for e in _sc.get_tournament_events(tid, sid, upcoming=True, page=0):
                dt = datetime.fromtimestamp(e.start_timestamp, tz=timezone.utc)
                if dt.date().isoformat() in win and _stype(e) in UPCOMING_STATUSES:
                    out.append(_e2d(e, tid, sid))
        except Exception as ex:
            print(f"[ESD] upcoming {tid}: {ex}")
    _wc(ck, out)
    return out

def get_live_fixtures(leagues=None) -> list:
    ck = "live_fixtures"
    c = _rc(ck, 30)
    if c is not None: return c
    out = []
    try:
        for e in _sc.get_events(live=True):
            tid = getattr(getattr(e, "tournament", None), "id", None)
            if tid in LEAGUES:
                out.append(_e2d(e, tid, get_season_id(tid) or CURRENT_SEASON))
    except Exception as ex:
        print(f"[ESD] live: {ex}")
    _wc(ck, out)
    return out

def get_fixtures_for_date(target_date: str, leagues=None) -> list:
    all_fix = get_upcoming_fixtures(leagues) + get_live_fixtures(leagues)
    return [f for f in all_fix if f["fixture"]["date"][:10] == target_date]

def get_team_form(team_id: int, last: int = 8) -> dict:
    ck = f"form_{team_id}_{last}"
    c = _rc(ck, 43200)
    if c is not None: return c
    try:
        collected = []
        for page in range(4):
            evs = _sc.get_team_events(team_id, upcoming=False, page=page)
            if not evs: break
            for e in evs:
                if _stype(e) not in FINISHED_STATUSES: continue
                hs = getattr(getattr(e, "home_score", None), "current", None)
                aws = getattr(getattr(e, "away_score", None), "current", None)
                if hs is None or aws is None: continue
                collected.append(e)
            if len(collected) >= last: break
        m = collected[:last]
        if not m:
            r = {}
        else:
            sc2, co = 0, 0
            for x in m:
                ih = x.home_team.id == team_id
                h, a = x.home_score.current or 0, x.away_score.current or 0
                sc2 += h if ih else a
                co  += a if ih else h
            n = len(m)
            r = {"avg_scored": round(sc2/n, 3), "avg_conceded": round(co/n, 3), "games": n}
        _wc(ck, r)
        return r
    except Exception as ex:
        print(f"[ESD] form {team_id}: {ex}")
        return {}

def get_head_to_head(home_id: int, away_id: int, last: int = 10) -> dict:
    ck = f"h2h_{home_id}_{away_id}_{last}"
    c = _rc(ck, 604800)
    if c is not None: return c
    try:
        h2h = []
        for page in range(4):
            evs = _sc.get_team_events(home_id, upcoming=False, page=page)
            if not evs: break
            for e in evs:
                if _stype(e) not in FINISHED_STATUSES: continue
                hs = getattr(getattr(e, "home_score", None), "current", None)
                aws = getattr(getattr(e, "away_score", None), "current", None)
                if hs is None or aws is None: continue
                if e.home_team.id == away_id or e.away_team.id == away_id:
                    h2h.append(e)
            if len(h2h) >= last: break
        m = h2h[:last]
        if not m:
            r = {}
        else:
            hs2, as2 = 0, 0
            for x in m:
                ih = x.home_team.id == home_id
                h, a = x.home_score.current or 0, x.away_score.current or 0
                hs2 += h if ih else a
                as2 += a if ih else h
            n = len(m)
            r = {"home_avg": round(hs2/n, 3), "away_avg": round(as2/n, 3), "games": n}
        _wc(ck, r)
        return r
    except Exception as ex:
        print(f"[ESD] h2h {home_id}-{away_id}: {ex}")
        return {}

def get_fixture_predictions(fixture_id: int) -> dict: return {}
def get_api_prediction_probs(fixture_id: int) -> dict: return {}
def get_team_season_stats(team_id: int, league_id: int, season: int) -> dict: return {}

def get_league_top_scorers(league_id: int, season: int) -> list:
    ck = f"top_sc_{league_id}"
    c = _rc(ck, 86400)
    if c is not None: return c
    try:
        sid = get_season_id(league_id)
        if not sid: return []
        players = _sc.get_tournament_top_players(league_id, sid)
        pid = lambda p: getattr(p, "id", 0)
        r = [{"player": {"name": getattr(p, "name", "?"),
                         "photo": f"https://api.sofascore.app/api/v1/player/{pid(p)}/image"},
              "team": {"name": getattr(getattr(p, "team", None), "name", ""), "logo": ""},
              "statistics": {"goals": getattr(p, "goals", 0)}}
             for p in (players or [])[:10]]
        _wc(ck, r)
        return r
    except Exception as ex:
        print(f"[ESD] top_sc {league_id}: {ex}")
        return []

def get_league_top_assists(league_id: int, season: int) -> list: return []

ML_MODEL_DATA = None
try:
    with open("models/xgb_classifier.pkl", "rb") as f:
        ML_MODEL_DATA = pickle.load(f)
except Exception as e:
    print(f"Warning: ML model not found - {e}")

def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def compute_poisson_markets(home_team_name: str, away_team_name: str,
                            home_avg_scored: float, home_avg_conceded: float,
                            away_avg_scored: float, away_avg_conceded: float,
                            max_goals: int = 6) -> dict:
    lam_h = max(0.3, (home_avg_scored + away_avg_conceded) / 2)
    lam_a = max(0.3, (away_avg_scored + home_avg_conceded) / 2)
    matrix = {(h, a): _poisson_pmf(lam_h, h) * _poisson_pmf(lam_a, a)
              for h in range(max_goals + 1) for a in range(max_goals + 1)}
    total = sum(matrix.values())
    p_home = sum(v for (h, a), v in matrix.items() if h > a) / total
    p_draw = sum(v for (h, a), v in matrix.items() if h == a) / total
    p_away = sum(v for (h, a), v in matrix.items() if h < a) / total
    ml_conf = 0; warn = None
    if ML_MODEL_DATA:
        import difflib, numpy as np
        known = list(ML_MODEL_DATA.get("team_encodings", {}).keys())
        def _f(n):
            m = difflib.get_close_matches(n, known, n=1, cutoff=0.5)
            return m[0] if m else None
        hm = _f(home_team_name); am = _f(away_team_name)
        if hm and am:
            try:
                enc = ML_MODEL_DATA["team_encodings"]
                sc3 = ML_MODEL_DATA.get("scaler")
                mod = ML_MODEL_DATA.get("model")
                feats = np.array([[enc[hm], enc[am], home_avg_scored, home_avg_conceded,
                                   away_avg_scored, away_avg_conceded]])
                if sc3: feats = sc3.transform(feats)
                mp = mod.predict_proba(feats)[0]; ml_conf = float(max(mp)); b = 0.4
                p_home = p_home*(1-b)+mp[2]*b; p_draw = p_draw*(1-b)+mp[1]*b
                p_away = p_away*(1-b)+mp[0]*b
                s = p_home+p_draw+p_away; p_home /= s; p_draw /= s; p_away /= s
            except Exception as ex:
                print(f"ML blend failed: {ex}")
        elif not hm:
            warn = f"Limited ML data for {home_team_name}."
        else:
            warn = f"Limited ML data for {away_team_name}."
    p_btts = sum(v for (h, a), v in matrix.items() if h >= 1 and a >= 1) / total
    p15 = sum(v for (h, a), v in matrix.items() if h+a > 1) / total
    p25 = sum(v for (h, a), v in matrix.items() if h+a > 2) / total
    p35 = sum(v for (h, a), v in matrix.items() if h+a > 3) / total
    ss = sorted(matrix.items(), key=lambda x: x[1], reverse=True)
    top_scores = [(f"{h}-{a}", round(v/total*100, 1)) for (h, a), v in ss[:5]]
    return {
        "home_win": round(p_home*100, 1), "draw": round(p_draw*100, 1),
        "away_win": round(p_away*100, 1), "btts": round(p_btts*100, 1),
        "over_1_5": round(p15*100, 1),   "over_2_5": round(p25*100, 1),
        "over_3_5": round(p35*100, 1),
        "dc_home_draw": round((p_home+p_draw)*100, 1),
        "dc_away_draw": round((p_away+p_draw)*100, 1),
        "top_scores": top_scores,
        "lam_home": round(lam_h, 2), "lam_away": round(lam_a, 2),
        "ml_confidence": round(ml_conf*100, 1), "low_data_warning": warn,
    }
