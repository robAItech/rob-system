<#
    dev.ps1 — EN UKAZ ZAGON: LiteLLM proxy + Claude (prek DeepSeek)
    ==================================================================
    Vend je skaljen za Windows PowerShell 5.1 (default Windows 11).

    UPORABA:
      .\dev.ps1            # požene LiteLLM v ozadju, počaka na health,
                           # postavi ANTHROPIC_ENV in požene `claude`.
                           # Po izhodu claude-a samodejno ugasne litellm.

      .\dev.ps1 -ProxyOnly # samo LiteLLM v ospredju (za ročno uporabo).
      .\dev.ps1 -ClaudeOnly# samo claude proti obstoječemu proxyju.
      .\dev.ps1 -Init      # preveri konfiguracijo in izpiše primer (ne zažene nič).
#>

[CmdletBinding()]
param(
    [switch]$ProxyOnly,   # samo litellm proxy v ospredju
    [switch]$ClaudeOnly,  # samo claude (obstoječi proxy)
    [switch]$Init         # skripta v "dry-run" načinu (nikoli ne zažene)
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# 0. Lokacije
# ------------------------------------------------------------------
$Root      = $PSScriptRoot
$ConfigPath = Join-Path $Root 'bridges\litellm_config.yaml'
$EnvFile   = Join-Path $Root '.env'
$DefaultPort = 4000
$BaseUrl   = "http://127.0.0.1:$DefaultPort"

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  [ROB] ROB AI STUDIO - EN UKAZ ZAGON" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------
# 1. Naloži .env v hashtable (ne spreminja procesnega env globalno)
# ------------------------------------------------------------------
$envVars = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -le 0) { return }
        $name = $line.Substring(0, $eq).Trim()
        $val  = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        $envVars[$name] = $val
    }
}

$deepseek = $envVars['DEEPSEEK_API_KEY']
if ([string]::IsNullOrWhiteSpace($deepseek)) {
    Write-Host "`n[NAP] DEEPSEEK_API_KEY ni v .env (ni mogoče zagnati proxyja)" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------
# 2. Preberi master_key + morebiten port IZ YAML configa (ne hardcode)
#    Uporabimo majhen inline python z yaml, ker je pyyaml že v projektu.
# ------------------------------------------------------------------
$masterKey = 'sk-hermes-master-key'   # fallback, če vseeno ni v YAML
$port = $DefaultPort
try {
    $py = @'
import sys, json, yaml
from pathlib import Path
data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = {"master_key": None, "port": None}
sec = data.get("general_settings") or {}
out["master_key"] = sec.get("master_key")
port = sec.get("port")
if port is not None:
    out["port"] = int(port)
print(json.dumps(out))
'@
    $tmp = Join-Path $env:TEMP "rob_dev_readyaml_$PID.py"
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    $json = python $tmp $ConfigPath
    $ok = $LASTEXITCODE -eq 0
    Remove-Item -Path $tmp -Force -ErrorAction SilentlyContinue

    if ($ok -and $json) {
        $parsed = $json | ConvertFrom-Json
        if ($parsed.master_key) { $masterKey = $parsed.master_key }
        if ($parsed.port)       { $port = $parsed.port; $BaseUrl = "http://127.0.0.1:$port" }
    } else {
        Write-Warning "Ni bilo mogoče prebrati master_key iz configa; uporabljam fallback."
    }
} catch {
    Write-Warning "YAML read opozorilo: $($_.Exception.Message) (uporabim fallback)"
}

# ------------------------------------------------------------------
# 3. Init način (dry-run)
# ------------------------------------------------------------------
if ($Init) {
    Write-Host ""
    Write-Host "  Konfiguracija:" -ForegroundColor Yellow
    Write-Host "    Config      : $ConfigPath"
    Write-Host "    DEEPSEEK    : nastavljen  [OK]"
    Write-Host "    master_key  : $masterKey"
    Write-Host "    port        : $port"

    # Diagnostika okolja: ali sta litellm in claude dosegljiva na PATH.
    $chkLitellm = Get-Command litellm -ErrorAction SilentlyContinue
    $chkClaude  = Get-Command claude  -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "  Okolje (PATH):" -ForegroundColor Yellow
    Write-Host ("    claude    : {0}" -f $(if ($chkClaude) { "DOSEGLJIV [$($chkClaude.Source)]" } else { "[MANJKA] — ni na PATH" }))
    Write-Host ("    litellm   : {0}" -f $(if ($chkLitellm) { "DOSEGLJIV [$($chkLitellm.Source)]" } else { "[MANJKA] — teči: python -m pip install litellm" }))
    if (-not ($chkLitellm -and $chkClaude)) {
        Write-Host ""
        Write-Host "[NAP] Okolje ni v celoti pripravljeno — odpravite manjkajoče elemente." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host "  Zagon:  .\dev.ps1        (vse v enem)" -ForegroundColor Cyan
    Write-Host "          .\dev.ps1 -ProxyOnly" -ForegroundColor DarkGray
    exit 0
}

# Preveri litellm na PATH.
$litellmCmd = Get-Command litellm -ErrorAction SilentlyContinue
if (-not $litellmCmd) {
    Write-Host "`n[NAP] 'litellm' ni na PATH. Preveri:  python -m pip install litellm" -ForegroundColor Red
    exit 1
}

# Claude mora biti dosegljiv za vse načine, ki ga kličejo.
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudeCmd) {
    Write-Host "`n[NAP] 'claude' ni na PATH. Dobrič:  npm i -g @anthropic-ai/claude-code" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------
# 4. Pomožni: ali je proxy dosegljiv in se nanj lahko avtenticiramo.
#    Liveliness pove le, da proces teče; /v1/models preveri še, da so
#    modeli registrirani in da nas master_key sprejme — kar je tisto,
#    kar claude dejansko potrebuje.
# ------------------------------------------------------------------
function Test-ProxyHealth {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/health/liveliness" -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -ne 200) { return $false }
        $m = Invoke-WebRequest -Uri "$BaseUrl/v1/models" `
                 -Headers @{ 'Authorization' = "Bearer $masterKey" } `
                 -TimeoutSec 3 -ErrorAction Stop
        return ($m.StatusCode -eq 200)
    } catch {
        return $false
    }
}

# ------------------------------------------------------------------
# 5. ProxyOnly način — litellm v ospredju
# ------------------------------------------------------------------
if ($ProxyOnly) {
    Write-Host "`n[PROXY] LiteLLM proxy v OSPREDJU na $BaseUrl (Ctrl+C za izhod)..." -ForegroundColor Cyan
    $env:DEEPSEEK_API_KEY = $deepseek
    & $litellmCmd.Source --config $ConfigPath --port $port
    exit $LASTEXITCODE
}

# ------------------------------------------------------------------
# 6. ClaudeOnly način — le claude ob obstoječem proxyju
# ------------------------------------------------------------------
if ($ClaudeOnly) {
    if (-not (Test-ProxyHealth)) {
        Write-Host "`n[NAP] Proxy na $BaseUrl ni dosegljiv. Najprej: .\dev.ps1 -ProxyOnly" -ForegroundColor Red
        exit 1
    }
    Write-Host "`n[LINK] Uporabljam obstoječi proxy $BaseUrl" -ForegroundColor Cyan
    $env:ANTHROPIC_BASE_URL = $BaseUrl
    $env:ANTHROPIC_API_KEY  = $masterKey
    claude @args
    exit $LASTEXITCODE
}

# ------------------------------------------------------------------
# 7. GLAVNI NAČIN — vse v enem
# ------------------------------------------------------------------
$alreadyRunning = Test-ProxyHealth
$litellmProc = $null

if ($alreadyRunning) {
    Write-Host "`n[LINK] Proxy že teče na $BaseUrl - uporabljam obstoječega." -ForegroundColor DarkGray
} else {
    # Zaženi litellm v ozadju s pomočjo Start-Process (PS 5.1 varno),
    # ključ podamo preko okolja za podproces.
    Write-Host "`n[PROXY] Zaganjam LiteLLM proxy ($BaseUrl) v OZADJU..." -ForegroundColor Cyan
    $logOut = Join-Path $env:TEMP 'rob_litellm.out.log'
    $logErr = Join-Path $env:TEMP 'rob_litellm.err.log'

    $oldKey = $env:DEEPSEEK_API_KEY
    $env:DEEPSEEK_API_KEY = $deepseek
    $litellmProc = Start-Process -FilePath $litellmCmd.Source `
                    -ArgumentList @('--config', $ConfigPath, '--port', "$port") `
                    -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    $env:DEEPSEEK_API_KEY = $oldKey

    Write-Host "    PID=$($litellmProc.Id)  log: $logErr" -ForegroundColor DarkGray
}

# Počakaj na pripravo proxyja (do ~30s).
Write-Host "[WAIT] Pripravljam proxy..." -ForegroundColor DarkGray
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-ProxyHealth) { $ok = $true; break }
    Start-Sleep -Milliseconds 1000
}
if (-not $ok) {
    Write-Host "`n[NAP] Proxy se ni zagnal v 30s. Zadnjih 30 vrstic loga:" -ForegroundColor Red
    if (Test-Path $logErr) { Get-Content $logErr -Tail 30 -ErrorAction SilentlyContinue }
    if ($litellmProc -and -not $litellmProc.HasExited) { Stop-Process -Id $litellmProc.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

Write-Host "[OK] Proxy dosegljiv na $BaseUrl" -ForegroundColor Green

# Postavi env za claude (podedovano v podproces).
$env:ANTHROPIC_BASE_URL = $BaseUrl
$env:ANTHROPIC_API_KEY  = $masterKey

Write-Host "`n[RUN] Zaganjam CLAUDE (Ctrl+C prekine samo claude)..." -ForegroundColor Magenta
& claude @args
$code = $LASTEXITCODE

# Cleanup: ugasni litellm, če smo ga sami zagnali.
if ($litellmProc -and (-not $litellmProc.HasExited)) {
    Write-Host "`n[CLEAN] Ugašam LiteLLM proxy (PID $($litellmProc.Id))..." -ForegroundColor DarkGray
    Stop-Process -Id $litellmProc.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "`n[END] Konec. (exit code: $code)" -ForegroundColor DarkGray
exit $code
