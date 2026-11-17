param([switch]$ForceRestart)
$WorkDir = "C:\Quant-Nexus-Eng"
Set-Location $WorkDir
$PythonExe = (Get-Command python).Source

$WorkerTargets = @(
    @{ Name = "T1"; Args = "nexus_sleeve_worker.py T1" },
    @{ Name = "T2"; Args = "nexus_sleeve_worker.py T2" },
    @{ Name = "T3"; Args = "nexus_sleeve_worker.py T3" }
)

if ($ForceRestart) {
    $Running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue
    foreach ($w in $WorkerTargets) {
        $Running | Where-Object { $_.CommandLine -like "*$($w.Args)*" } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[INFO] Stopped $($w.Name) PID $($_.ProcessId)"
        }
    }
    Start-Sleep -Seconds 2
}

$CurrentProcs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue
foreach ($w in $WorkerTargets) {
    $alreadyUp = $CurrentProcs | Where-Object { $_.CommandLine -like "*$($w.Args)*" }
    if (-not $alreadyUp) {
        $p = Start-Process -FilePath $PythonExe -ArgumentList $w.Args -WorkingDirectory $WorkDir -WindowStyle Hidden -PassThru
        Write-Host "[STARTED] $($w.Name) -> PID $($p.Id) ($($w.Args))"
        Start-Sleep -Seconds 5
    } else {
        Write-Host "[SKIPPED] $($w.Name) already running (PID $($alreadyUp.ProcessId))"
    }
}
