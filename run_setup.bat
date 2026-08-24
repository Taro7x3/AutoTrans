@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "SETUP_PS1=%SCRIPT_DIR%setup.ps1"
set "REPO_RAW=https://raw.githubusercontent.com/Taro7x3/AutoTrans/main/setup.ps1"
set "TEMP_PS1=%TEMP%\autotrans_setup.ps1"

if exist "%SETUP_PS1%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SETUP_PS1%"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Downloading setup script...' -ForegroundColor Cyan; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $bytes = (New-Object Net.WebClient).DownloadData('%REPO_RAW%'); if ($bytes[0] -ne 0xEF -or $bytes[1] -ne 0xBB -or $bytes[2] -ne 0xBF) { $bytes = [byte[]](0xEF,0xBB,0xBF) + $bytes }; [IO.File]::WriteAllBytes('%TEMP_PS1%', $bytes); & '%TEMP_PS1%'"
)

endlocal
pause
