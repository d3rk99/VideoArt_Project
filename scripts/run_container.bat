@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

where docker >nul 2>nul
if errorlevel 1 goto :docker_missing

docker compose up --build ai-portrait-gallery
if errorlevel 1 goto :fail

set "ERR=0"
goto :end

:docker_missing
echo.
echo Docker CLI was not found. Install Docker Desktop, then rerun run_container.bat.
set "ERR=9009"
goto :end

:fail
echo.
echo run_container.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
