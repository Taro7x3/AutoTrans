@echo off
chcp 65001 > nul
title AutoTrans Bot - セットアップ

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     AutoTrans Bot セットアップウィザード              ║
echo ║     Discord 日韓リアルタイム翻訳Bot                   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo  setup.ps1 を起動しています...
echo.

:: PowerShell の実行ポリシーをバイパスして setup.ps1 を実行
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

:: setup.ps1 が終了した後の処理
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [エラー] セットアップ中にエラーが発生しました。
    echo  setup_log.txt を確認してください。
    echo.
)

pause
