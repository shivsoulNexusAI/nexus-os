@echo off
cd /d "C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master"
set PYTHONUNBUFFERED=1
"C:\Program Files\Python312\python.exe" -u telemetry_dashboard.py >> c2_stdout.log 2>> c2_err.log
