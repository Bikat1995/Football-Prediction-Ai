import os

def patch_file():
    with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
        code = f.read()
        
    old_code = '''            data = r.json()
            _write_cache(ck, data)
            
            # --- AUTO-LOGGING FOR FUTURE TRAINING ---'''
            
    new_code = '''            data = r.json()
            _write_cache(ck, data)
            
            # --- AUTO-LOGGING FOR FUTURE TRAINING ---
            try:
                # Log literally everything fetched (stats, odds, matches) to a master data lake
                _log_everything_to_datalake(endpoint, params, data)
            except Exception:
                pass
'''
            
    if old_code in code:
        code = code.replace(old_code, new_code)
        
        # Add the _log_everything_to_datalake function
        logger_func = '''
def _log_everything_to_datalake(endpoint, params, data):
    """Appends ALL raw API responses into a master CSV data lake."""
    import csv
    import os
    import json
    from datetime import datetime
    
    csv_file = 'api_master_datalake.csv'
    file_exists = os.path.isfile(csv_file)
    
    # We dump the data dict into a json string so it fits in one CSV column
    row = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'endpoint': endpoint,
        'params': json.dumps(params),
        'raw_json_data': json.dumps(data)
    }
    
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'endpoint', 'params', 'raw_json_data'])
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
'''
        # Insert before `def _log_matches_to_csv`
        code = code.replace('def _log_matches_to_csv(matches_data):', logger_func + '\ndef _log_matches_to_csv(matches_data):')
        
        with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
            f.write(code)
        print("Patched live_data_fetcher.py to log EVERYTHING!")
    else:
        print("Failed to find replacement target!")

patch_file()
