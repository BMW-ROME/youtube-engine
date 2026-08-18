@echo off
REM start_engine.bat -- Windows launcher for the YouTube Engine.
REM Run this from the repo root (where scripts\ and core\ live).

setlocal

if not exist "scripts\start_engine.py" (
    echo ERROR: scripts\start_engine.py not found.
    echo Run this .bat file from the youtube-engine repo root, not from inside scripts\.
    pause
    exit /b 1
)

if "%VIRTUAL_ENV%"=="" (
    if exist "venv\Scripts\activate.bat" (
        echo Activating venv...
        call venv\Scripts\activate.bat
    ) else (
        echo WARNING: No virtual environment detected and venv\ not found.
        echo Continuing with system Python -- this may fail if dependencies
        echo are not installed globally.
    )
)

python scripts\start_engine.py %*

endlocal
