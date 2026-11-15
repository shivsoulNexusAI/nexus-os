Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "            QUANTNEXUS PRODUCTION FLEET STATUS             " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Daemon Process Map
$processes = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%quantum_institutional%' OR CommandLine LIKE '%gold_hft%' OR CommandLine LIKE '%pending_majors%' OR CommandLine LIKE '%circuit_breaker%' OR CommandLine LIKE '%rollover%' OR CommandLine LIKE '%command_center%' OR CommandLine LIKE '%session_pnl_digest%' OR CommandLine LIKE '%news_shock_guard%' OR CommandLine LIKE '%nexus_telemetry_db%' OR CommandLine LIKE '%engine_watchdog%'"
Write-Host "[*] Active Production Engines: $($processes.Count)/10 running" -ForegroundColor Green

# 2. Macro News Status
if (Test-Path "C:\Quant-Nexus-Eng\news_lockout.json") {
    $news = Get-Content "C:\Quant-Nexus-Eng\news_lockout.json" | ConvertFrom-Json
    $lockStr = if ($news.quarantine_active) { "LOCKED (High-Impact Event Active)" } else { "CLEAR (Trading Permitted)" }
    Write-Host "[*] Macro News Sentinel     : $lockStr" -ForegroundColor Yellow
}

# 3. Gold HFT Volatility Status
if (Test-Path "C:\Quant-Nexus-Eng\gold_volatility_state.json") {
    $gold = Get-Content "C:\Quant-Nexus-Eng\gold_volatility_state.json" | ConvertFrom-Json
    Write-Host "[*] T3 Gold Volatility Guard : $($gold.status) | M5 ATR: $($gold.atr_m5) | CHOP: $($gold.chop_index)" -ForegroundColor Yellow
}

# 4. Database Metrics
& "C:\Program Files\Python312\python.exe" "C:\Quant-Nexus-Eng\nexus_telemetry_db.py" --audit

Write-Host "============================================================" -ForegroundColor Cyan
