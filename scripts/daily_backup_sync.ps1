$ErrorActionPreference = "Continue"
$LogFile = "C:\Quant-Nexus-Eng\logs\backup_sync.log"
$TgToken = if ($env:NEXUS_OS_TELEGRAM_TOKEN) { $env:NEXUS_OS_TELEGRAM_TOKEN } else { "9213146215:AAGNsCGLIvzrfjowmxQ32R8zbz8_YQsVTKE" }
$TgChat  = if ($env:NEXUS_OS_TELEGRAM_CHAT_ID) { $env:NEXUS_OS_TELEGRAM_CHAT_ID } else { "5279761713" }

function Write-SyncLog($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')] $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Send-SyncAlert($text) {
    try {
        Invoke-RestMethod -Uri "https://api.telegram.org/bot$TgToken/sendMessage" -Method Post -Body @{
            chat_id = $TgChat
            text    = $text
        } -TimeoutSec 10 | Out-Null
    } catch {}
}

Write-SyncLog "=== Starting QuantNexus v5.6 Automated Local Mirror, ZIP & Multi-Repo Git Sync ==="

# 1. Mirror clean codebase to C:\QuantNexus_Golden_Backups\Nexus_Mirror
$StageDir = "C:\QuantNexus_Golden_Backups\Nexus_Mirror"
New-Item -ItemType Directory -Force -Path $StageDir, "C:\Quant-Nexus-Backups" | Out-Null
robocopy "C:\Quant-Nexus-Eng" $StageDir /MIR /R:2 /W:2 /MT:8 /XD ".git" "__pycache__" ".venv" "venv" "logs" "prometheus_data" /XF "*.log" "*.tmp" /NFL /NDL /NJH /NJS | Out-Null

# 2. Compress verified ZIP snapshot into C:\Quant-Nexus-Backups
$Ts = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$ZipPath = "C:\Quant-Nexus-Backups\QuantNexus_Snapshot_$Ts.zip"
Add-Type -AssemblyName "System.IO.Compression.FileSystem"
[System.IO.Compression.ZipFile]::CreateFromDirectory($StageDir, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)

# Prune older ZIPs on C:\ (keep latest 2 to preserve disk space)
Get-ChildItem "C:\Quant-Nexus-Backups\QuantNexus_Snapshot_*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 2 |
    Remove-Item -Force -ErrorAction SilentlyContinue

if ((Test-Path $ZipPath) -and ((Get-Item $ZipPath).Length -gt 10KB)) {
    Write-SyncLog "Local Golden ZIP created: $ZipPath ($([math]::Round((Get-Item $ZipPath).Length / 1MB, 2)) MB)"
    # Optional mirror to local PC if RDP drive redirection (\\tsclient\E) is active
    if (Test-Path "\\tsclient\E\Nexus-OS-Backups") {
        Copy-Item -Path $ZipPath -Destination "\\tsclient\E\Nexus-OS-Backups\QuantNexus_v5.6_Full_Golden_$Ts.zip" -Force -ErrorAction SilentlyContinue
        Write-SyncLog "Synced Golden ZIP to local PC (\\tsclient\E\Nexus-OS-Backups)"
    }
} else {
    Write-SyncLog "ERROR: Local Golden ZIP creation failed or produced empty file!"
    Send-SyncAlert "⚠️ QUANTNEXUS BACKUP WARNING: Daily local ZIP creation failed on VPS."
}

# 3. Commit State & Push Across All 3 GitHub Repositories
Set-Location "C:\Quant-Nexus-Eng"
$Branch = (git rev-parse --abbrev-ref HEAD).Trim()
git add -A
if (git status --porcelain) {
    $CommitTs = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mmUTC")
    git commit -m "chore(auto-sync): daily QuantNexus v5.6 state, mirror & telemetry sync ($CommitTs)" | Out-Null
}

foreach ($r in @("origin", "nexus-os", "py-projects")) {
    git push $r $Branch 2>&1 | Out-Null
    if ($r -ne "origin") {
        git push $r "${Branch}:main" --force 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "ERROR: Git push failed for remote [$r]"
        Send-SyncAlert "⚠️ QUANTNEXUS GIT SYNC FAILED: Push to remote [$r] returned exit code $LASTEXITCODE."
    } else {
        Write-SyncLog "Git push succeeded for remote [$r] ($Branch)"
    }
}

Write-SyncLog "=== Daily Backup & Multi-Repo Sync Complete ==="
