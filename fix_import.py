with open('mss_matrix.py', 'r', encoding='utf-8') as f:
    text = f.read()

if 'import datetime' not in text:
    text = 'import datetime\n' + text

with open('mss_matrix.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('[+] Injected import datetime into mss_matrix.py.')
