import os
import re

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace _get function to handle retries and rate limit
old_get = '''def _get(endpoint: str, params: dict, ttl: int = 1800):
    ck = _cache_key(endpoint, params)
    cached = _read_cache(ck, ttl)
    if cached:
        return cached

    try:
        r = requests.get(f"{BASE_URL}/{endpoint}",
                         headers=_headers(),
                         params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        _write_cache(ck, data)
        return data
    except requests.exceptions.HTTPError as e:
        print(f"[API] {endpoint} HTTP Error: {e.response.status_code} - {e.response.text[:100]}")
        try:
            return e.response.json()
        except:
            return {"errors": {"access": f"HTTP {e.response.status_code} Forbidden"}}
    except Exception as e:
        print(f"[API] {endpoint} failed: {e}")
        return {"errors": {"access": f"Connection Error: {str(e)[:50]}"}}'''

new_get = '''def _get(endpoint: str, params: dict, ttl: int = 1800, retries=2):
    ck = _cache_key(endpoint, params)
    cached = _read_cache(ck, ttl)
    if cached:
        return cached

    import time
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{BASE_URL}/{endpoint}",
                             headers=_headers(),
                             params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            _write_cache(ck, data)
            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < retries:
                # Rate limited, wait and retry
                time.sleep(1.0)
                continue
            
            print(f"[API] {endpoint} HTTP Error: {e.response.status_code} - {e.response.text[:100]}")
            try:
                return e.response.json()
            except:
                return {"errors": {"access": f"HTTP {e.response.status_code} Forbidden"}}
        except Exception as e:
            print(f"[API] {endpoint} failed: {e}")
            return {"errors": {"access": f"Connection Error: {str(e)[:50]}"}}
    return {}'''
code = code.replace(old_get, new_get)

# Increase sleep to 0.25 in get_upcoming_fixtures and get_fixtures_for_date
code = code.replace('time.sleep(0.1) # Respect 12 req/sec rate limit', 'time.sleep(0.25) # 4 req/sec is very safe')

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Patched _get with retries and increased sleep")
