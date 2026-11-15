# DUAL-MASTER PRODUCTION GUARD: Terminal 1 (#278017866) & Terminal 2 (#278041169)
$py  = "C:\Program Files\Python312\python.exe"
$eng = "C:\Quant-Nexus-Eng"

# 1. Ensure both MT5 Terminals are running in /portable mode
$mt5Procs = Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'"
if (-not ($mt5Procs | Where-Object { $_.ExecutablePath -match "MT5_Quant_278017866" })) {
    Start-Process -FilePath "C:\MT5_Quant_278017866\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Quant_278017866"
    Start-Sleep -Seconds 8
}
if (-not ($mt5Procs | Where-Object { $_.ExecutablePath -match "MT5_Pending_278041169" })) {
    Start-Process -FilePath "C:\MT5_Pending_278041169\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Pending_278041169"
    Start-Sleep -Seconds 8
}

# 2. Ensure Terminal 1 (quantum_institutional_pro.py) & Terminal 2 (nexus_multi_straddle_daemon.py) are running
$pyProcs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Select-Object -ExpandProperty CommandLine
if (-not ($pyProcs -match "quantum_institutional_pro\.py")) {
    Start-Process -FilePath $py -ArgumentList "-u `"$eng\quantum_institutional_pro.py`"" -WorkingDirectory $eng -WindowStyle Hidden
}
if (-not ($pyProcs -match "nexus_multi_straddle_daemon\.py")) {
    Start-Process -FilePath $py -ArgumentList "-u `"$eng\nexus_multi_straddle_daemon.py`"" -WorkingDirectory $eng -WindowStyle Hidden
}
if (-not ($pyProcs -match "telegram_telemetry_v441\.py")) {
    Start-Process -FilePath $py -ArgumentList "-u `"$eng\telegram_telemetry_v441.py`"" -WorkingDirectory $eng -WindowStyle Hidden
}
