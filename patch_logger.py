import os
import csv

def patch_file():
    with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
        code = f.read()
        
    old_code = '''            data = r.json()
            _write_cache(ck, data)
            return data'''
            
    new_code = '''            data = r.json()
            _write_cache(ck, data)
            
            # --- AUTO-LOGGING FOR FUTURE TRAINING ---
            try:
                if 'matches' in endpoint and 'data' in data:
                    _log_matches_to_csv(data['data'])
            except Exception as e:
                pass
                
            return data'''
            
    if old_code in code:
        code = code.replace(old_code, new_code)
        
        # Add the _log_matches_to_csv function
        logger_func = '''
def _log_matches_to_csv(matches_data):
    """Appends finished match data to a CSV for future model training."""
    import csv
    import os
    if not isinstance(matches_data, list):
        return
        
    csv_file = 'collected_training_data.csv'
    file_exists = os.path.isfile(csv_file)
    
    headers = ['Match_ID', 'Date', 'Competition_ID', 'Home_ID', 'Home_Name', 'Away_ID', 'Away_Name', 
               'Home_Goals', 'Away_Goals', 'Winner']
               
    rows_to_write = []
    
    # We may have already written some matches, read IDs to prevent duplicates
    existing_ids = set()
    if file_exists:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None) # skip header
                for row in reader:
                    if row:
                        existing_ids.add(row[0])
        except Exception:
            pass
            
    for m in matches_data:
        # Only log finished matches with a valid score object
        if not isinstance(m, dict) or m.get('status') not in FINISHED_STATUSES:
            continue
            
        m_id = m.get('id')
        if not m_id or m_id in existing_ids:
            continue
            
        score = m.get('score', {})
        if score:
            h_g = score.get('home')
            a_g = score.get('away')
            if h_g is not None and a_g is not None:
                rows_to_write.append({
                    'Match_ID': m_id,
                    'Date': m.get('utc_date', '')[:10],
                    'Competition_ID': m.get('competition_id', ''),
                    'Home_ID': m.get('home_team', {}).get('id', ''),
                    'Home_Name': m.get('home_team', {}).get('name', ''),
                    'Away_ID': m.get('away_team', {}).get('id', ''),
                    'Away_Name': m.get('away_team', {}).get('name', ''),
                    'Home_Goals': h_g,
                    'Away_Goals': a_g,
                    'Winner': score.get('winner', '')
                })
                existing_ids.add(m_id)
                
    if rows_to_write:
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows_to_write)
'''
        # Insert before `def _get`
        code = code.replace('def _get(endpoint: str, params: dict, ttl: int = 1800, retries=2):', logger_func + '\ndef _get(endpoint: str, params: dict, ttl: int = 1800, retries=2):')
        
        with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
            f.write(code)
        print("Patched live_data_fetcher.py successfully!")
    else:
        print("Failed to find replacement target!")

patch_file()
