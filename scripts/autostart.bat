@echo off
REM alias: scripts/autostart.bat — Task Scheduler target za AVTONOMEN zagon.
REM Dvigne proxy :4010 + dashboard :8787 v ozadju (brez claude-a), idempotentno.
REM Vnos nalog skozi dashboard UI; Terminal/rescue pot = "rob dev" v PowerShell.
REM
REM Uporaba (PowerShell, registracija prek register-autostart.ps1):
REM   schtasks /create /tn RobSystem /tr "cmd /c C:\Rob system\scripts\autostart.bat" /sc onlogon /f
REM
REM Odpiranje dashboarda v brskalniku ob prijavi (neobvezno — odkomentiraj):
REM   start http://localhost:8787

cd /d "C:\Rob system"
python core\dev_cli.py --serve >> "%TEMP%\rob_serve.log" 2>&1
