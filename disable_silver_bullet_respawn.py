from pathlib import Path

roots = [Path(r"C:\Quant-Nexus-Eng")]
if Path(r"C:\Quant-Nexus-OS").exists():
    roots.append(Path(r"C:\Quant-Nexus-OS"))

patched_files = 0
for root in roots:
    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        if fpath.suffix.lower() not in {".ps1", ".py", ".bat", ".cmd"}:
            continue
        # [DISABLED_V44] if ".bak" in fpath.name or fpath.name == "silver_bullet_daemon.py":
            continue

        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        # [DISABLED_V44] if "silver_bullet_daemon" not in text:
            continue

        bak = fpath.with_name(fpath.name + ".bak_no_sb")
        if not bak.exists():
            bak.write_bytes(fpath.read_bytes())

        new_lines = []
        changed = False
        for line in text.splitlines():
            stripped = line.lstrip()
            # [DISABLED_V44] if "silver_bullet_daemon" in line and not stripped.startswith(("#", "REM ", "::")):
                indent = line[: len(line) - len(stripped)]
                prefix = "REM " if fpath.suffix.lower() in {".bat", ".cmd"} else "# "
                new_lines.append(f"{indent}{prefix}[DISABLED_V44] {stripped}")
                changed = True
            else:
                new_lines.append(line)

        if changed:
            fpath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            patched_files += 1
            # [DISABLED_V44] print(f"[OK] Commented out silver_bullet_daemon launch in: {fpath}")

if patched_files == 0:
    print("[INFO] Zero active launch lines required patching.")
