$WorkDir = "C:\Quant-Nexus-Eng"
Set-Location $WorkDir

# Prevent duplicate supervisor instances (avoids Telegram getUpdates 409 Conflict)
$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*nexus_fleet_supervisor.py*" }

if ($existing) {
    exit 0
}

$PythonExe = (Get-Command python).Source
& $PythonExe "$WorkDir\nexus_fleet_supervisor.py"
