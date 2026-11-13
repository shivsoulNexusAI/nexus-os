# SINGLE-MASTER REBOOT RECOVERY: Terminal 2 (#278041169) V4.4 Turbo ONLY
$py  = "C:\Program Files\Python312\python.exe"
$eng = "C:\Quant-Nexus-Eng"

# 1. Clean >24h tick caches on Terminal 2 only
Get-ChildItem "C:\MT5_Pending_278041169\bases" -Recurse -Filter "*.tkc" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-24) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 2. Ensure Terminal 2 (#278041169) MT5 client is running in /portable mode
$procs = Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'"
if (-not ($procs | Where-Object { $_.ExecutablePath -match "MT5_Pending_278041169" })) {
    Start-Process -FilePath "C:\MT5_Pending_278041169\terminal64.exe" -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Pending_278041169"
    Start-Sleep -Seconds 10
}

# 3. Ensure V4.4 Turbo Master Daemon is running (protected by 127.0.0.1:47269 singleton lock)
$pyProcs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Select-Object -ExpandProperty CommandLine
if (-not ($pyProcs -match "nexus_multi_straddle_daemon\.py")) {
    Start-Process -FilePath $py -ArgumentList "-u `"$eng\nexus_multi_straddle_daemon.py`"" -WorkingDirectory $eng -WindowStyle Hidden
}
