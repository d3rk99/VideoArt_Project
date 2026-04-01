@echo off
setlocal EnableDelayedExpansion

set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  where py >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD goto :no_python

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
goto :end

:no_python
echo.
echo Python interpreter was not found.
echo Install Python 3.10+ from https://www.python.org/downloads/windows/
echo or enable the 'py' launcher and rerun this script.
set "ERR=9009"
goto :end

:fail
echo.
echo setup_env.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
if not defined ERR set "ERR=0"
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
