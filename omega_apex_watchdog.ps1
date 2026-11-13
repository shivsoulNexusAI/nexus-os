# SINGLE-MASTER PRODUCTION GUARD: Terminal 2 (#278041169) ONLY
$mt5Procs = Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'"
if (-not ($mt5Procs | Where-Object { $_.ExecutablePath -match "MT5_Pending_278041169" })) {
    Start-Process -FilePath "C:\MT5_Pending_278041169\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Pending_278041169"
}
