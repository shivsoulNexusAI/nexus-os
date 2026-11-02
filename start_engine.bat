@echo off
setlocal
cd /d C:\Quant-Nexus-Eng
set PYTHONUNBUFFERED=1

:: 1. Launch MT5 Terminal in portable mode if not running
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I /N "terminal64.exe">NUL
if "%ERRORLEVEL%"=="1" (
    start "" "C:\Program Files\MetaTrader 5\terminal64.exe" /portable
    timeout /t 5 /nobreak >nul
)

:: 2. Execute Quant-Nexus Master Engine with live stream redirection
"C:\Program Files\Python312\python.exe" -u "C:\Quant-Nexus-Eng\production_institutional.py" >> "C:\Quant-Nexus-Eng\production_institutional.log" 2>&1
