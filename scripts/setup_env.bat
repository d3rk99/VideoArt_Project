@echo off
setlocal

if not exist .venv (
  python -m venv .venv
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

:fail
echo.
echo setup_env.bat failed with errorlevel %errorlevel%.

:end
if /I not "%~1"=="--no-pause" pause
exit /b %errorlevel%
