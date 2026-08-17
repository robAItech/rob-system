<#
    register-autostart.ps1 — registracija/odstranitev avtonomnega zagona (Task Scheduler).

    Dvigne system (proxy :4010 + dashboard :8787) ob PRIJAVI Windows, v ozadju,
    brez terminala. UI (dashboard) je glavni vnos; Terminal/rescue = "rob dev".

    UPORABA (PowerShell v korenu projekta):
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -Remove
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -Query
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -OpenBrowser

    Tailscale: PREDGOPOJ za remote dostop iz drugih naprav (ne admin-samodejno):
      1) namesti Tailscale (tailscale.com/download)
      2) tailscale login
      3) tailscale up
      Ta skripta preveri, ampak ne namesca.
#>
[CmdletBinding()]
param(
    [switch]$Remove,       # odstrani RobSystem nalogo
    [switch]$Query,        # preveri obstoj naloge
    [switch]$OpenBrowser   # po registraciji odpri dashboard v brskalniku
)

$ErrorActionPreference = 'Stop'
$TaskName = 'RobSystem'
$Root = Split-Path -Parent $PSScriptRoot   # repo koren (scripts/ -> koren)
$Target  = Join-Path $PSScriptRoot 'autostart.bat'
$TaskCmd = 'cmd /c "' + $Target + '"'

# --- Tailscale predpogoj (porocilo) ---
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if ($ts) {
    Write-Host "  [TS] Tailscale name sken ($($ts.Source)). Remote dostop omogocen." -ForegroundColor Green
} else {
    Write-Host "  [TS] WARN: tailscale ni na PATH - remote dostop Z DRUGIH naprav NE deluje."
    Write-Host "        Namesti: https://tailscale.com/download ; potem 'tailscale up'."
    Write-Host "        Lokalno dashboard deluje (localhost:8787)." -ForegroundColor Yellow
}

if ($Query) {
    schtasks /query /tn $TaskName | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Naloga '$TaskName' obstaja (autostart)." -ForegroundColor Green
    } else {
        Write-Host "[--] Naloga '$TaskName' NE obstaja." -ForegroundColor Yellow
    }
    exit 0
}

if ($Remove) {
    schtasks /delete /tn $TaskName /f | Out-Null
    Write-Host "[OK] Naloga '$TaskName' odstranjena. System ostane (if running) - stop z 'rob dev'." -ForegroundColor Green
    exit 0
}

Write-Host "  Target: $TaskCmd"
schtasks /create /tn $TaskName /tr $TaskCmd /sc onlogon /rl LIMITED /f | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[NAP] Registracija ni uspela (exit $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Avtonomen zagon registriran: ob prijavi se dvigne proxy+dashboard v ozadju." -ForegroundColor Green
Write-Host "      Dashboard: http://localhost:8787   (vnos nalog prek UI)"
Write-Host "      Terminal/rescue: rob dev (v PowerShell) - za rocni nadzor/claude."
if ($OpenBrowser) {
    Start-Process "http://localhost:8787"
}
