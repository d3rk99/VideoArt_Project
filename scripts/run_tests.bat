@echo off
setlocal

call scripts\setup_env.bat --no-pause
if errorlevel 1 goto :fail

call .venv\Scripts\activate
if errorlevel 1 goto :fail

pytest -q
if errorlevel 1 goto :fail

echo Tests passed.
goto :end

:fail
echo.
echo run_tests.bat failed with errorlevel %errorlevel%.

:end
if /I not "%~1"=="--no-pause" pause
exit /b %errorlevel%
