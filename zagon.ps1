<#
    zagon.ps1 — EN UKAZ ZAGON: izoliran LiteLLM proxy + Command-Center + Claude
    ==================================================================
    Za razliko od dev.ps1 deluje NA LASTNEM portu 4010 (proxy) in se
    sploh ne ukvarja s portom 4000 (ki je rezerviran za uporabnikov
    obstoječi proxy v terminalu 1). Ta skripta NIKOLI ne ugasne ali
    upravlja procesa na 4000.

    Poleg proxyja dvigne tudi Command-Center dashboard (bun run
    src/server.ts) na :8787 — živa konzola z /api/health, /api/ledger,
    /api/runs in POST /api/run.

    UPORABA:
      .\zagon.ps1            # dvigne LiteLLM na 4010 + dashboard na 8787
                             # v ozadju, počaka na pripravo, postavi ANTHROPIC_*
                             # env in požene `claude`. Po izhodu claude-a sam
                             # ugasne proxy in dashboard. Port 4000 se ne dotakne.
      .\zagon.ps1 -ProxyOnly      # samo LiteLLM na 4010 v ospredju.
      .\zagon.ps1 -ClaudeOnly     # samo claude ob obstoječem proxyju na 4010.
      .\zagon.ps1 -DashboardOnly  # samo Command-Center (bun src/server.ts) v ospredju.
      .\zagon.ps1 -Init           # dry-run: preveri konfiguracijo, 4010 in 8787 (ne zažene nič).
#>

[CmdletBinding()]
param(
    [switch]$ProxyOnly,        # samo litellm proxy na 4010 v ospredju
    [switch]$ClaudeOnly,       # samo claude (obstoječi proxy na 4010)
    [switch]$DashboardOnly,    # samo Command-Center (bun src/server.ts)
    [switch]$Init              # skripta v dry-run (nikoli ne zažene)
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# 0. Lokacije — vse je izolirano (proxy 4010, dashboard 8787), NE 4000.
# ------------------------------------------------------------------
$Root       = $PSScriptRoot
$ConfigPath = Join-Path $Root 'bridges\litellm_config.yaml'
$ServerTs   = Join-Path $Root 'src\server.ts'
$EnvFile    = Join-Path $Root '.env'
$Port       = 4010            # namerni izoliran proxy port — NE 4000
$BaseUrl    = "http://127.0.0.1:$Port"
$DashPort   = 8787            # Command-Center privzeti port (iz src/server.ts)
$DashUrl    = "http://127.0.0.1:$DashPort"

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  [ROB] ZAGON - izoliran proxy :$Port + Claude (DeepSeek)"  -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  (Port 4000 je uporabnikov — ta skripta se ga NE dotika.)" -ForegroundColor DarkGray

# ------------------------------------------------------------------
# 1. Naloži .env v hashtable (ne spreminja globalnega env)
# ------------------------------------------------------------------
$envVars = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -le 0) { return }
        $envVars[$line.Substring(0, $eq).Trim()] = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
    }
}

$deepseek = $envVars['DEEPSEEK_API_KEY']
if ([string]::IsNullOrWhiteSpace($deepseek)) {
    Write-Host "`n[NAP] DEEPSEEK_API_KEY ni v .env (ni mogoče zagnati proxyja)" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------
# 2. Preberi master_key IZ configa (ne hardcode) — samo za avtentikacijo
#    clienta. Port vedno pride iz CLI (4010), ne iz configa.
# ------------------------------------------------------------------
$masterKey = 'sk-hermes-master-key'   # fallback, če ni v YAML
try {
    $py = @'
import sys, json, yaml
from pathlib import Path
data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
sec = (data or {}).get("general_settings") or {}
print(json.dumps({"master_key": sec.get("master_key")}))
'@
    $tmp = Join-Path $env:TEMP "rob_zagon_readyaml_$PID.py"
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    $json = python $tmp $ConfigPath
    $ok = $LASTEXITCODE -eq 0
    Remove-Item -Path $tmp -Force -ErrorAction SilentlyContinue
    if ($ok -and $json) {
        $parsed = $json | ConvertFrom-Json
        if ($parsed.master_key) { $masterKey = $parsed.master_key }
    }
} catch {
    Write-Warning "YAML read opozorilo: $($_.Exception.Message) (uporabim fallback)"
}

# ------------------------------------------------------------------
# 3. Pomožni: ali je proxy dosegljiv na $Port (liveliness + auth /v1/models)
# ------------------------------------------------------------------
function Test-ProxyHealth {
    try {
        # -UseBasicParsing je NUJEN v PS 5.1 (neinteraktivno/piped okolje):
        # brez njega Invoke-WebRequest naredi interni .NET crash ("Object
        # reference not set") namesto HTTP odgovora, zato bi health preverba
        # vedno vrnila false tudi ob delujočem proxyju.
        $r = Invoke-WebRequest -Uri "$BaseUrl/health/liveliness" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -ne 200) { return $false }
        $m = Invoke-WebRequest -Uri "$BaseUrl/v1/models" `
                 -Headers @{ 'Authorization' = "Bearer $masterKey" } `
                 -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return ($m.StatusCode -eq 200)
    } catch {
        return $false
    }
}

# Pomožni: ali je Command-Center dosegljiv na $DashPort (README tip /api/health).
function Test-DashboardHealth {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$DashPort/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

# Preverimo litellm, claude in bun na PATH (za vse načine).
$litellmCmd = Get-Command litellm -ErrorAction SilentlyContinue
$claudeCmd  = Get-Command claude  -ErrorAction SilentlyContinue
$bunCmd     = Get-Command bun     -ErrorAction SilentlyContinue

# ------------------------------------------------------------------
# 4. Init način (dry-run) — izrecno PREVERI 4010, ne 4000.
# ------------------------------------------------------------------
if ($Init) {
    Write-Host ""
    Write-Host "  Konfiguracija:" -ForegroundColor Yellow
    Write-Host "    config        : $ConfigPath"
    Write-Host "    DEEPSEEK      : nastavljen  [OK]"
    Write-Host "    master_key    : $masterKey"
    Write-Host "    proxy port (izoliran) : $Port"
    Write-Host "    dashboard     : $DashUrl  (port $DashPort)"

    $chkProxy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($chkProxy) {
        Write-Host ("    port $Port   : ZASEDEN (PID $($chkProxy.OwningProcess)) — nastavi prosto.") -ForegroundColor Red
    } else {
        Write-Host "    port $Port   : PROST  [OK]" -ForegroundColor Green
    }
    $chkDash = Get-NetTCPConnection -LocalPort $DashPort -State Listen -ErrorAction SilentlyContinue
    if ($chkDash) {
        Write-Host ("    port $DashPort   : ZASEDEN (PID $($chkDash.OwningProcess)) — nastavi prosto.") -ForegroundColor Red
    } else {
        Write-Host "    port $DashPort   : PROST  [OK]" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "  Okolje (PATH):" -ForegroundColor Yellow
    Write-Host ("    claude    : {0}" -f $(if ($claudeCmd) { "DOSEGLJIV [$($claudeCmd.Source)]" } else { "[MANJKA] — ni na PATH" }))
    Write-Host ("    litellm   : {0}" -f $(if ($litellmCmd) { "DOSEGLJIV [$($litellmCmd.Source)]" } else { "[MANJKA] — teči: python -m pip install litellm" }))
    Write-Host ("    bun       : {0}" -f $(if ($bunCmd) { "DOSEGLJIV [$($bunCmd.Source)]" } else { "[MANJKA] — teči: npm i -g bun" }))

    $poor = $false
    if (-not $litellmCmd) { Write-Host "[NAP] litellm manjka." -ForegroundColor Red; $poor = $true }
    if (-not $claudeCmd)  { Write-Host "[NAP] claude manjka."  -ForegroundColor Red; $poor = $true }
    if (-not $bunCmd)     { Write-Host "[NAP] bun manjka."     -ForegroundColor Red; $poor = $true }
    if ($poor) { Write-Host "[NAP] Odpravite manjkajoče elemente." -ForegroundColor Red; exit 1 }

    Write-Host ""
    Write-Host "  Zagon:  .\zagon.ps1     (vse v enem: proxy :4010 + dashboard :8787)" -ForegroundColor Cyan
    Write-Host "          .\zagon.ps1 -ProxyOnly" -ForegroundColor DarkGray
    Write-Host "          .\zagon.ps1 -ClaudeOnly" -ForegroundColor DarkGray
    Write-Host "          .\zagon.ps1 -DashboardOnly" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Varnost: Port 4000 ni vpleten in se ga skripta NE dotika." -ForegroundColor DarkGray
    exit 0
}

if (-not $litellmCmd) {
    Write-Host "`n[NAP] 'litellm' ni na PATH. Preveri:  python -m pip install litellm" -ForegroundColor Red
    exit 1
}
if (-not $claudeCmd) {
    Write-Host "`n[NAP] 'claude' ni na PATH. Dobro:  npm i -g @anthropic-ai/claude-code" -ForegroundColor Red
    exit 1
}
if (-not $bunCmd) {
    Write-Host "`n[NAP] 'bun' ni na PATH. Dobro:  npm i -g bun" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------
# 5. ProxyOnly način — litellm na $Port v ospredju
# ------------------------------------------------------------------
if ($ProxyOnly) {
    Write-Host "`n[PROXY] LiteLLM proxy v OSPREDJU na $BaseUrl (Ctrl+C za izhod)..." -ForegroundColor Cyan
    $env:DEEPSEEK_API_KEY = $deepseek
    $env:PYTHONIOENCODING = 'utf-8'   # banner na cp1250 terminalu bi zrušil zagon
    & $litellmCmd.Source --config $ConfigPath --port $Port
    exit $LASTEXITCODE
}

# ------------------------------------------------------------------
# 5b. DashboardOnly način — samo Command-Center (bun src/server.ts) v ospredju
# ------------------------------------------------------------------
if ($DashboardOnly) {
    Write-Host "`n[DASH] Command-Center v OSPREDJU na $DashUrl (Ctrl+C za izhod)..." -ForegroundColor Cyan
    Push-Location $Root
    try {
        & $bunCmd.Source run src/server.ts
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

# ------------------------------------------------------------------
# 6. ClaudeOnly način — le claude ob obstoječem proxyju na $Port
# ------------------------------------------------------------------
if ($ClaudeOnly) {
    if (-not (Test-ProxyHealth)) {
        Write-Host "`n[NAP] Proxy na $BaseUrl ni dosegljiv. Najprej:  .\zagon.ps1 -ProxyOnly" -ForegroundColor Red
        exit 1
    }
    Write-Host "`n[LINK] Uporabljam obstoječi proxy $BaseUrl" -ForegroundColor Cyan
    $env:ANTHROPIC_BASE_URL = $BaseUrl
    $env:ANTHROPIC_API_KEY  = $masterKey
    claude @args
    exit $LASTEXITCODE
}

# ------------------------------------------------------------------
# 7. GLAVNI NAČIN — vse v enem na $Port
# ------------------------------------------------------------------
$alreadyRunning = Test-ProxyHealth

if ($alreadyRunning) {
    Write-Host "`n[LINK] Proxy že teče na $BaseUrl - uporabljam obstoječega." -ForegroundColor DarkGray
} else {
    Write-Host "`n[PROXY] Zaganjam lasten izoliran LiteLLM proxy ($BaseUrl) v OZADJU..." -ForegroundColor Cyan

    $logOut = Join-Path $env:TEMP 'rob_zagon.out.log'
    $logErr = Join-Path $env:TEMP 'rob_zagon.err.log'

    $oldKey = $env:DEEPSEEK_API_KEY
    $oldEnc = $env:PYTHONIOENCODING
    $env:DEEPSEEK_API_KEY = $deepseek
    $env:PYTHONIOENCODING = 'utf-8'

    # PS 5.1 Start-Process -ArgumentList razbije poti s presledki, zato poslužimo
    # prek powershell -Command z enojnimi navedkami okoli vrednosti (enako kot
    # -ProxyOnly). PID, ki ga sledimo, je wrapper; za čiščenje se vežemo na
    # proces, ki dejansko POSLUŠA na $Port.
    $inner = "& '$($litellmCmd.Source)' --config '$ConfigPath' --port $Port"
    $wrapper = Start-Process -FilePath 'powershell' `
                    -ArgumentList @('-NoProfile', '-Command', $inner) `
                    -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    $env:DEEPSEEK_API_KEY = $oldKey
    $env:PYTHONIOENCODING = $oldEnc

    Write-Host "    wrapper PID=$($wrapper.Id)  log: $logErr" -ForegroundColor DarkGray

    # Počakaj na pripravo proxyja (do ~30s).
    Write-Host "[WAIT] Pripravljam proxy..." -ForegroundColor DarkGray
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-ProxyHealth) { $ok = $true; break }
        Start-Sleep -Milliseconds 1000
    }
    if (-not $ok) {
        Write-Host "`n[NAP] Proxy se ni zagnal v 30s na $Port. Zadnjih 30 vrstic loga:" -ForegroundColor Red
        if (Test-Path $logErr) { Get-Content $logErr -Tail 30 -ErrorAction SilentlyContinue }
        if ($wrapper -and -not $wrapper.HasExited) { Stop-Process -Id $wrapper.Id -Force -ErrorAction SilentlyContinue }
        # Varnostno: če je kje obtičal proces, ki POSLUŠA na $Port, ga odstranimo
        # (to je NAŠ proces — port tvorimo lastni, ne 4000).
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }
        exit 1
    }
}

Write-Host "[OK] Proxy dosegljiv na $BaseUrl" -ForegroundColor Green

# --- Command-Center dashboard (bun run src/server.ts) v OZADJU ---
$dashAlreadyRunning = Test-DashboardHealth
$dashProc = $null
if ($dashAlreadyRunning) {
    Write-Host "[LINK] Dashboard že teče na $DashUrl - uporabljam obstoječega." -ForegroundColor DarkGray
} else {
    Write-Host "`n[DASH] Zaganjam Command-Center ($DashUrl) v OZADJU (bun run src/server.ts)..." -ForegroundColor Cyan
    $dashLog = Join-Path $env:TEMP 'rob_zagon_dash.log'
    $dashErr = Join-Path $env:TEMP 'rob_zagon_dash.err.log'
    # bun run src/server.ts se kliče iz korena projekta (relativna pot).
    $dashProc = Start-Process -FilePath 'powershell' `
                    -ArgumentList @('-NoProfile', '-Command', "& '$($bunCmd.Source)' run src/server.ts") `
                    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput $dashLog -RedirectStandardError $dashErr
    Write-Host "    PID=$($dashProc.Id)  log: $dashErr" -ForegroundColor DarkGray
    # Počakaj (do ~15s) — dashboard naj gor odpre svoje endpoint-e.
    $dok = $false
    for ($i = 0; $i -lt 15; $i++) {
        if (Test-DashboardHealth) { $dok = $true; break }
        Start-Sleep -Milliseconds 1000
    }
    if ($dok) { Write-Host "[DASH] Command-Center dosegljiv na $DashUrl" -ForegroundColor Green }
    else      { Write-Host "[WARN] Dashboard se ni odzval v 15s — nadaljujem; log: $dashErr" -ForegroundColor Yellow }
}

# Postavi env za claude (podedovano v podproces).
$env:ANTHROPIC_BASE_URL = $BaseUrl
$env:ANTHROPIC_API_KEY  = $masterKey

Write-Host "`n[RUN] Zaganjam CLAUDE (Ctrl+C prekine samo claude)..." -ForegroundColor Magenta
& claude @args
$code = $LASTEXITCODE

# Cleanup: ugasni LASTEN proxy na $Port — nikoli ne 4000. Vežemo se na
# proces, ki POSLUŠA na $Port (to je naš litellm), saj je $wrapper le
# ovojni powershell.
if (-not $alreadyRunning) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "`n[CLEAN] Ugašam lasten LiteLLM proxy na :$Port (PID $($conn.OwningProcess))..." -ForegroundColor DarkGray
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    if ($wrapper -and -not $wrapper.HasExited) {
        Stop-Process -Id $wrapper.Id -Force -ErrorAction SilentlyContinue
    }
}

# Cleanup: ugasni dashboard, če smo ga sami zagnali (ne tistega, ki je že tekel).
if (-not $dashAlreadyRunning) {
    $dconn = Get-NetTCPConnection -LocalPort $DashPort -State Listen -ErrorAction SilentlyContinue
    if ($dconn) {
        Write-Host "[CLEAN] Ugašam dashboard na :$DashPort (PID $($dconn.OwningProcess))..." -ForegroundColor DarkGray
        Stop-Process -Id $dconn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    if ($dashProc -and -not $dashProc.HasExited) {
        Stop-Process -Id $dashProc.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "`n[END] Konec. (exit code: $code)" -ForegroundColor DarkGray
Write-Host "      Port 4000 (uporabnikov) ostaja nedotaknjen." -ForegroundColor DarkGray
exit $code
