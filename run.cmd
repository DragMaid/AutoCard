@echo off
setlocal enabledelayedexpansion

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found. Installing...

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    where uv >nul 2>nul
    if errorlevel 1 (
        echo Failed to install uv or it is not in PATH
        exit /b 1
    )
)

set MODE=%1
shift

if "%MODE%"=="--server" goto server
if "%MODE%"=="--learner" goto learner
if "%MODE%"=="--actor" goto actor

echo Usage:
echo   run.cmd --server
echo   run.cmd --learner --device cuda
echo   run.cmd --actor --count 4
exit /b 1


:server
set ARGS=%*
set PYTHONPATH=.
uv run ml/distributed/server.py %ARGS%
exit /b %errorlevel%


:learner
set DEVICE=

:learner_loop
if "%~1"=="" goto learner_done

if "%~1"=="--device" (
    shift
    set DEVICE=%~1
) else (
    echo Unknown learner arg: %~1
    exit /b 1
)

shift
goto learner_loop

:learner_done
if "%DEVICE%"=="" (
    echo --device is required
    exit /b 1
)

set PYTHONPATH=.
uv run ml/distributed/learner.py --device %DEVICE% --debug
exit /b %errorlevel%


:actor
set COUNT=1
set EXTRA_ARGS=

:actor_loop
if "%~1"=="" goto actor_run

if "%~1"=="--count" (
    shift
    set COUNT=%~1
) else (
    set EXTRA_ARGS=!EXTRA_ARGS! %~1
)

shift
goto actor_loop


:actor_run
set PYTHONPATH=.

for /L %%i in (1,1,%COUNT%) do (
    start "" cmd /c "uv run ml/distributed/actor.py !EXTRA_ARGS! --debug"
)

exit /b 0
