import sqlite3
import subprocess
import json
from pathlib import Path

DB_PATH = Path("nexus_ledger.db")
OUT_PS1 = Path("start_fleet_workers.ps1")


def get_live_worker_pids() -> dict[str, int]:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT sleeve, pid FROM worker_heartbeats ORDER BY sleeve ASC;").fetchall()
        return {str(r["sleeve"]): int(r["pid"]) for r in rows if r["pid"]}
    finally:
        conn.close()


def get_process_command_lines() -> dict[int, str]:
    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = res.stdout.strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return {int(item["ProcessId"]): str(item.get("CommandLine") or "") for item in data}


def strip_python_prefix(cmd_line: str) -> str:
    s = cmd_line.strip()
    if s.startswith('"'):
        end_quote = s.find('"', 1)
        if end_quote != -1:
            return s[end_quote + 1 :].strip()
    parts = s.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else s


def main() -> None:
    sleeve_pids = get_live_worker_pids()
    proc_cmds = get_process_command_lines()

    targets = []
    print("=== DISCOVERED LIVE WORKER COMMAND LINES ===")
    for sleeve in ["T1", "T2", "T3"]:
        pid = sleeve_pids.get(sleeve)
        full_cmd = proc_cmds.get(pid, "") if pid else ""
        if not full_cmd:
            # Fallback search across all python processes matching sleeve token
            for p_id, c_line in proc_cmds.items():
                if sleeve in c_line and "supervisor" not in c_line.lower():
                    pid = p_id
                    full_cmd = c_line
                    break

        args_only = strip_python_prefix(full_cmd) if full_cmd else f"nexus_worker.py --sleeve {sleeve}"
        print(f"• {sleeve} (PID {pid}): {args_only}")
        targets.append((sleeve, args_only))

    lines = [
        'param([switch]$ForceRestart)',
        '$WorkDir = "C:\\Quant-Nexus-Eng"',
        'Set-Location $WorkDir',
        '$PythonExe = (Get-Command python).Source',
        '',
        '$WorkerTargets = @(',
    ]
    for idx, (sleeve, args_only) in enumerate(targets):
        escaped_args = args_only.replace('"', '`"')
        comma = "," if idx < len(targets) - 1 else ""
        lines.append(f'    @{{ Name = "{sleeve}"; Args = "{escaped_args}" }}{comma}')
    lines.extend([
        ')',
        '',
        'if ($ForceRestart) {',
        '    $Running = Get-CimInstance Win32_Process -Filter "Name = \'python.exe\'" -ErrorAction SilentlyContinue',
        '    foreach ($w in $WorkerTargets) {',
        '        $Running | Where-Object { $_.CommandLine -like "*$($w.Args)*" } | ForEach-Object {',
        '            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue',
        '            Write-Host "[INFO] Stopped $($w.Name) PID $($_.ProcessId)"',
        '        }',
        '    }',
        '    Start-Sleep -Seconds 2',
        '}',
        '',
        '$CurrentProcs = Get-CimInstance Win32_Process -Filter "Name = \'python.exe\'" -ErrorAction SilentlyContinue',
        'foreach ($w in $WorkerTargets) {',
        '    $alreadyUp = $CurrentProcs | Where-Object { $_.CommandLine -like "*$($w.Args)*" }',
        '    if (-not $alreadyUp) {',
        '        $p = Start-Process -FilePath $PythonExe -ArgumentList $w.Args -WorkingDirectory $WorkDir -WindowStyle Hidden -PassThru',
        '        Write-Host "[STARTED] $($w.Name) -> PID $($p.Id) ($($w.Args))"',
        '        Start-Sleep -Seconds 5',
        '    } else {',
        '        Write-Host "[SKIPPED] $($w.Name) already running (PID $($alreadyUp.ProcessId))"',
        '    }',
        '}',
    ])

    OUT_PS1.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[SUCCESS] Synced {OUT_PS1} with exact live worker arguments.")


if __name__ == "__main__":
    main()
