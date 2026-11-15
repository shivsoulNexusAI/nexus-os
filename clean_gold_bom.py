from pathlib import Path

gold_file = Path(r"C:\Quant-Nexus-Eng\gold_hft_straddle_daemon.py")
raw_bytes = gold_file.read_bytes()

# Decode and purge all BOM characters (\ufeff)
text = raw_bytes.decode("utf-8-sig", errors="ignore")
text = text.replace("\ufeff", "")

# Ensure clean top header
lines = [line for line in text.splitlines() if not line.strip().startswith("# -*- coding: utf-8 -*-")]
clean_code = "# -*- coding: utf-8 -*-\n" + "\n".join(lines) + "\n"

# Write strictly without BOM
gold_file.write_bytes(clean_code.encode("utf-8"))
print("[+] Purged U+FEFF BOM from gold_hft_straddle_daemon.py successfully.")