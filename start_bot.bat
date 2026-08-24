@echo off
setlocal

title AutoTrans Bot

echo ========================================
echo   AutoTrans Bot Starting...
echo ========================================
echo.

:: Determine install directory
set "BOT_DIR=%~dp0"
if not exist "%BOT_DIR%venv\Scripts\activate.bat" (
    set "BOT_DIR=%USERPROFILE%\AutoTrans\"
)

:: Check venv exists
if not exist "%BOT_DIR%venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo Please run run_setup.bat first.
    echo.
    pause
    exit /b 1
)

:: Check .env exists
if not exist "%BOT_DIR%.env" (
    echo [ERROR] .env file not found.
    echo Please run run_setup.bat first.
    echo.
    pause
    exit /b 1
)

:: Check and start Ollama service
echo [INFO] Checking Ollama service...
ollama list >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Starting Ollama service...
    start /B ollama serve >nul 2>&1
    echo [INFO] Waiting for Ollama to start (5 seconds)...
    timeout /t 5 /nobreak >nul
    ollama list >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARN] Ollama service could not be confirmed.
        echo        Translation features may not work.
        echo.
    ) else (
        echo [INFO] Ollama service started successfully.
    )
) else (
    echo [INFO] Ollama service is already running.
)

echo.

:: Check bot.py exists
if not exist "%BOT_DIR%bot.py" (
    echo [ERROR] bot.py not found.
    echo Please ensure AutoTrans files are correctly placed.
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call "%BOT_DIR%venv\Scripts\activate.bat"

:: Start bot
echo [INFO] Starting AutoTrans Bot...
echo.
echo ----------------------------------------
echo   Bot is running. Press Ctrl+C to stop.
echo ----------------------------------------
echo.

cd /d "%BOT_DIR%"
python bot.py

echo.
echo ----------------------------------------
echo   Bot stopped.
echo ----------------------------------------
echo.
pause
endlocal
