# DUAL-MASTER REBOOT RECOVERY: Terminal 1 (#278017866) & Terminal 2 (#278041169)
$py  = "C:\Program Files\Python312\python.exe"
$eng = "C:\Quant-Nexus-Eng"

# 1. Clean >24h tick caches on Terminal 1 and Terminal 2
Get-ChildItem "C:\MT5_Quant_278017866\bases", "C:\MT5_Pending_278041169\bases" -Recurse -Filter "*.tkc" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-24) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 2. Ensure Terminal 1 & Terminal 2 MT5 clients are running in /portable mode
$procs = Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'"
if (-not ($procs | Where-Object { $_.ExecutablePath -match "MT5_Quant_278017866" })) {
    Start-Process -FilePath "C:\MT5_Quant_278017866\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Quant_278017866"
    Start-Sleep -Seconds 10
}
if (-not ($procs | Where-Object { $_.ExecutablePath -match "MT5_Pending_278041169" })) {
    Start-Process -FilePath "C:\MT5_Pending_278041169\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Pending_278041169"
    Start-Sleep -Seconds 10
}

# 3. Ensure T1 60s Autonomous Matrix & T2 V4.4.1 Master Daemons are running
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
if (-not ($pyProcs -match "microstructure_sentinel\.py")) {
    Start-Process -FilePath $py -ArgumentList "-u `"$eng\microstructure_sentinel.py`"" -WorkingDirectory $eng -WindowStyle Hidden
}
