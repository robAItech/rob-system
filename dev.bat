@echo off
REM dev.bat — Windows launcher za core/dev_cli.py (P4 orkestracija)
REM Nadomešča dev.ps1 in zagon.ps1. Port 4000 se ne dotika.
REM
REM Uporaba:
REM   dev.bat                  proxy :4010 + dashboard :8787 v ozadju, poveže claude
REM   dev.bat --init           dry-run preverba
REM   dev.bat --proxy-only     samo LiteLLM na 4010 v ospredju
REM   dev.bat --dashboard-only samo Command-Center (bun src/server.ts) na 8787
REM   dev.bat --claude-only    samo claude ob že obstoječem proxyju
cd /d "%~dp0"
REM Aktiviraj venv (Windows: Scripts\activate.bat), če obstaja; sicer sistemski python.
if exist "engine\Scripts\activate.bat" (
    call "engine\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)
python core\dev_cli.py %*
