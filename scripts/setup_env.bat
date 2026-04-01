@echo off
setlocal EnableDelayedExpansion

set "PYTHON_CMD="
call :detect_python
if defined PYTHON_CMD goto :have_python

echo Python was not found. Attempting automatic install with winget...
where winget >nul 2>nul
if errorlevel 1 goto :no_python

winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :no_python

rem Try common install locations in current shell before re-detecting.
set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"
set "PATH=%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts;%PATH%"

call :detect_python
if defined PYTHON_CMD goto :have_python
goto :no_python

:have_python
echo Using interpreter: %PYTHON_CMD%

if not exist .venv (
  call %PYTHON_CMD% -m venv .venv
)
if errorlevel 1 goto :fail

call .venv\Scripts\activate
if errorlevel 1 goto :fail

python -m pip install --upgrade pip
if errorlevel 1 goto :fail

pip install -r requirements.txt
if errorlevel 1 goto :fail

echo Environment ready.
set "ERR=0"
goto :end

:detect_python
set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  where py >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=py -3"
)
exit /b 0

:no_python
echo.
echo Python interpreter is still unavailable.
echo Install Python 3.10+ from https://www.python.org/downloads/windows/
echo or install manually with: winget install -e --id Python.Python.3.11
set "ERR=9009"
goto :end

:fail
echo.
echo setup_env.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
