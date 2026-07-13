@echo off
REM ============================================================================
REM  Lance le sequenceur d'alimentation.
REM  - Si .venv existe -> l'utilise (mode materiel reel possible).
REM  - Sinon -> Python systeme / WinPython (le mode simulation fonctionne).
REM
REM  WinPython sans venv : renseigne PYTHON ci-dessous (chemin de python.exe),
REM  ou lance depuis le "WinPython Command Prompt".
REM ============================================================================
cd /d "%~dp0"

REM === A PERSONNALISER si besoin (chemin python.exe WinPython) ===
set "PYTHON="

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py %*
  goto :eof
)

if not "%PYTHON%"=="" (
  "%PYTHON%" main.py %*
  goto :eof
)

echo [INFO] Pas de venv .venv : lancement avec le Python detecte.
py -3.12 main.py %* 2>nul && goto :eof
python main.py %*
