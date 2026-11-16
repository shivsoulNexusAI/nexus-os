$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoPath   = "C:\Quant-Nexus-Eng"
$BackupDir  = "C:\Quant-Nexus-Backups"
$LogFile    = "$RepoPath\logs\backup_sync.log"
$Branch     = "omega-apex-elite-v45-20261112"
$Timestamp  = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmUTC")

$TgToken    = if ($env:NEXUS_OS_TELEGRAM_TOKEN) { $env:NEXUS_OS_TELEGRAM_TOKEN } else { "9213146215:AAGNsCGLIvzrfjowmxQ32R8zbz8_YQsVTKE" }
$TgChatId   = if ($env:NEXUS_OS_TELEGRAM_CHAT_ID) { $env:NEXUS_OS_TELEGRAM_CHAT_ID } else { "5279761713" }

function Write-Log {
    param([string]$Message)
    $entry = "[$( (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss UTC') )] $Message"
    Add-Content -Path $LogFile -Value $entry
    Write-Host $entry
}

function Send-TelegramAlert {
    param([string]$AlertText)
    try {
        $Uri = "https://api.telegram.org/bot$TgToken/sendMessage"
        $Payload = @{
            chat_id = $TgChatId
            text    = $AlertText
        } | ConvertTo-Json -Compress

        Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" -Body $Payload -TimeoutSec 10 | Out-Null
        Write-Log "INFO: Telegram failure notification delivered to Chat ID $TgChatId."
    } catch {
        Write-Log "WARN: Failed to dispatch Telegram alert: $_"
    }
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
New-Item -ItemType Directory -Force -Path "$RepoPath\logs" | Out-Null

Write-Log "=== Starting QuantNexus Daily Backup & Git Sync ==="

# 1. Create Compressed Local Snapshot (Excluding .git, logs, caches, and virtualenvs)
$StagingDir = "$env:TEMP\QuantNexus_Stage_$Timestamp"
try {
    $ZipPath = "$BackupDir\QuantNexus_Snapshot_$Timestamp.zip"
    New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

    # Mirror clean project tree excluding locked logs and heavy git/cache dirs
    & robocopy $RepoPath $StagingDir /E /XD ".git" "logs" "__pycache__" ".venv" "venv" /XF "*.log" /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

    Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal -Force
    Write-Log "SUCCESS: Local archive saved to $ZipPath"

    # Enforce 14-day backup retention
    Get-ChildItem -Path $BackupDir -Filter "QuantNexus_Snapshot_*.zip" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
        Remove-Item -Force
} catch {
    $errMsg = "ERROR (Archive): $_"
    Write-Log $errMsg
    Send-TelegramAlert -AlertText "🚨 QUANTNEXUS BACKUP FAILURE ($Timestamp)`nStage: Local ZIP Snapshot`nError: $_"
} finally {
    if (Test-Path $StagingDir) { Remove-Item -Path $StagingDir -Recurse -Force -ErrorAction SilentlyContinue }
}

# 2. Git Stage, Commit & Push
try {
    Set-Location $RepoPath
    
    git add -u
    git add audit_reports/ docker-compose.yml prometheus.yml scripts/ 2>$null

    $Changes = git status --porcelain
    if ($Changes) {
        git commit -m "chore(auto-sync): daily state snapshot & audit backup ($Timestamp)"
        if ($LASTEXITCODE -ne 0) { throw "git commit exited with code $LASTEXITCODE" }
        Write-Log "SUCCESS: Committed changes to $Branch."
    } else {
        Write-Log "INFO: Working tree clean; no new changes to commit."
    }

    git pull --rebase origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git pull --rebase exited with code $LASTEXITCODE" }

    git push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push exited with code $LASTEXITCODE" }

    Write-Log "SUCCESS: Pushed $Branch to origin."
} catch {
    $errMsg = "ERROR (Git Sync): $_"
    Write-Log $errMsg
    Send-TelegramAlert -AlertText "🚨 QUANTNEXUS GIT SYNC FAILURE ($Timestamp)`nBranch: $Branch`nError: $_"
}

Write-Log "=== Completed QuantNexus Daily Backup & Git Sync ==="
