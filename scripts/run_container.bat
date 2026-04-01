@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

where docker >nul 2>nul
if errorlevel 1 goto :install_docker

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

:fail
echo.
echo run_container.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if /I not "%~1"=="--no-pause" pause
exit /b %ERR%
