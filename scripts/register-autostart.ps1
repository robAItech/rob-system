<#
    register-autostart.ps1 — registracija/odstranitev/preverba avtonomnega zagona (HKCU Run).

    Dvigne P1 daemon (core/daemon.py) ob PRIJAVI Windows, v ozadju, brez
    terminala. Daemon je edini 24/7 master proces: dvigne proxy :4010 +
    dashboard :8787 (idempotentno), prazni agendo, predlaga naloge, teče
    periodične jobe, piše heartbeat. UI (dashboard) je glavni vnos;
    Terminal/rescue = "rob dev".

    Uporablja HKCU Run (registry autorun) namesto Task Scheduler — ker
    `schtasks /sc onlogon` v tem okolju zahteva admin (Access denied), medtem ko
    pisanje v HKCU Run (CurrentUser) deluje BREZ admin pravic, za istega uporabnika.

    UPORABA (PowerShell v korenu projekta):
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1          # registrira
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -Remove  # odstrani
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -Query   # preveri
      powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1 -OpenBrowser

    Tailscale: PREDGOPOJ za remote dostop iz drugih naprav (ne admin-samodejno):
      1) namesti Tailscale (tailscale.com/download)
      2) tailscale login
      3) tailscale up
      Ta skripta preveri, ampak ne namesca.
#>
[CmdletBinding()]
param(
    [switch]$Remove,       # odstrani HKCU Run vnos
    [switch]$Query,        # preveri obstoj vnosa
    [switch]$OpenBrowser   # po registraciji odpri dashboard v brskalniku
)

$ErrorActionPreference = 'Stop'
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$Name = 'RobSystem'
$Root = Split-Path -Parent $PSScriptRoot    # repo koren (scripts/ -> koren)
$Target = Join-Path $PSScriptRoot 'autostart.bat'
# Vrednost HKCU Run: zapišemo kot cmd /c + citirano pot, da .bat izvede ob prijavi.
$Value = 'cmd /c "' + $Target + '"'

# --- Tailscale predpogoj (porocilo, ne blokira) ---
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if ($ts) {
    Write-Host "  [TS] Tailscale namescen ($($ts.Source)). Remote dostop omogocen." -ForegroundColor Green
} else {
    Write-Host "  [TS] WARN: tailscale ni na PATH - remote dostop Z DRUGIH naprav NE deluje."
    Write-Host "        Namesti: https://tailscale.com/download ; potem 'tailscale up'."
    Write-Host "        Lokalno dashboard deluje (localhost:8787)." -ForegroundColor Yellow
}

if ($Query) {
    $v = (Get-ItemProperty -Path $RunKey -Name $Name -ErrorAction SilentlyContinue).$Name
    if ($v) {
        Write-Host "[OK] Autostart '$Name' registriran: $v" -ForegroundColor Green
    } else {
        Write-Host "[--] Autostart '$Name' NI registriran." -ForegroundColor Yellow
    }
    exit 0
}

if ($Remove) {
    Remove-ItemProperty -Path $RunKey -Name $Name -ErrorAction SilentlyContinue
    Write-Host "[OK] Autostart '$Name' odstranjen. System ostane (if running) - stop z 'rob dev'." -ForegroundColor Green
    exit 0
}

# --- Registracija (HKCU Run, brez admin) ---
$vExisting = (Get-ItemProperty -Path $RunKey -Name $Name -ErrorAction SilentlyContinue).$Name
if ($vExisting) {
    Write-Host "[LINK] Autostart '$Name' že obstaja: $vExisting" -ForegroundColor DarkGray
} else {
    Set-ItemProperty -Path $RunKey -Name $Name -Value $Value
    Write-Host "[OK] Autostart '$Name' registriran (HKCU Run)." -ForegroundColor Green
}
Write-Host "      Ob naslednji prijavi se dvigne P1 daemon (proxy+dashboard+obdelava nalog)."
Write-Host "      Dashboard: http://localhost:8787   (vnos nalog prek UI)"
Write-Host "      Stanje daemona: rob daemon --status   |   Stop: rob daemon --stop"
Write-Host "      Terminal/rescue: rob dev (v PowerShell) - za rocni nadzor/claude."
Write-Host "      ODSTRANI: powershell -File scripts\register-autostart.ps1 -Remove"
if ($OpenBrowser) {
    Start-Process "http://localhost:8787"
}
