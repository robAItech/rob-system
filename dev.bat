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
REM Razreši Python enako kot `rob`: portabilen engine\python.exe → venv →
REM sistemski python. engine/ (ali venv/) Scripts damo na PATH, da dev_cli.py
REM najde litellm/bun/claude. Namestitev ne kreira klasičnega activate.bat,
REM zato se zanašamo na python.exe, ne na aktivacijo venva.
if exist "engine\python.exe" (
    set "PATH=%~dp0engine\Scripts;%PATH%"
    "engine\python.exe" core\dev_cli.py %*
) else if exist "venv\Scripts\python.exe" (
    set "PATH=%~dp0venv\Scripts;%PATH%"
    "venv\Scripts\python.exe" core\dev_cli.py %*
) else (
    python core\dev_cli.py %*
)
