from pathlib import Path

search_dirs = [Path(r"C:\Quant-Nexus-Eng"), Path(r"C:\Quant-Nexus-Prod")]
candidates = []

for d in search_dirs:
    if d.exists():
        candidates.extend(list(d.rglob("*tele*.log")))
        candidates.extend(list(d.rglob("*watcher*.log")))
        candidates.extend(list(d.rglob("*bot*.log")))

# De-duplicate
candidates = list(dict.fromkeys(candidates))

print("=" * 85)
print(f"TELEGRAM & BROADCAST LOG AUDIT ({len(candidates)} log files identified)")
print("=" * 85)

if not candidates:
    print("[-] No explicit '*tele*.log' files found. Searching for general stdout/err logs containing Telegram calls...")
    general_logs = list(Path(r"C:\Quant-Nexus-Eng").glob("*.log"))
    for gl in general_logs:
        try:
            lines = gl.read_text(encoding="utf-8", errors="ignore").splitlines()
            tele_lines = [l for l in lines if "telegram" in l.lower() or "editmessagetext" in l.lower() or "sendmessage" in l.lower()]
            if tele_lines:
                print(f"\n=== {gl.name} (Telegram Activity: {len(tele_lines)} lines) ===")
                for tl in tele_lines[-5:]:
                    print(f"  {tl}")
        except Exception:
            pass
else:
    for f in candidates:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            print(f"\n=== {f.name} ({f.parent.name}) ===")
            if lines:
                for l in lines[-5:]:
                    print(f"  {l}")
            else:
                print("  [File is empty]")
        except Exception as e:
            print(f"  [Read error: {e}]")

print("\n" + "=" * 85)