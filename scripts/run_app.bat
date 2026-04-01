@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

call scripts\setup_env.bat --no-pause
if errorlevel 1 goto :fail

call .venv\Scripts\activate
if errorlevel 1 goto :fail

python -m app.main --config app\config\settings.yaml
if errorlevel 1 goto :fail

set "ERR=0"
goto :end

:fail
echo.
echo run_app.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
