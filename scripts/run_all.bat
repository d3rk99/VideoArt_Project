@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

echo [1/4] Creating Python environment and installing dependencies...
call scripts\setup_env.bat --no-pause
if errorlevel 1 goto :fail

echo [2/4] Running unit tests...
call scripts\run_tests.bat --skip-setup
if errorlevel 1 goto :fail

where docker >nul 2>nul
if errorlevel 1 goto :docker_missing

echo [3/4] Building container image...
docker compose build
if errorlevel 1 goto :fail

echo [4/4] Running tests in container...
docker compose run --rm tests
if errorlevel 1 goto :fail

echo Done. Local + container checks are complete.
set "ERR=0"
goto :end

:docker_missing
echo [3/4] Docker CLI not found. Skipping container build/test checks.
echo Install Docker Desktop to enable contained-environment validation.
echo Done. Local checks are complete.
set "ERR=0"
goto :end

:fail
echo.
echo run_all.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
