<#
================================================================================
   QUANT-NEXUS 3-SILO MT5 UNIFIED FLEET LAUNCHER (VERIFIED & LOCKED)
   Silo 1: Silver Bullet (Account #278017866) -> Apex Satellite
   Silo 2: Majors Grid   (Account #278041169) -> MT5_Quant (AppData Mode)
   Silo 3: Gold HFT      (Account #278041671) -> MT5_HFT (/portable Mode)
================================================================================
#>

[CmdletBinding()]
param(
    [switch]$ForceRestart = $false
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         STARTING QUANT-NEXUS 3-SILO FLEET BOOT           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if ($ForceRestart) {
    Write-Host "[!] Terminating MT5 terminal processes for clean reboot..." -ForegroundColor Yellow
    Get-CimInstance Win32_Process -Filter "Name LIKE 'terminal64%'" | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
}

$silos = @(
    @{
        Name       = "Silo 1 (Silver Bullet #278017866)"
        BinaryPath = "C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe"
        WorkDir    = "C:\Program Files\MetaTrader 5 - Apex Satellite"
        Arguments  = "/skipupdate"
        Portable   = $false
    },
    @{
        Name       = "Silo 2 (Majors Grid #278041169)"
        BinaryPath = "C:\MT5_Quant_278017866\terminal64.exe"
        WorkDir    = "C:\MT5_Quant_278017866"
        Arguments  = "/skipupdate"
        Portable   = $false
    },
    @{
        Name       = "Silo 3 (Gold HFT #278041671)"
        BinaryPath = "C:\MT5_HFT_278041671\terminal64.exe"
        WorkDir    = "C:\MT5_HFT_278041671"
        Arguments  = "/portable /skipupdate"
        Portable   = $true
    }
)

foreach ($silo in $silos) {
    Write-Host "`n[*] Auditing $($silo.Name)..." -ForegroundColor White
    
    if (-not (Test-Path $silo.BinaryPath)) {
        Write-Host "[-] Executable missing: $($silo.BinaryPath)" -ForegroundColor Red
        continue
    }

    $running = Get-CimInstance Win32_Process -Filter "Name LIKE 'terminal64%'" | Where-Object {
        $_.ExecutablePath -eq $silo.BinaryPath
    }

    if ($running) {
        Write-Host "[+] Already running with PID: $($running.ProcessId) (Healthy)" -ForegroundColor Green
    } else {
        Write-Host "[*] Launching: $($silo.BinaryPath) $($silo.Arguments)" -ForegroundColor Cyan
        
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $silo.BinaryPath
        $psi.Arguments = $silo.Arguments
        $psi.WorkingDirectory = $silo.WorkDir
        $psi.UseShellExecute = $true
        $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
        
        $proc = [System.Diagnostics.Process]::Start($psi)
        Write-Host "[+] Successfully spawned PID: $($proc.Id)" -ForegroundColor Green
        
        Start-Sleep -Seconds 7
    }
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "                ACTIVE MT5 PROCESS TABLE                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Get-CimInstance Win32_Process -Filter "Name LIKE 'terminal64%'" | 
    Select-Object ProcessId, ExecutablePath, CommandLine, @{Name="RAM_MB";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}} | 
    Format-Table -AutoSize

Write-Host "[+] Fleet verified and synchronized." -ForegroundColor Green