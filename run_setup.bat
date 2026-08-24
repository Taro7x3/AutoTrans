@echo off
chcp 65001 > nul
title AutoTrans Bot Setup

powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host ''; Write-Host '╔══════════════════════════════════════════════════════╗' -ForegroundColor Cyan; Write-Host '║     AutoTrans Bot セットアップウィザード              ║' -ForegroundColor Cyan; Write-Host '║     Discord 日韓リアルタイム翻訳Bot                   ║' -ForegroundColor Cyan; Write-Host '╚══════════════════════════════════════════════════════╝' -ForegroundColor Cyan; Write-Host ''"

:: setup.ps1 が同じフォルダにあるか確認
if exist "%~dp0setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host '  setup.ps1 を起動しています...' -ForegroundColor Gray; Write-Host ''"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host '  setup.ps1 が見つかりません。GitHubからダウンロードします...' -ForegroundColor Yellow; Write-Host ''"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $url='https://raw.githubusercontent.com/Taro7x3/AutoTrans/main/setup.ps1'; $tmp=[System.IO.Path]::Combine($env:TEMP,'autotrans_setup.ps1'); [System.Net.WebClient]::new().DownloadFile($url,$tmp); $bytes=[System.IO.File]::ReadAllBytes($tmp); if ($bytes[0] -ne 0xEF -or $bytes[1] -ne 0xBB -or $bytes[2] -ne 0xBF) { [System.IO.File]::WriteAllBytes($tmp, ([byte[]](0xEF,0xBB,0xBF) + $bytes)) }; & $tmp"
)

:: 終了コードの確認
if %ERRORLEVEL% NEQ 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host ''; Write-Host '  [エラー] セットアップ中にエラーが発生しました。' -ForegroundColor Red; Write-Host '  setup_log.txt を確認してください。' -ForegroundColor Red; Write-Host ''"
)

pause
