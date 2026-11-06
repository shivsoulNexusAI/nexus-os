$host.UI.RawUI.WindowTitle = "QUANT-NEXUS 24/7 SOVEREIGN DAEMON"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   QUANT NEXUS VPS SOVEREIGN OMEGA APEX MATRIX ACTIVE     " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

while ($true) {
    try {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting Sovereign Interactive Matrix..." -ForegroundColor Green
        Set-Location "C:\Quant-Nexus-Eng"
        python telegram_interactive.py
    }
    catch {
        Write-Host "Engine crashed with error: $_" -ForegroundColor Red
    }
    
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Process stopped. Auto-restarting in 5 seconds..." -ForegroundColor Magenta
    Start-Sleep -Seconds 5
}
