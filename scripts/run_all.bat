@echo off
setlocal

echo [1/4] Creating Python environment and installing dependencies...
call scripts\setup_env.bat
if errorlevel 1 exit /b 1

echo [2/4] Running unit tests...
call scripts\run_tests.bat
if errorlevel 1 exit /b 1

echo [3/4] Building container image...
docker compose build
if errorlevel 1 exit /b 1

echo [4/4] Running tests in container...
docker compose run --rm tests
if errorlevel 1 exit /b 1

echo Done. Local + container checks are complete.
