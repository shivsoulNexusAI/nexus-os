Write-Host "=== INITIALIZING 3-TERMINAL 24/7 TRADING ENVIRONMENT ===" -ForegroundColor Cyan

# 1. Start all 3 Isolated MT5 Portable Terminals
$terminals = @(
    @{ Name = "HFT (#278041671)";     Path = "C:\MT5_HFT_278041671\terminal64.exe";     Dir = "C:\MT5_HFT_278041671" },
    @{ Name = "Quant (#278017866)";   Path = "C:\MT5_Quant_278017866\terminal64.exe";   Dir = "C:\MT5_Quant_278017866" },
    @{ Name = "Pending (#278041169)"; Path = "C:\MT5_Pending_278041169\terminal64.exe"; Dir = "C:\MT5_Pending_278041169" }
)

foreach ($t in $terminals) {
    $running = Get-CimInstance Win32_Process -Filter "Name LIKE 'terminal64%'" | Where-Object { $_.CommandLine -match [regex]::Escape($t.Dir) }
    if (-not $running) {
        Write-Host "[+] Launching $($t.Name)..." -ForegroundColor Yellow
        Start-Process -FilePath $t.Path -ArgumentList "/portable" -WorkingDirectory $t.Dir -WindowStyle Minimized
        Start-Sleep -Seconds 3
    } else {
        Write-Host "[+] $($t.Name) already active." -ForegroundColor Green
    }
}

# 2. Start HFT Execution Engine
$hft = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%xauusd_ultra_hft.py%'"
if (-not $hft) {
    Write-Host "[+] Starting xauusd_ultra_hft.py..." -ForegroundColor Yellow
    Start-Process -FilePath "python.exe" `
        -ArgumentList "-u xauusd_ultra_hft.py" `
        -WorkingDirectory "C:\Quant-Straddle-Prod\sandbox_gold_lab" `
        -RedirectStandardOutput "C:\Quant-Straddle-Prod\sandbox_gold_lab\hft_execution.log" `
        -RedirectStandardError "C:\Quant-Straddle-Prod\sandbox_gold_lab\hft_execution_err.log" `
        -WindowStyle Hidden
}

# 3. Start Dev Guard Sentinel
$sentinel = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%dev_guard_sentinel.py%'"
if (-not $sentinel) {
    Write-Host "[+] Starting dev_guard_sentinel.py..." -ForegroundColor Yellow
    Start-Process -FilePath "python.exe" `
        -ArgumentList "-u dev_guard_sentinel.py" `
        -WorkingDirectory "C:\Quant-Nexus-Eng" `
        -WindowStyle Hidden
}

Write-Host "`n[✔] ALL 3 TERMINALS AND ENGINES ONLINE AND GUARDED." -ForegroundColor Green