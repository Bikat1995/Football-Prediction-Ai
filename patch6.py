import os

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Make upcoming fixtures filter out finished games again
old_upcoming_return = 'return all_items'
new_upcoming_return = 'return [f for f in all_items if f[\'status\'] in UPCOMING_STATUSES]'
code = code.replace(old_upcoming_return, new_upcoming_return)

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated live_data_fetcher to filter out finished games.")
