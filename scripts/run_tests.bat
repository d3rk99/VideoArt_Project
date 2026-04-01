@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
pushd "%PROJECT_ROOT%"

set "SKIP_SETUP=0"
set "NO_PAUSE=0"
:parse_args
if "%~1"=="" goto :after_args
if /I "%~1"=="--skip-setup" set "SKIP_SETUP=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto :parse_args
:after_args

if "%SKIP_SETUP%"=="0" (
  call scripts\setup_env.bat --no-pause
  if errorlevel 1 goto :fail
)

call .venv\Scripts\activate
if errorlevel 1 goto :fail

pytest -q
if errorlevel 1 goto :fail

echo Tests passed.
set "ERR=0"
goto :end

:fail
echo.
echo run_tests.bat failed with errorlevel %errorlevel%.
set "ERR=%errorlevel%"

:end
popd
if "%NO_PAUSE%"=="0" pause
exit /b %ERR%
