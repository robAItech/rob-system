@echo off
REM alias: scripts/autostart.bat — target za AVTONOMEN zagon (HKCU Run autorun).
REM Dvigne proxy :4010 + dashboard :8787 v ozadju (brez claude-a), idempotentno.
REM Vnos nalog skozi dashboard UI; Terminal/rescue pot = "rob dev" v PowerShell.
REM
REM Registracija se izvede prek register-autostart.ps1 (HKCU Run, brez admin):
REM   powershell -ExecutionPolicy Bypass -File scripts\register-autostart.ps1
REM
REM Odpiranje dashboarda v brskalniku ob prijavi (neobvezno — odkomentiraj):
REM   start http://localhost:8787

cd /d "C:\Rob system"
python core\dev_cli.py --serve >> "%TEMP%\rob_serve.log" 2>&1
