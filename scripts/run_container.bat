@echo off
setlocal

docker compose up --build ai-portrait-gallery
if errorlevel 1 goto :fail

goto :end

:fail
echo.
echo run_container.bat failed with errorlevel %errorlevel%.

:end
if /I not "%~1"=="--no-pause" pause
exit /b %errorlevel%
