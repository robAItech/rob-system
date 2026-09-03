@echo off
REM Worker daemon — poganja naloge iz master agende (fleet, živi kanal :8789).
REM Vloga/naslov/token se berejo iz LOKALNEGA .env (NI commitano):
REM   ROB_FLEET_ROLE=worker
REM   ROB_FLEET_MASTER_URL=http://<master-ip>:8789   (LAN ali Tailscale)
REM   ROB_FLEET_TOKEN=<isti kot na masterju>
REM Zaženi ročno (daemon teče naprej) ali prek Windows Task Scheduler (ONLOGON).
cd /d "%~dp0.."
if exist "engine\python.exe" (
    "engine\python.exe" core\daemon.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" core\daemon.py
) else (
    python core\daemon.py
)
