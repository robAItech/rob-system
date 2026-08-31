# setup_worker_24h7.ps1 - pozeni ENKRAT na workerju (Windows PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\setup_worker_24h7.ps1
#
# Postavi 24/7 daemon brez admin-a (kot na masterju):
#   1) ustvari .rob_ai\watchdog_worker.ps1 (samozdravljenje),
#   2) HKCU Run -> zagon daemona ob logonu,
#   3) HKCU Run -> zagon watchdog-a ob logonu,
#   4) takoj pozeni watchdog.
#
# Skripta je ASCII (PowerShell 5.1 bere .ps1 kot ANSI).
# Repo koren = mapa nad scripts/.

$root = Split-Path -Parent $PSScriptRoot

# --- Python workerja: engine\python.exe (portabilen) ali sistemski ---------
$py = Join-Path $root "engine\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Host "ERROR: ni python-a (engine\python.exe ali python na PATH)."; exit 1 }
Write-Host "python: $py"

$daemon = Join-Path $root "core\daemon.py"
$wdPath = Join-Path $root ".rob_ai\watchdog_worker.ps1"
New-Item -ItemType Directory -Force (Join-Path $root ".rob_ai") | Out-Null

# --- Watchdog skripta (ASCII) ----------------------------------------------
$wdTemplate = @'
# watchdog_worker.ps1 - keeps the P1 worker daemon running (24/7). ASCII only.
$python = "@@PY@@"
$daemonPath = "@@DAEMON@@"
$workDir = "@@DIR@@"
while ($true) {
    $alive = $false
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop
        if ($procs | Where-Object { $_.CommandLine -like "*core\daemon.py*" }) { $alive = $true }
    } catch { }
    if (-not $alive) {
        Start-Process -FilePath $python -ArgumentList ('"{0}"' -f $daemonPath) -WorkingDirectory $workDir -WindowStyle Hidden
    }
    Start-Sleep -Seconds 60
}
'@
$wdContent = $wdTemplate.Replace("@@PY@@", $py).Replace("@@DAEMON@@", $daemon).Replace("@@DIR@@", $root)
Set-Content -Path $wdPath -Value $wdContent -Encoding ASCII
Write-Host "watchdog zapisan: $wdPath"

# --- HKCU Run (ob logonu) ---------------------------------------------------
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
Set-ItemProperty -Path $run -Name "RobWorkerDaemon" -Value ('"{0}" "{1}"' -f $py, $daemon)
Set-ItemProperty -Path $run -Name "RobWorkerWatchdog" -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $wdPath)
Write-Host "HKCU Run: RobWorkerDaemon + RobWorkerWatchdog nastavljena"

# --- Takoj pozeni watchdog (dvigne daemon, ce ne tece) ---------------------
Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $wdPath)
Write-Host "watchdog zagnan."
Write-Host "DONE. Worker daemon je zdaj 24/7 (ob logonu + samozdravljenje)."
