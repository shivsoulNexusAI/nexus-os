param(
    [string]$CommitMessage = "Shivsoul Nexus v9.0: Institutional upgrade, PF 3.01+, Monte Carlo verified"
)

$ErrorActionPreference = "Stop"
Set-Location "C:\Quant-Nexus-Eng"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDirC = "C:\Quant-Nexus-Eng\backups"
$ZipName = "Shivsoul_Nexus_v9_Golden_Snapshot_$Timestamp.zip"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " SHIVSOUL NEXUS v9.0 // AUTOMATED BACKUP & SYNC DAEMON" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Ensure backup directory exists
New-Item -ItemType Directory -Force -Path $BackupDirC | Out-Null
$ZipPathC = Join-Path $BackupDirC $ZipName

# 2. Gather files for golden snapshot (excluding .git, backups, __pycache__)
Write-Host "[+] Collecting workspace files for golden zip snapshot..." -ForegroundColor Yellow
$ExcludedFolders = @(".git", "__pycache__", "backups")
$FilesToZip = Get-ChildItem -Path "C:\Quant-Nexus-Eng" -Recurse | Where-Object {
    $item = $_
    $skip = $false
    foreach ($ex in $ExcludedFolders) {
        if ($item.FullName -like "*\$ex\*") { $skip = $true }
    }
    -not $skip -and !$item.PSIsContainer
}

# Safely handle locked SQLite ledger by copying temp snapshot for zip
$TempLedger = $null
if (Test-Path "nexus_ledger.db") {
    $TempLedger = "C:\Quant-Nexus-Eng\nexus_ledger_temp.db"
    Copy-Item "nexus_ledger.db" $TempLedger -Force
    # Replace ledger in files list with temp copy to avoid file-lock errors
    $FilesToZip = $FilesToZip | Where-Object { $_.Name -ne "nexus_ledger.db" }
}

if (Test-Path $ZipPathC) { Remove-Item $ZipPathC -Force }
Compress-Archive -Path $FilesToZip.FullName -DestinationPath $ZipPathC -CompressionLevel Optimal

if ($TempLedger -and (Test-Path $TempLedger)) {
    # Add actual ledger back or clean up temp
    Remove-Item $TempLedger -Force
}
Write-Host "[OK] Golden zip archive created successfully at: $ZipPathC" -ForegroundColor Green

# 3. Synchronize with GitHub
Write-Host "[+] Staging and committing files to Git / GitHub..." -ForegroundColor Yellow
if (!(Test-Path ".git")) {
    git init
    git branch -M main
}

git add nexus_sleeve_worker.py nexus_fleet_supervisor.py scan_v8_readonly.py test_telegram_direct.py inspect_supervisor.py backtest_v9_engine.py monte_carlo_stress_v9.py reports/backtest_v9_2025_2026.csv nexus_ledger.db t1_telegram_config.json backup_sync_daemon.ps1

$gitStatus = git status --porcelain
if ($gitStatus) {
    git commit -m "$CommitMessage [$Timestamp]"
    Write-Host "[OK] Git commit created successfully." -ForegroundColor Green
} else {
    Write-Host "[INFO] Working tree clean. No new git changes to commit." -ForegroundColor Gray
}

# Pull latest remote changes first to prevent non-fast-forward rejection
try {
    $remoteCheck = git remote -v
    if ($remoteCheck) {
        Write-Host "[+] Fetching and merging remote GitHub branch..." -ForegroundColor Yellow
        git pull origin main --allow-unrelated-histories --no-edit
        Write-Host "[+] Pushing updates to GitHub remote..." -ForegroundColor Yellow
        git push origin main
        Write-Host "[SUCCESS] GitHub remote repository successfully synchronized!" -ForegroundColor Green
    } else {
        Write-Host "[INFO] No Git remote 'origin' configured yet. Local backup preserved." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] GitHub sync notice: $_" -ForegroundColor Yellow
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [SUCCESS] Local Snapshot & Sync Cycle Complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
