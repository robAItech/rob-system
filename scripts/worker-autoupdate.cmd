@echo off
REM Worker self-update (git-model): `rob fleet pull` = git pull --rebase + uvoz
REM masterjevega fleet/backup.json (spomin + agenda) v enem. Uporabi jo Windows
REM Task Scheduler vsakih N minut, da se worker posodablja tudi, ko daemon ne
REM teče. Zagnana je iz korena repa (cd /d "%~dp0..").
cd /d "%~dp0.."
if exist "engine\python.exe" (
    "engine\python.exe" core\fleet.py pull
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" core\fleet.py pull
) else (
    python core\fleet.py pull
)
