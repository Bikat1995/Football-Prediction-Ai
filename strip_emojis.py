with open('dashboard.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(', icon="ℹ️"', '')
code = code.replace('icon="ℹ️"', '')
code = code.replace('⚠ ', '')
code = code.replace('🔴 LIVE', 'LIVE')
code = code.replace('⬤ Live', 'Live')
code = code.replace('⚽  ', '')
code = code.replace('🎯  ', '')
code = code.replace('🔥  ', '')
code = code.replace('📐  ', '')
code = code.replace('↔  ', '')
code = code.replace('🔀  ', '')
code = code.replace('📊 ', '')
code = code.replace('📈 ', '')
code = code.replace('💰 ', '')

with open('dashboard.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Emojis removed")
