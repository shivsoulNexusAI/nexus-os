$py = "C:\Program Files\Python312\python.exe"
$heartbeatFile = "C:\Quant-Nexus-Eng\daemon_heartbeat.json"
$logFile = "C:\Quant-Nexus-Eng\watchdog.log"
$maxStaleSeconds = 25

function Log-Msg($msg) {
    $t = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    "$t [WATCHDOG] $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "$t [WATCHDOG] $msg"
}

Log-Msg "Starting QuantNexus Heartbeat Watchdog..."

while ($true) {
    Start-Sleep -Seconds 10
    $proc = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%silver_bullet_daemon.py%'"
    if (-not $proc) {
        Log-Msg "Daemon not running. Restarting..."
        Start-Process -FilePath $py -ArgumentList "-u silver_bullet_daemon.py --live" -WorkingDirectory "C:\Quant-Nexus-Eng" -RedirectStandardOutput "C:\Quant-Nexus-Eng\silver_bullet_daemon.log" -RedirectStandardError "C:\Quant-Nexus-Eng\silver_bullet_daemon_err.log" -WindowStyle Hidden
        continue
    }

    if (Test-Path $heartbeatFile) {
        try {
            $content = Get-Content $heartbeatFile -Raw | ConvertFrom-Json
            $lastPulse = [DateTime]::Parse($content.timestamp).ToUniversalTime()
            $diff = ([DateTime]::UtcNow - $lastPulse).TotalSeconds
            if ($diff -gt $maxStaleSeconds) {
                Log-Msg "HEARTBEAT FROZEN ($([math]::Round($diff,1))s). Recycling PID $($proc.ProcessId)..."
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                Start-Process -FilePath $py -ArgumentList "-u silver_bullet_daemon.py --live" -WorkingDirectory "C:\Quant-Nexus-Eng" -RedirectStandardOutput "C:\Quant-Nexus-Eng\silver_bullet_daemon.log" -RedirectStandardError "C:\Quant-Nexus-Eng\silver_bullet_daemon_err.log" -WindowStyle Hidden
                Log-Msg "Daemon restarted."
            }
        } catch {}
    }
}