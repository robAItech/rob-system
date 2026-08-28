@echo off
REM alias: scripts/autostart.bat — target za AVTONOMEN zagon (HKCU Run autorun).
REM P1 daemon (core/daemon.py) je EDINI 24/7 master proces: idempotentno dvigne
REM proxy :4010 + dashboard :8787 (reuse dev_cli.cmd_serve), prazni agendo,
REM sam predlaga naloge, teče periodične jobe in piše heartbeat.
REM Vnos nalog skozi dashboard UI; Terminal/rescue pot = "rob dev" v PowerShell.
REM
REM Registracija se izvede prek register-autostart.ps1 (HKCU Run, brez admin):
REM   powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1
REM
REM Odpiranje dashboarda v brskalniku ob prijavi (neobvezno — odkomentiraj):
REM   start http://localhost:8787

REM Repo koren iz lokacije te skripte (scripts\ -> koren) — NE trdo-kodirana pot,
REM da avto-zagon deluje na kateremkoli računalniku/kopiji repozitorija.
cd /d "%~dp0..\"

REM Python razreši enako kot rob: venv (Windows: Scripts\), portabilen engine,
REM sicer `python` iz PATH. Daemon ob prijavi ne sme tiho pasti na napačen python.
if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else if exist "engine\python.exe" (
    set "PY=engine\python.exe"
) else if exist "engine\Scripts\python.exe" (
    set "PY=engine\Scripts\python.exe"
) else (
    set "PY=python"
)
%PY% core\daemon.py >> "%TEMP%\rob_daemon.log" 2>&1
