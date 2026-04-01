@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

where docker >nul 2>nul
if errorlevel 1 goto :install_docker

docker info >nul 2>nul
if errorlevel 1 goto :start_daemon

goto :run_compose

:start_daemon
echo.
echo Docker CLI found, but daemon is not running. Attempting to start Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
) else if exist "%LocalAppData%\Programs\Docker\Docker\Docker Desktop.exe" (
  start "" "%LocalAppData%\Programs\Docker\Docker\Docker Desktop.exe"
) else (
  goto :daemon_unavailable
)

set /a WAIT_COUNT=0
:wait_for_daemon
docker info >nul 2>nul
if %errorlevel%==0 goto :run_compose
timeout /t 2 /nobreak >nul
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 goto :daemon_unavailable
goto :wait_for_daemon

:run_compose
docker compose up --build ai-portrait-gallery
if errorlevel 1 goto :fail

set "ERR=0"
goto :end

:install_docker
echo.
echo Docker CLI was not found. Attempting automatic install of Docker Desktop...
where winget >nul 2>nul
if errorlevel 1 goto :docker_missing
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :docker_missing
echo Docker install command completed. Launch Docker Desktop once, then rerun run_container.bat.
set "ERR=0"
goto :end

:docker_missing
echo.
echo Unable to install Docker automatically.
echo Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and rerun run_container.bat.
set "ERR=9009"
goto :end

:daemon_unavailable
echo.
echo Docker Desktop could not be started automatically or daemon is still unavailable.
echo Start Docker Desktop manually, wait until it shows "Engine running", then rerun run_container.bat.
set "ERR=1"
goto :end

:fail
echo.
echo run_container.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
