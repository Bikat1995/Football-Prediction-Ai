import os

with open('dashboard.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Hide spinners
code = code.replace('@st.cache_data(ttl=60)', '@st.cache_data(ttl=60, show_spinner=False)')
code = code.replace('@st.cache_data(ttl=300)', '@st.cache_data(ttl=300, show_spinner=False)')
code = code.replace('@st.cache_data(ttl=3600)', '@st.cache_data(ttl=3600, show_spinner=False)')
code = code.replace('@st.cache_data(ttl=86400)', '@st.cache_data(ttl=86400, show_spinner=False)')

# 2. Revert sidebar finished score display (not needed since we filter them out now)
code = code.replace("if m['status'] in LIVE_STATUSES or m['status'] in ['finished', 'awarded']:", "if m['status'] in LIVE_STATUSES:")
code = code.replace("hg = m['goals'].get('home', '?') if m['goals'] else '?'\n                ag = m['goals'].get('away', '?') if m['goals'] else '?'", "hg = m['goals'].get('home', '?')\n                ag = m['goals'].get('away', '?')")

# 3. AI Recommendation Banner - exclude over 1.5, pick the best value
old_banner_logic = '''candidates = [
    (hw,   f"Home Win — {selected_fixture['home_name']} ({hw:.1f}%)"),
    (aw,   f"Away Win — {selected_fixture['away_name']} ({aw:.1f}%)"),
    (dc_hd,f"{selected_fixture['home_name']} or Draw ({dc_hd:.1f}%)"),
    (dc_ad,f"{selected_fixture['away_name']} or Draw ({dc_ad:.1f}%)"),
    (bt,   f"Both Teams to Score ({bt:.1f}%)"),
    (o25,  f"Over 2.5 Goals ({o25:.1f}%)"),
    (o15,  f"Over 1.5 Goals ({o15:.1f}%)"),
]
best_prob, ai_rec = max(candidates, key=lambda x: x[0])'''

new_banner_logic = '''# Select top pick focusing on value, ignoring the "too safe" Over 1.5
candidates = [
    (hw,   f"Home Win — {selected_fixture['home_name']} ({hw:.1f}%)"),
    (aw,   f"Away Win — {selected_fixture['away_name']} ({aw:.1f}%)"),
    (dc_hd,f"{selected_fixture['home_name']} or Draw ({dc_hd:.1f}%)"),
    (dc_ad,f"{selected_fixture['away_name']} or Draw ({dc_ad:.1f}%)"),
    (bt,   f"Both Teams to Score ({bt:.1f}%)"),
    (o25,  f"Over 2.5 Goals ({o25:.1f}%)"),
]
# If double chance is very high, prefer it over match winner
best_prob, ai_rec = max(candidates, key=lambda x: x[0])
# If the win prob is > 55%, recommend it confidently instead of double chance
if hw > 55.0 and hw > aw:
    ai_rec = f"Home Win — {selected_fixture['home_name']} ({hw:.1f}%)"
elif aw > 55.0 and aw > hw:
    ai_rec = f"Away Win — {selected_fixture['away_name']} ({aw:.1f}%)"
'''
code = code.replace(old_banner_logic, new_banner_logic)

# 4. Add Broad Markets Section to Betting Markets Tab
odds_insertion = '''
    if match_odds and 'match_odds' in match_odds:
        st.html('<div class="section-title" style="margin-top:24px;">Live Bookmaker Odds (Bet365)</div>')
        o = match_odds['match_odds']
        oc1, oc2, oc3 = st.columns(3)
        for col, title, key in [(oc1, selected_fixture['home_name'], 'home'), (oc2, 'Draw', 'draw'), (oc3, selected_fixture['away_name'], 'away')]:
            open_odd = float(o[key]['opening'])
            cur_odd = float(o[key]['last_seen'])
            trend = "⬇️" if cur_odd < open_odd else ("⬆️" if cur_odd > open_odd else "➖")
            col.html(f'<div class="ou-card"><div class="ou-title">{title}</div><div style="font-size:24px;font-weight:700;color:#dde2ef;">{cur_odd:.2f}</div><div style="font-size:12px;color:#94a3b8;margin-top:4px;">Opened at {open_odd:.2f} {trend}</div></div>')

        # Add safe props
        st.html('<div class="section-title" style="margin-top:24px;">Safe Props & Handicaps</div>')
        prop_c1, prop_c2, prop_c3 = st.columns(3)
        
        # Asian Handicap
        if 'asian_handicap' in match_odds:
            with prop_c1:
                st.html('<div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px;">Asian Handicap</div>')
                # Pick the most balanced line
                lines = list(match_odds['asian_handicap'].keys())
                if lines:
                    # just take the first line for display
                    line = lines[0]
                    line_data = match_odds['asian_handicap'][line]
                    h_odd = line_data['home']['last_seen']
                    a_odd = line_data['away']['last_seen']
                    st.html(f'<div class="ou-card" style="padding:10px;"><div class="ou-row" style="border:none;"><div class="ou-team">{selected_fixture["home_name"]} {line}</div><div class="ou-vals">{h_odd}</div></div><div class="ou-row" style="border:none;"><div class="ou-team">{selected_fixture["away_name"]}</div><div class="ou-vals">{a_odd}</div></div></div>')
                    
        # Draw No Bet
        if 'draw_no_bet' in match_odds:
            with prop_c2:
                st.html('<div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px;">Draw No Bet</div>')
                dnb = match_odds['draw_no_bet']
                h_odd = dnb['home']['last_seen']
                a_odd = dnb['away']['last_seen']
                st.html(f'<div class="ou-card" style="padding:10px;"><div class="ou-row" style="border:none;"><div class="ou-team">{selected_fixture["home_name"]}</div><div class="ou-vals">{h_odd}</div></div><div class="ou-row" style="border:none;"><div class="ou-team">{selected_fixture["away_name"]}</div><div class="ou-vals">{a_odd}</div></div></div>')
                
        # Match Corners
        if 'match_corners' in match_odds:
            with prop_c3:
                st.html('<div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px;">Total Corners</div>')
                lines = list(match_odds['match_corners'].keys())
                if lines:
                    line = lines[len(lines)//2] # middle line
                    line_data = match_odds['match_corners'][line]
                    o_odd = line_data['over']['last_seen']
                    u_odd = line_data['under']['last_seen']
                    st.html(f'<div class="ou-card" style="padding:10px;"><div class="ou-row" style="border:none;"><div class="ou-team">Over {line}</div><div class="ou-vals">{o_odd}</div></div><div class="ou-row" style="border:none;"><div class="ou-team">Under {line}</div><div class="ou-vals">{u_odd}</div></div></div>')
'''

# Replace the old odds block with the new one
old_odds_block = '''    if match_odds and 'match_odds' in match_odds:
        st.html('<div class="section-title" style="margin-top:24px;">Live Bookmaker Odds (Bet365)</div>')
        o = match_odds['match_odds']
        oc1, oc2, oc3 = st.columns(3)
        for col, title, key in [(oc1, selected_fixture['home_name'], 'home'), (oc2, 'Draw', 'draw'), (oc3, selected_fixture['away_name'], 'away')]:
            open_odd = float(o[key]['opening'])
            cur_odd = float(o[key]['last_seen'])
            trend = "⬇️" if cur_odd < open_odd else ("⬆️" if cur_odd > open_odd else "➖")
            col.html(f'<div class="ou-card"><div class="ou-title">{title}</div><div style="font-size:24px;font-weight:700;color:#dde2ef;">{cur_odd:.2f}</div><div style="font-size:12px;color:#94a3b8;margin-top:4px;">Opened at {open_odd:.2f} {trend}</div></div>')'''

code = code.replace(old_odds_block, odds_insertion)

with open('dashboard.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated dashboard logic")
