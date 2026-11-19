$ErrorActionPreference = "SilentlyContinue"
$mt5Exe = "C:\MT5_Sovereign_T4\terminal64.exe"
$pyExe  = "C:\Program Files\Python312\python.exe"
$pyBot  = "C:\Quant-Nexus-Eng\t4_sovereign_apex.py"
$logOut = "C:\Quant-Nexus-Eng\logs\t4_watchdog.log"
$token  = "8500432698:AAFLDz1nN_JeSMo2HBNx2gujV7tSlMfQGGg"
$chatId = "5279761713"

$restarted = @()

$mt5Proc = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $mt5Exe }
if (-not $mt5Proc) {
    Start-Process -FilePath $mt5Exe -ArgumentList "/portable" -WorkingDirectory "C:\MT5_Sovereign_T4"
    Start-Sleep -Seconds 8
    $restarted += "MT5_Sovereign_T4"
}

$pyProc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*t4_sovereign_apex.py*" }
if (-not $pyProc) {
    Start-Process -FilePath $pyExe -ArgumentList $pyBot -WorkingDirectory "C:\Quant-Nexus-Eng" -WindowStyle Hidden
    $restarted += "t4_sovereign_apex.py"
}

if ($restarted.Count -gt 0) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $joined = $restarted -join ", "
    Add-Content -Path $logOut -Value "$ts [WATCHDOG] Recovered: $joined"
    try {
        $msg = [uri]::EscapeDataString("🔄 <b>T4 WATCHDOG // AUTO-RECOVERY</b>`n• <b>Recovered:</b> <code>$joined</code>`n• <b>Host:</b> <code>AdmVps (#278071462)</code>")
        Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/sendMessage?chat_id=$chatId&parse_mode=HTML&text=$msg" -TimeoutSec 8 | Out-Null
    } catch {}
}
