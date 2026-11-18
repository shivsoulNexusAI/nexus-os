$ErrorActionPreference = "SilentlyContinue"
$workDir = "C:\Quant-Nexus-Eng"
$logFile = "$workDir\logs\watchdog.log"
$nowStr = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss UTC")

# Query SQLite for stale heartbeats (> 180s old) without nested here-strings
$pyCheck = "import sqlite3; from datetime import datetime, timezone; conn=sqlite3.connect(r'C:\Quant-Nexus-Eng\nexus_ledger.db', timeout=5.0); now=datetime.now(timezone.utc); rows=conn.execute('SELECT sleeve, pid, last_tick_utc FROM worker_heartbeats').fetchall(); conn.close(); seen=set(); [print(f'{s}:{p}') for s,p,t in rows if not seen.add(s) and (now - datetime.fromisoformat(t)).total_seconds() > 180]; [print(f'{r}:0') for r in ('T1','T2','T3') if r not in seen]"
$staleSleeves = python -c $pyCheck

$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*nexus_sleeve_worker.py*" }

foreach ($s in @("T1", "T2", "T3")) {
    $matched = $procs | Where-Object { $_.CommandLine -match "nexus_sleeve_worker\.py\s+$s\b" }
    $isStale = $staleSleeves | Where-Object { $_ -like "$s`:*" }

    if (-not $matched -or $isStale) {
        foreach ($m in $matched) {
            Stop-Process -Id $m.ProcessId -Force
            Add-Content -Path $logFile -Value "[$nowStr] [WATCHDOG] Killed hung/stale $s worker PID $($m.ProcessId)"
        }
        Start-Process python -ArgumentList "$workDir\nexus_sleeve_worker.py $s" -WorkingDirectory $workDir -WindowStyle Hidden
        Add-Content -Path $logFile -Value "[$nowStr] [WATCHDOG] Relaunched $s worker"
    }
}

$beProc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*breakeven_engine.py*" }
if (-not $beProc) {
    Start-Process python -ArgumentList "$workDir\breakeven_engine.py" -WorkingDirectory $workDir -WindowStyle Hidden
    Add-Content -Path $logFile -Value "[$nowStr] [WATCHDOG] Relaunched breakeven_engine.py"
}
