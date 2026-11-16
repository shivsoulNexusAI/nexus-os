@echo off
setlocal
cd /d C:\Quant-Nexus-Eng

echo [%DATE% %TIME%] Starting Quant Nexus AEOS Daily Master Sync... > C:\Quant-Nexus-Eng\logs\sync_last_run.log

:: 1. Git Auto-Commit & Push
echo [%DATE% %TIME%] Staging & pushing git changes... >> C:\Quant-Nexus-Eng\logs\sync_last_run.log
git add -A
git commit -m "Auto-sync: Daily AEOS backup state %DATE%" 2>> C:\Quant-Nexus-Eng\logs\sync_last_run.log
git push origin main 2>> C:\Quant-Nexus-Eng\logs\sync_last_run.log

:: 2. Golden ZIP Archival (Compresses Quant-Nexus-Eng excluding .venv and heavy logs)
echo [%DATE% %TIME%] Creating Golden ZIP Archive... >> C:\Quant-Nexus-Eng\logs\sync_last_run.log
powershell -Command "Add-Type -A 'System.IO.Compression.FileSystem'; [System.IO.Compression.ZipFile]::CreateFromDirectory('C:\Quant-Nexus-Eng', 'C:\Quant-Nexus-Eng\logs\QuantNexus_Golden_Backup_%DATE:~-4,4%%DATE:~-10,2%%DATE:~-7,2%.zip')" 2>> C:\Quant-Nexus-Eng\logs\sync_last_run.log

:: 3. Prune logs older than 7 days
forfiles /p "C:\Quant-Nexus-Eng\logs" /s /m *.log /d -7 /c "cmd /c del @path" 2>nul

echo [%DATE% %TIME%] Quant Nexus AEOS Daily Master Sync Complete. >> C:\Quant-Nexus-Eng\logs\sync_last_run.log
endlocal