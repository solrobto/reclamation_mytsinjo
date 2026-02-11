@echo off
setlocal

rem Move to the script directory so relative paths work
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

rem Find a Python launcher
set "PY_CMD="
where python >nul 2>&1
if %errorlevel%==0 set "PY_CMD=python"

if not defined PY_CMD (
  where py >nul 2>&1
  if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
  echo [ERREUR] Python est introuvable. Installe Python 3 puis relance.
  exit /b 1
)

if not exist ".venv" (
  echo [INFO] Creation de l'environnement virtuel...
  %PY_CMD% -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

if exist "requirements.txt" (
  echo [INFO] Installation des dependances...
  python -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

echo [INFO] Lancement de l'app Flask...
python reclam.py

endlocal
