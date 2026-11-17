$WorkDir = "C:\Quant-Nexus-Eng"
Set-Location $WorkDir

$ReportsDir = Join-Path $WorkDir "reports"
if (-not (Test-Path $ReportsDir)) {
    New-Item -ItemType Directory -Path $ReportsDir | Out-Null
}

$LogFile = Join-Path $ReportsDir "daily_audit.log"
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss UTC")
Add-Content -Path $LogFile -Value "=== DAILY CLOSE AUDIT RUN: $Timestamp ==="

$PythonExe = (Get-Command python).Source
& $PythonExe "$WorkDir\dispatch_daily_audit.py" *>> $LogFile
