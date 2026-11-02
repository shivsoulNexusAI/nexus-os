path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "rb") as f:
    content = f.read()

# Strip UTF-8 BOM bytes (\xef\xbb\xbf) anywhere in the file
cleaned = content.replace(b"\xef\xbb\xbf", b"")

# Decode as UTF-8, strip any raw \ufeff unicode chars, and re-encode
text = cleaned.decode("utf-8", errors="ignore").replace("\ufeff", "")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Successfully stripped all U+FEFF BOM characters.")
