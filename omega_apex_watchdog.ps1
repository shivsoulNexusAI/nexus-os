$py = "C:\Program Files\Python312\python.exe"
$procs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Select-Object -ExpandProperty CommandLine
if (-not ($procs -match "microstructure_sentinel\.py")) {
    Start-Process -FilePath $py -ArgumentList "C:\Quant-Nexus-Eng\microstructure_sentinel.py" -WorkingDirectory "C:\Quant-Nexus-Eng" -WindowStyle Hidden
}
if (-not ($procs -match "nexus_omega_apex_daemon\.py")) {
    Start-Process -FilePath $py -ArgumentList "C:\Quant-Nexus-Eng\nexus_omega_apex_daemon.py" -WorkingDirectory "C:\Quant-Nexus-Eng" -WindowStyle Hidden
}
