import os

with open('live_data_fetcher.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_return = 'return [f for f in all_items if f[\'status\'] in UPCOMING_STATUSES]'
new_return = 'return all_items'
if old_return in code:
    code = code.replace(old_return, new_return)
else:
    print("Could not find the return statement to replace.")

with open('live_data_fetcher.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Removed status filter for upcoming fixtures")
