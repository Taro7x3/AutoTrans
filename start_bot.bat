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
    pause
    exit /b 1
)

:: Check .env exists
if not exist "%BOT_DIR%.env" (
    echo [ERROR] .env file not found.
    echo Please run run_setup.bat first.
    pause
    exit /b 1
)

:: Check bot.py exists
if not exist "%BOT_DIR%bot.py" (
    echo [ERROR] bot.py not found.
    echo Please run run_setup.bat first.
    pause
    exit /b 1
)

:: Check and start Ollama service using TCP port check
echo [INFO] Checking Ollama service...
powershell.exe -NoProfile -Command "try { $tcp = New-Object System.Net.Sockets.TcpClient; $tcp.Connect('127.0.0.1', 11434); $tcp.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Starting Ollama service...
    start "" /B ollama serve
    ping -n 6 127.0.0.1 >nul
    echo [INFO] Ollama service started.
) else (
    echo [INFO] Ollama service is already running.
)

echo.
echo [INFO] Activating virtual environment...
call "%BOT_DIR%venv\Scripts\activate.bat"

:: Check and install PyTorch if missing
echo [INFO] Checking PyTorch installation...
python -c "import torch" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyTorch not found. Installing PyTorch with CUDA support...
    echo [INFO] This may take several minutes...
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install PyTorch.
        echo Please run manually: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
        pause
        exit /b 1
    )
    echo [INFO] PyTorch installed successfully.
)

echo [INFO] Starting bot...
echo.
cd /d "%BOT_DIR%"
python bot.py

echo.
echo [INFO] Bot stopped.
endlocal
pause
