$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -like "python*" } | Select-Object -ExpandProperty CommandLine
$pyExe = (Get-Command python).Source

if (-not ($procs -match "breakeven_engine\.py")) {
    Start-Process $pyExe -ArgumentList "C:\Quant-Nexus-Eng\breakeven_engine.py" -WorkingDirectory "C:\Quant-Nexus-Eng" -WindowStyle Hidden
}

foreach ($s in @("T1", "T2", "T3")) {
    if (-not ($procs -match "nexus_sleeve_worker\.py\s+$s\b")) {
        Start-Process $pyExe -ArgumentList "C:\Quant-Nexus-Eng\nexus_sleeve_worker.py $s" -WorkingDirectory "C:\Quant-Nexus-Eng" -WindowStyle Hidden
    }
}
