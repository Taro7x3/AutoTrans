#Requires -Version 5.1
<#
.SYNOPSIS
    AutoTrans Discord翻訳Bot 自動セットアップスクリプト
.DESCRIPTION
    Git、Python 3.11、FFmpeg、Ollama、AIモデル、Pythonパッケージを自動インストールし、
    Discord Botが動作する環境を構築します。
    GitHubからリポジトリをcloneして完全セットアップします。
.NOTES
    対象OS: Windows 11 / 必要環境: NVIDIA GPU (VRAM 8GB以上)、インターネット接続
#>

# ─────────────────────────────────────────────────────────────────────────────
# 文字コード設定
# ─────────────────────────────────────────────────────────────────────────────
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# ─────────────────────────────────────────────────────────────────────────────
# グローバル変数
# ─────────────────────────────────────────────────────────────────────────────
$RepoUrl            = "https://github.com/Taro7x3/AutoTrans"
$InstallDir         = "$env:USERPROFILE\AutoTrans"
$tempLogFile        = "$env:TEMP\AutoTrans_setup_log.txt"
$LogFile            = Join-Path $InstallDir "setup_log.txt"
$TotalSteps         = 13
$script:CurrentStep = 0
$script:ErrorCount  = 0

# ─────────────────────────────────────────────────────────────────────────────
# ユーティリティ関数
# ─────────────────────────────────────────────────────────────────────────────
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        Add-Content -Path $tempLogFile -Value "[$ts] $Message" -Encoding UTF8
        if (Test-Path $InstallDir) {
            Add-Content -Path $LogFile -Value "[$ts] $Message" -Encoding UTF8
        }
    } catch {
        # ログ書き込み失敗は無視
    }
}

function Write-StepHeader {
    param([string]$StepName)
    $script:CurrentStep++
    $n = $script:CurrentStep
    Write-Host ""
    Write-Host "-----------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "[$n/$TotalSteps] Step $n`: $StepName" -ForegroundColor White
    Write-Host "-----------------------------------------------------" -ForegroundColor DarkGray
    Write-Log "=== Step $n`: $StepName ==="
}

function Write-Running { param([string]$m); Write-Host "  [実行中] $m" -ForegroundColor Yellow;  Write-Log "[実行中] $m" }
function Write-Done    { param([string]$m); Write-Host "  [完了]   $m" -ForegroundColor Green;   Write-Log "[完了] $m" }
function Write-Skip    { param([string]$m); Write-Host "  [スキップ] $m" -ForegroundColor Cyan;  Write-Log "[スキップ] $m" }
function Write-Err     { param([string]$m); Write-Host "  [エラー] $m" -ForegroundColor Red;     Write-Log "[エラー] $m"; $script:ErrorCount++ }
function Write-Info    { param([string]$m); Write-Host "  $m" -ForegroundColor Gray;             Write-Log "[情報] $m" }

function Confirm-Continue {
    param([string]$Prompt = "続行しますか？ (Y/N)")
    Write-Host ""
    $ans = Read-Host $Prompt
    if ($ans -notmatch '^[Yy]') {
        Write-Host "セットアップを中断しました。" -ForegroundColor Yellow
        Write-Log "ユーザーによりセットアップが中断されました。"
        exit 1
    }
}

function Refresh-Path {
    $mp      = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $up      = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$mp;$up"
    Write-Log "PATHを更新しました。"
}

# ─────────────────────────────────────────────────────────────────────────────
# ログファイル初期化（一時ファイル）
# ─────────────────────────────────────────────────────────────────────────────
$startTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Set-Content -Path $tempLogFile -Value "AutoTrans Bot セットアップログ - $startTime" -Encoding UTF8
Add-Content -Path $tempLogFile -Value ("=" * 60) -Encoding UTF8

# ─────────────────────────────────────────────────────────────────────────────
# ステップ0: 管理者権限チェック
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  管理者権限を確認しています..." -ForegroundColor Gray

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin   = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "  管理者権限が必要です。管理者として再起動します..." -ForegroundColor Yellow
    Write-Log "管理者権限なし。管理者として再起動します。"
    Start-Sleep -Seconds 2
    $sp = $MyInvocation.MyCommand.Path
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$sp`"" -Verb RunAs
    exit
}

Write-Log "管理者権限確認済み。"

try {
    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction SilentlyContinue
    Write-Log "実行ポリシーを RemoteSigned に設定しました。"
} catch {
    Write-Log "実行ポリシーの設定をスキップしました。"
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ1: ウェルカムメッセージ
# ─────────────────────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     AutoTrans Bot セットアップウィザード              ║" -ForegroundColor Cyan
Write-Host "║     Discord 日韓リアルタイム翻訳Bot                   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  このスクリプトは以下をインストールします：" -ForegroundColor White
Write-Host "    ✓ Git" -ForegroundColor Green
Write-Host "    ✓ Python 3.11" -ForegroundColor Green
Write-Host "    ✓ FFmpeg" -ForegroundColor Green
Write-Host "    ✓ Ollama (ローカルAI実行環境)" -ForegroundColor Green
Write-Host "    ✓ AIモデル (qwen2.5:7b-instruct) ※約4GB" -ForegroundColor Green
Write-Host "    ✓ 必要なPythonパッケージ" -ForegroundColor Green
Write-Host ""
Write-Host "  インストール先: $InstallDir" -ForegroundColor White
Write-Host ""
Write-Host "  続行するには Enter キーを押してください..." -ForegroundColor White
Read-Host | Out-Null

Write-Log "セットアップ開始。インストール先: $InstallDir"
$script:CurrentStep = 1

# ─────────────────────────────────────────────────────────────────────────────
# ステップ2: wingetの確認
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "winget の確認"

try {
    Write-Running "winget のバージョンを確認しています..."
    $wv = winget --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Done "winget が見つかりました: $wv"
        Write-Log "winget バージョン: $wv"
    } else {
        throw "winget コマンドが失敗しました"
    }
} catch {
    Write-Err "winget が見つかりません。"
    Write-Host ""
    Write-Host "  winget (App Installer) をインストールする必要があります。" -ForegroundColor Yellow
    Write-Host "  Microsoft Store を開いて App Installer を検索し、" -ForegroundColor Yellow
    Write-Host "  インストールしてからこのスクリプトを再実行してください。" -ForegroundColor Yellow
    Write-Host ""
    Write-Log "winget が見つかりません。Microsoft Store を開きます。"
    try {
        Start-Process "ms-windows-store://pdp/?ProductId=9NBLGGH4NNS1"
    } catch {
        Start-Process "https://apps.microsoft.com/store/detail/app-installer/9NBLGGH4NNS1"
    }
    Write-Host "  Microsoft Store を開きました。App Installer をインストール後、" -ForegroundColor Cyan
    Write-Host "  このスクリプトを再実行してください。" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Enterキーで終了します"
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ3: Git のインストール確認
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Git のインストール確認"

$gitInstalled = $false

try {
    Write-Running "Git のバージョンを確認しています..."
    $gv = git --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $gv -match "git version") {
        Write-Skip "Git がすでにインストールされています: $gv"
        Write-Log "Git 検出: $gv"
        $gitInstalled = $true
    } else {
        throw "Git が見つかりません"
    }
} catch {
    Write-Info "Git が見つかりません。インストールします。"
}

if (-not $gitInstalled) {
    try {
        Write-Running "Git をインストールしています..."
        Write-Log "winget install Git.Git を実行します。"
        winget install --id Git.Git --source winget --accept-package-agreements --accept-source-agreements --silent 2>&1 | ForEach-Object {
            Write-Log "  winget: $_"
        }
        Write-Running "PATHを更新しています..."
        Refresh-Path

        $gitPaths = @(
            "C:\Program Files\Git\cmd",
            "C:\Program Files (x86)\Git\cmd"
        )
        foreach ($gp in $gitPaths) {
            if (Test-Path "$gp\git.exe") {
                $env:Path += ";$gp"
                Write-Log "Git パス追加: $gp"
                break
            }
        }

        $gv2 = git --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $gv2 -match "git version") {
            Write-Done "Git のインストールが完了しました: $gv2"
            $gitInstalled = $true
        } else {
            throw "インストール後も Git が見つかりません"
        }
    } catch {
        Write-Err "Git のインストールに失敗しました: $_"
        Write-Log "Git インストールエラー: $_"
        Confirm-Continue "Git のインストールに失敗しました。続行しますか？ (Y/N)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ4: Python 3.11のインストール
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Python 3.11 のインストール"

$pythonInstalled = $false
$pythonExe       = "python"

# Python 3.10〜3.12 がインストール済みか確認（PyTorch対応バージョン）
try {
    Write-Running "Pythonのバージョンを確認しています..."
    $pv = python --version 2>&1
    Write-Log "python --version: $pv"
    if ($pv -match "Python (\d+)\.(\d+)") {
        $maj = [int]$Matches[1]
        $min = [int]$Matches[2]
        if ($maj -eq 3 -and $min -ge 10 -and $min -le 12) {
            Write-Skip "Python $maj.$min が見つかりました（PyTorch対応バージョン）"
            Write-Log "Python $maj.$min 検出（PyTorch対応）。"
            $pythonInstalled = $true
        } elseif ($maj -eq 3 -and $min -ge 13) {
            Write-Info "Python $maj.$min はPyTorch非対応です。Python 3.11をインストールします..."
            Write-Log "Python $maj.$min はPyTorch非対応（3.13以上）。Python 3.11をインストールします。"
        } else {
            Write-Info "Python $maj.$min が見つかりましたが 3.10〜3.12 が必要です。Python 3.11 をインストールします。"
            Write-Log "Python $maj.$min 検出（バージョン不足）。Python 3.11をインストールします。"
        }
    }
} catch {
    Write-Info "Python が見つかりません。インストールします。"
    Write-Log "Python 未検出: $_"
}

# py ランチャーで Python 3.11 を確認
if (-not $pythonInstalled) {
    try {
        $py311Ver = & py -3.11 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonInstalled = $true
            Write-Skip "Python 3.11 (py launcher) が見つかりました"
            Write-Log "Python 3.11 (py launcher) 検出済み。"
        }
    } catch {}
}

# LOCALAPPDATA のパスを確認
if (-not $pythonInstalled) {
    if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe") {
        $pythonInstalled = $true
        Write-Skip "Python 3.11 が見つかりました: $env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
        Write-Log "Python 3.11 検出済み: $env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    }
}

if (-not $pythonInstalled) {
    try {
        Write-Running "Python 3.11 をインストールしています... (数分かかる場合があります)"
        Write-Log "winget install Python.Python.3.11 を実行します。"
        winget install --id Python.Python.3.11 --source winget --accept-package-agreements --accept-source-agreements --silent 2>&1 | ForEach-Object {
            Write-Log "  winget: $_"
        }
        Write-Running "PATHを更新しています..."
        Refresh-Path

        $pyPaths = @(
            "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
            "C:\Python311\python.exe",
            "$env:ProgramFiles\Python311\python.exe"
        )
        foreach ($p in $pyPaths) {
            if (Test-Path $p) { $pythonExe = $p; Write-Log "Python発見: $p"; break }
        }

        $pv2 = & $pythonExe --version 2>&1
        if ($pv2 -match "Python") {
            Write-Done "Python のインストールが完了しました: $pv2"
            $pythonInstalled = $true
        } else {
            throw "インストール後もPythonが見つかりません"
        }
    } catch {
        Write-Err "Python のインストールに失敗しました: $_"
        Write-Log "Python インストールエラー: $_"
        Confirm-Continue "Python のインストールに失敗しました。続行しますか？ (Y/N)"
    }
}

# Python 3.11 のフルパスを解決する
$python311Path = $null
$possiblePaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "C:\Python311\python.exe",
    "$env:ProgramFiles\Python311\python.exe"
)
foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $python311Path = $path
        Write-Log "Python 3.11 フルパス発見: $path"
        break
    }
}

# py ランチャーで Python 3.11 を探す
if (-not $python311Path) {
    try {
        $pyOutput = & py -3.11 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $python311Path = (& py -3.11 -c "import sys; print(sys.executable)" 2>&1).Trim()
            Write-Log "Python 3.11 フルパス (py launcher): $python311Path"
        }
    } catch {}
}

if ($python311Path) {
    $pythonExe = $python311Path
    Write-Info "使用するPython 3.11: $pythonExe"
    Write-Log "pythonExe を Python 3.11 フルパスに設定: $pythonExe"
} else {
    Write-Info "使用するPython: $pythonExe"
    Write-Log "Python 3.11 フルパスが見つかりません。pythonExe=$pythonExe を使用します。"
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ5: AutoTrans リポジトリのダウンロード
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "AutoTrans リポジトリのダウンロード"

if (Test-Path $InstallDir) {
    Write-Host ""
    Write-Host "  $InstallDir に既存のインストールが見つかりました。" -ForegroundColor Yellow
    $upd = Read-Host "  上書き更新しますか？ (Y/N)"
    if ($upd -match '^[Yy]') {
        try {
            Write-Running "リポジトリを更新しています (git pull)..."
            Write-Log "git -C $InstallDir pull を実行します。"
            git -C $InstallDir pull 2>&1 | ForEach-Object { Write-Log "  git pull: $_" }
            if ($LASTEXITCODE -eq 0) {
                Write-Done "リポジトリを更新しました: $InstallDir"
            } else {
                throw "git pull が終了コード $LASTEXITCODE で終了しました"
            }
        } catch {
            Write-Host "  [警告] アップデートに失敗しました。既存のファイルを使用します。" -ForegroundColor Yellow
            Write-Log "[警告] git pull エラー: $_"
        }
    } else {
        Write-Skip "既存のインストールをそのまま使用します。"
        Write-Log "既存インストールをスキップ。"
    }
} else {
    try {
        Write-Running "リポジトリをダウンロードしています (git clone)..."
        Write-Log "git clone $RepoUrl $InstallDir を実行します。"
        git clone $RepoUrl $InstallDir 2>&1 | ForEach-Object { Write-Log "  git clone: $_" }
        if ($LASTEXITCODE -ne 0) {
            throw "git clone に失敗しました (終了コード: $LASTEXITCODE)"
        }
        Write-Done "リポジトリをダウンロードしました: $InstallDir"
        Write-Log "git clone 完了。"
    } catch {
        Write-Err "リポジトリのダウンロードに失敗しました: $_"
        Write-Log "git clone エラー: $_"
        Write-Host "  インターネット接続を確認してください。" -ForegroundColor Yellow
        Confirm-Continue "リポジトリのダウンロードに失敗しました。続行しますか？ (Y/N)"
    }
}

# InstallDir に移動して以降の処理を実行
if (Test-Path $InstallDir) {
    Set-Location $InstallDir
    Write-Log "作業ディレクトリを変更しました: $InstallDir"

    # ログファイルを InstallDir にコピー
    try {
        if (Test-Path $tempLogFile) {
            Copy-Item -Path $tempLogFile -Destination $LogFile -Force
        }
    } catch {
        # ログ移行失敗は無視
    }
} else {
    Write-Err "インストールディレクトリが見つかりません: $InstallDir"
    Write-Host "  セットアップを続行できません。" -ForegroundColor Red
    Read-Host "Enterキーで終了します"
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ6: FFmpegのインストール
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "FFmpeg のインストール"

$ffmpegInstalled = $false

try {
    Write-Running "FFmpeg のバージョンを確認しています..."
    $fv = ffmpeg -version 2>&1 | Select-Object -First 1
    if ($fv -match "ffmpeg version") {
        Write-Skip "FFmpeg がすでにインストールされています。"
        Write-Log "FFmpeg 検出: $fv"
        $ffmpegInstalled = $true
    }
} catch {
    Write-Info "FFmpeg が見つかりません。インストールします。"
}

if (-not $ffmpegInstalled) {
    try {
        Write-Running "FFmpeg をインストールしています..."
        Write-Log "winget install Gyan.FFmpeg を実行します。"
        winget install --id Gyan.FFmpeg --source winget --accept-package-agreements --accept-source-agreements --silent 2>&1 | ForEach-Object {
            Write-Log "  winget: $_"
        }
        Write-Running "PATHを更新しています..."
        Refresh-Path
        Write-Done "FFmpeg のインストールが完了しました。"
        Write-Log "FFmpeg インストール完了。"
    } catch {
        Write-Err "FFmpeg のインストールに失敗しました: $_"
        Write-Log "FFmpeg インストールエラー: $_"
        Confirm-Continue "FFmpeg のインストールに失敗しました。続行しますか？ (Y/N)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ7: Ollamaのインストール
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Ollama のインストール"

$ollamaInstalled = $false

try {
    Write-Running "Ollama のバージョンを確認しています..."
    $ov = ollama --version 2>&1
    if ($LASTEXITCODE -eq 0 -or ($ov -match "ollama")) {
        Write-Skip "Ollama がすでにインストールされています。"
        Write-Log "Ollama 検出: $ov"
        $ollamaInstalled = $true
    }
} catch {
    Write-Info "Ollama が見つかりません。インストールします。"
}

if (-not $ollamaInstalled) {
    # まず --silent でサイレントインストールを試みる
    $wingetSuccess = $false
    try {
        Write-Running "Ollama をサイレントインストールしています... (数分かかる場合があります)"
        Write-Log "winget install Ollama.Ollama --silent を実行します。"
        winget install --id Ollama.Ollama --source winget --accept-package-agreements --accept-source-agreements --silent 2>&1 | ForEach-Object {
            Write-Log "  winget: $_"
        }
        if ($LASTEXITCODE -eq 0) {
            $wingetSuccess = $true
            Write-Log "winget --silent インストール成功。"
        } else {
            Write-Log "winget --silent が終了コード $LASTEXITCODE で終了。通常インストールにフォールバックします。"
        }
    } catch {
        Write-Log "winget --silent 失敗: $_。通常インストールにフォールバックします。"
    }

    # --silent が失敗した場合は通常インストール（GUIインストーラー）にフォールバック
    if (-not $wingetSuccess) {
        try {
            Write-Running "Ollama を通常インストールしています... (GUIインストーラーが起動します)"
            Write-Host "  ※ インストーラーが起動したら指示に従ってインストールを完了してください。" -ForegroundColor Yellow
            Write-Log "winget install Ollama.Ollama (通常) を実行します。"
            winget install --id Ollama.Ollama --source winget --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object {
                Write-Log "  winget: $_"
            }
            Write-Log "winget 通常インストール完了 (終了コード: $LASTEXITCODE)。"
        } catch {
            Write-Err "Ollama のインストールに失敗しました: $_"
            Write-Log "Ollama インストールエラー: $_"
            Confirm-Continue "Ollama のインストールに失敗しました。続行しますか？ (Y/N)"
        }
    }

    # PATHを更新してollamaコマンドを認識させる
    Write-Running "PATHを更新しています..."
    Refresh-Path

    $ollamaPaths = @(
        "$env:LOCALAPPDATA\Programs\Ollama",
        "C:\Program Files\Ollama",
        "$env:ProgramFiles\Ollama"
    )
    foreach ($op in $ollamaPaths) {
        if (Test-Path "$op\ollama.exe") {
            if ($env:Path -notlike "*$op*") {
                $env:Path += ";$op"
                Write-Log "Ollamaパス追加: $op"
            }
            break
        }
    }

    # ollamaコマンドが使えるか確認（最大30秒待機）
    $ollamaFound = $false
    for ($i = 0; $i -lt 6; $i++) {
        if (Get-Command ollama -ErrorAction SilentlyContinue) {
            $ollamaFound = $true
            break
        }
        # フルパスでも確認
        foreach ($op in $ollamaPaths) {
            if (Test-Path "$op\ollama.exe") {
                if ($env:Path -notlike "*$op*") {
                    $env:Path += ";$op"
                }
                $ollamaFound = $true
                break
            }
        }
        if ($ollamaFound) { break }
        Write-Info "Ollamaコマンドを待機中... ($($i+1)/6)"
        Write-Log "Ollamaコマンド待機中 ($($i+1)/6)。"
        Start-Sleep -Seconds 5
    }

    if ($ollamaFound) {
        Write-Done "Ollama のインストールが完了しました。"
        Write-Log "Ollama インストール完了。"
        $ollamaInstalled = $true
    } else {
        Write-Err "Ollamaコマンドが見つかりません。インストールが完了していない可能性があります。"
        Write-Log "Ollamaコマンド未検出。インストール失敗の可能性。"
        Confirm-Continue "Ollama のインストールを確認できませんでした。続行しますか？ (Y/N)"
    }
}

# Ollama serve をバックグラウンドで起動（すでに起動していなければ）
Write-Running "Ollama サービスを起動しています..."
$ollamaExePath = $null
$ollamaPaths = @(
    "$env:LOCALAPPDATA\Programs\Ollama",
    "C:\Program Files\Ollama",
    "$env:ProgramFiles\Ollama"
)
foreach ($op in $ollamaPaths) {
    if (Test-Path "$op\ollama.exe") {
        $ollamaExePath = "$op\ollama.exe"
        break
    }
}

try {
    $ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if ($ollamaProc) {
        Write-Skip "Ollama サービスはすでに起動しています。"
        Write-Log "Ollama プロセス確認済み。"
    } else {
        # フルパスが見つかればそれを使用、なければコマンド名で試みる
        if ($ollamaExePath) {
            Start-Process -FilePath $ollamaExePath -ArgumentList "serve" -WindowStyle Hidden -ErrorAction Stop
            Write-Log "ollama serve をフルパスで起動しました: $ollamaExePath"
        } else {
            Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction Stop
            Write-Log "ollama serve をコマンド名で起動しました。"
        }
        Write-Info "Ollama サービスを起動しました。起動待機中..."
        Start-Sleep -Seconds 3
        Write-Done "Ollama サービスが起動しました。"
    }
} catch {
    Write-Err "Ollama サービスの起動に失敗しました: $_"
    Write-Log "Ollama サービス起動エラー: $_"
    Write-Info "後で手動で 'ollama serve' を実行してください。"
}

# Ollama APIが応答するまで待機（最大60秒）
$apiReady = $false
Write-Running "Ollama API の応答を確認しています..."
for ($i = 0; $i -lt 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
        $apiReady = $true
        Write-Done "Ollama API が応答しています。"
        Write-Log "Ollama API 応答確認済み。"
        break
    } catch {
        Write-Info "Ollama API を待機中... ($($i+1)/12)"
        Write-Log "Ollama API 待機中 ($($i+1)/12)。"
        Start-Sleep -Seconds 5
    }
}

if (-not $apiReady) {
    Write-Host "  [警告] Ollama API が応答しません。モデルのダウンロードをスキップします。" -ForegroundColor Yellow
    Write-Host "  後で手動で 'ollama pull qwen2.5:7b-instruct' を実行してください。" -ForegroundColor Yellow
    Write-Log "[警告] Ollama API が応答しません。モデルダウンロードをスキップします。"
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ8: AIモデルのダウンロード
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "AIモデル (qwen2.5:7b-instruct) のダウンロード"

$modelName = "qwen2.5:7b-instruct"

# Ollama APIが応答していない場合はスキップ
if (-not $apiReady) {
    Write-Host "  [スキップ] Ollama API が応答していないため、モデルのダウンロードをスキップします。" -ForegroundColor Yellow
    Write-Host "  Ollama が正常に起動したら、以下のコマンドを手動で実行してください：" -ForegroundColor Yellow
    Write-Host "    ollama pull $modelName" -ForegroundColor Cyan
    Write-Log "[スキップ] Ollama API 未応答のためモデルダウンロードをスキップ。"
    $script:ErrorCount++
} else {
    try {
        Write-Running "インストール済みモデルを確認しています..."
        $ollamaList = ollama list 2>&1
        Write-Log "ollama list: $ollamaList"

        if ($ollamaList -match [regex]::Escape($modelName)) {
            Write-Skip "モデル '$modelName' はすでにダウンロード済みです。"
        } else {
            Write-Running "AIモデルをダウンロード中... (約4GB、時間がかかります)"
            Write-Host "  ※ ダウンロードには数分〜数十分かかる場合があります。" -ForegroundColor Yellow
            Write-Host "  ※ このウィンドウを閉じないでください。" -ForegroundColor Yellow
            Write-Log "ollama pull $modelName を実行します。"

            $pullProc = Start-Process -FilePath "ollama" -ArgumentList "pull $modelName" -NoNewWindow -PassThru -Wait
            if ($pullProc.ExitCode -eq 0) {
                Write-Done "AIモデルのダウンロードが完了しました。"
                Write-Log "モデル '$modelName' のダウンロード完了。"
            } else {
                throw "ollama pull が終了コード $($pullProc.ExitCode) で終了しました"
            }
        }
    } catch {
        Write-Err "AIモデルのダウンロードに失敗しました: $_"
        Write-Log "モデルダウンロードエラー: $_"
        Write-Info "後で手動で 'ollama pull $modelName' を実行してください。"
        Confirm-Continue "AIモデルのダウンロードに失敗しました。続行しますか？ (Y/N)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ9: Python仮想環境の作成とパッケージインストール
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Python仮想環境の作成とパッケージインストール"

Set-Location $InstallDir
$venvPath   = Join-Path $InstallDir "venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip    = Join-Path $venvPath "Scripts\pip.exe"

if (Test-Path $venvPython) {
    Write-Skip "仮想環境はすでに存在します。"
    Write-Log "仮想環境確認済み: $venvPath"
} else {
    try {
        Write-Running "Python仮想環境を作成しています..."

        # Python 3.11 のフルパスを使用して仮想環境を作成
        if ($python311Path) {
            Write-Log "Python 3.11 フルパスで venv を作成します: $python311Path -m venv $venvPath --clear"
            Write-Info "Python 3.11 を使用: $python311Path"
            & $python311Path -m venv $venvPath --clear 2>&1 | ForEach-Object { Write-Log "  venv: $_" }
        } else {
            Write-Log "python -m venv $venvPath を実行します（pythonExe=$pythonExe）。"
            & $pythonExe -m venv $venvPath 2>&1 | ForEach-Object { Write-Log "  venv: $_" }
        }

        if (Test-Path $venvPython) {
            Write-Done "仮想環境を作成しました: $venvPath"
        } else {
            throw "仮想環境の作成に失敗しました"
        }
    } catch {
        Write-Err "仮想環境の作成に失敗しました: $_"
        Write-Log "仮想環境作成エラー: $_"
        Confirm-Continue "仮想環境の作成に失敗しました。続行しますか？ (Y/N)"
    }
}

try {
    Write-Running "pip をアップグレードしています..."
    & $venvPython -m pip install --upgrade pip 2>&1 | ForEach-Object { Write-Log "  pip upgrade: $_" }
    Write-Done "pip のアップグレードが完了しました。"
} catch {
    Write-Err "pip のアップグレードに失敗しました: $_"
    Write-Log "pip アップグレードエラー: $_"
}

# PyTorch CUDA版のインストール（最優先・単独で実行）
Write-Log "PyTorch (CUDA 12.1対応版) をインストールしています..."
Write-Log "※ 約2GBのダウンロードが発生します。時間がかかる場合があります..."

$torchInstalled = $false
$torchAttempts = 0

while (-not $torchInstalled -and $torchAttempts -lt 3) {
    $torchAttempts++
    Write-Running "PyTorchインストール試行 $torchAttempts/3..."
    Write-Log "PyTorchインストール試行 $torchAttempts/3..."

    & "$InstallDir\venv\Scripts\pip.exe" install torch torchaudio `
        --index-url https://download.pytorch.org/whl/cu121 `
        --no-cache-dir 2>&1 | ForEach-Object {
        Write-Log "  torch: $_"
        if ($_ -match "Downloading|Installing|Successfully") {
            Write-Host "    $_" -ForegroundColor DarkGray
        }
    }

    if ($LASTEXITCODE -eq 0) {
        # インストール確認
        $torchCheck = & "$InstallDir\venv\Scripts\python.exe" -c "import torch; print(torch.__version__)" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $torchInstalled = $true
            Write-Done "PyTorch $torchCheck のインストールが完了しました"
            Write-Log "PyTorch $torchCheck インストール確認済み。"
        } else {
            Write-Host "  [警告] PyTorchのインポートに失敗しました。再試行します..." -ForegroundColor Yellow
            Write-Log "[警告] PyTorchのインポートに失敗しました。再試行します..."
        }
    } else {
        Write-Host "  [警告] PyTorchのインストールに失敗しました。再試行します..." -ForegroundColor Yellow
        Write-Log "[警告] PyTorchのインストールに失敗しました (終了コード: $LASTEXITCODE)。再試行します..."
        Start-Sleep -Seconds 3
    }
}

if (-not $torchInstalled) {
    Write-Host "  [エラー] PyTorchのインストールに3回失敗しました" -ForegroundColor Red
    Write-Log "[エラー] PyTorchのインストールに3回失敗しました"
    Write-Host "  Bot起動時に自動的に再インストールを試みます" -ForegroundColor Yellow
    Write-Log "Bot起動時に自動的に再インストールを試みます"
    $script:ErrorCount++
}

# requirements.txt の残りのパッケージをインストール
$reqFile = Join-Path $InstallDir "requirements.txt"
if (Test-Path $reqFile) {
    Write-Running "その他の依存パッケージをインストールしています..."
    Write-Log "pip install -r $reqFile --no-cache-dir を実行します。"
    & "$InstallDir\venv\Scripts\pip.exe" install -r $reqFile --no-cache-dir 2>&1 | ForEach-Object {
        Write-Log "  pip: $_"
        if ($_ -match "Successfully installed|Requirement already satisfied|Downloading|Installing") {
            Write-Host "    $_" -ForegroundColor DarkGray
        }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [警告] 一部のパッケージのインストールに失敗しました" -ForegroundColor Yellow
        Write-Log "[警告] 一部のパッケージのインストールに失敗しました"
        $script:ErrorCount++
    } else {
        Write-Done "依存パッケージのインストールが完了しました"
        Write-Log "requirements.txt インストール完了。"
    }
} else {
    Write-Err "requirements.txt が見つかりません: $reqFile"
    Write-Log "requirements.txt が見つかりません。"
    Confirm-Continue "requirements.txt が見つかりません。続行しますか？ (Y/N)"
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ10: .envファイルの対話的設定
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Discord Bot の設定 (.envファイルの作成)"

$envFile     = Join-Path $InstallDir ".env"
$doCreateEnv = $true

if (Test-Path $envFile) {
    Write-Host ""
    Write-Host "  .env ファイルがすでに存在します。" -ForegroundColor Yellow
    $ow = Read-Host "  上書きしますか？ (Y/N) [N でスキップ]"
    if ($ow -notmatch '^[Yy]') {
        Write-Skip ".env ファイルの設定をスキップします。"
        Write-Log ".env ファイルは既存のものを使用します。"
        $doCreateEnv = $false
    }
}

if ($doCreateEnv) {
    Write-Host ""
    Write-Host "  Discord Bot の設定を行います。" -ForegroundColor White
    Write-Host ""
    Write-Host "  【Discord Bot トークンの取得方法】" -ForegroundColor Cyan
    Write-Host "  1. https://discord.com/developers/applications を開く" -ForegroundColor White
    Write-Host "  2. New Application でアプリを作成" -ForegroundColor White
    Write-Host "  3. 左メニューの Bot をクリック" -ForegroundColor White
    Write-Host "  4. Reset Token でトークンを取得" -ForegroundColor White
    Write-Host "  5. MESSAGE CONTENT INTENT を有効にする" -ForegroundColor White
    Write-Host ""

    $ob = Read-Host "  Discord Developer Portal を今すぐ開きますか？ (Y/N)"
    if ($ob -match '^[Yy]') {
        Start-Process "https://discord.com/developers/applications"
        Write-Host "  ブラウザを開きました。トークンを取得してからここに戻ってください。" -ForegroundColor Green
        Write-Host ""
        Read-Host "  準備ができたら Enter キーを押してください"
    }

    Write-Host ""
    $token = ""
    while ($token -eq "") {
        $token = Read-Host "  Discord Bot トークンを入力してください"
        if ($token -eq "") {
            Write-Host "  トークンを入力してください。" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "  【テキストチャンネルIDの取得方法】" -ForegroundColor Cyan
    Write-Host "  1. Discordの設定 → 詳細設定 → 開発者モード をON" -ForegroundColor White
    Write-Host "  2. 翻訳結果を送信したいテキストチャンネルを右クリック" -ForegroundColor White
    Write-Host "  3. チャンネルIDをコピー を選択" -ForegroundColor White
    Write-Host ""

    $channelId = ""
    while ($channelId -eq "") {
        $channelId = Read-Host "  テキストチャンネルID を入力してください"
        if ($channelId -eq "") {
            Write-Host "  チャンネルIDを入力してください。" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "  【サーバー（ギルド）IDの取得方法】" -ForegroundColor Cyan
    Write-Host "  ※ スラッシュコマンドを即時反映させるために必要です" -ForegroundColor Yellow
    Write-Host "  1. Discordの設定 → 詳細設定 → 開発者モード をON（上記と同じ）" -ForegroundColor White
    Write-Host "  2. Botを招待したサーバーのサーバー名（左サイドバー）を右クリック" -ForegroundColor White
    Write-Host "  3. IDをコピー を選択" -ForegroundColor White
    Write-Host "  ※ 未入力の場合はグローバルコマンドとして登録（反映に最大1時間かかります）" -ForegroundColor Gray
    Write-Host ""

    $guildId = Read-Host "  サーバーID を入力してください（スキップする場合はEnterキー）"
    if ($guildId -eq "") {
        Write-Host "  サーバーIDをスキップしました。スラッシュコマンドの反映に最大1時間かかる場合があります。" -ForegroundColor Yellow
        Write-Log "GUILD_ID 未入力。グローバルコマンドとして登録されます。"
    } else {
        Write-Done "サーバーID を設定しました: $guildId"
        Write-Log "GUILD_ID 設定済み: $guildId"
    }

    # .envファイルを配列で生成（ヒアストリング不使用）
    $envLines = @(
        "# AutoTrans Bot - 環境変数設定ファイル",
        "# setup.ps1 により自動生成されました",
        "",
        "# 必須設定",
        "",
        "# Discord Botトークン",
        "DISCORD_TOKEN=$token",
        "",
        "# 翻訳結果を送信するテキストチャンネルのID",
        "TEXT_CHANNEL_ID=$channelId",
        "",
        "# スラッシュコマンドを即時反映させるサーバーのID（推奨）",
        "# サーバー名を右クリック→「IDをコピー」で取得",
        "GUILD_ID=$guildId",
        "",
        "# オプション設定（デフォルト値で動作します）",
        "",
        "# OllamaサーバーのURL",
        "OLLAMA_BASE_URL=http://localhost:11434",
        "",
        "# 使用するOllamaモデル",
        "OLLAMA_MODEL=qwen2.5:7b-instruct",
        "",
        "# 使用するWhisperモデル",
        "WHISPER_MODEL=large-v3-turbo",
        "",
        "# VAD無音検知閾値（ミリ秒）",
        "VAD_SILENCE_THRESHOLD_MS=400",
        "",
        "# VAD発話判定閾値（0.0〜1.0）",
        "VAD_THRESHOLD=0.5"
    )

    try {
        $envLines | Set-Content -Path $envFile -Encoding UTF8
        Write-Done ".env ファイルを作成しました: $envFile"
        Write-Log ".env ファイルを作成しました。"
    } catch {
        Write-Err ".env ファイルの作成に失敗しました: $_"
        Write-Log ".env ファイル作成エラー: $_"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ11: Discord Bot をサーバーに追加
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "Discord Bot をサーバーに追加"

if ($doCreateEnv -and $token -ne "") {
    try {
        Write-Log "Discord Bot Application ID を取得しています..."

        $appId = $null

        try {
            $headers = @{
                "Authorization" = "Bot $token"
                "Content-Type"  = "application/json"
            }
            $response = Invoke-RestMethod -Uri "https://discord.com/api/v10/users/@me" `
                -Headers $headers -Method Get -ErrorAction Stop
            $appId   = $response.id
            $botName = $response.username
            Write-Done "Bot名: $botName (ID: $appId)"
        } catch {
            Write-Host "  [警告] Bot情報の自動取得に失敗しました: $_" -ForegroundColor Yellow
            Write-Log "[警告] Bot情報の自動取得に失敗しました: $_"
            Write-Host ""
            Write-Host "  Discord Developer Portal (https://discord.com/developers/applications)" -ForegroundColor Cyan
            Write-Host "  でアプリを選択し、「General Information」の「APPLICATION ID」をコピーしてください。" -ForegroundColor Cyan
            Write-Host ""
            $appId = Read-Host "  Application ID を入力してください（スキップする場合はEnter）"
        }

        if ($appId) {
            # 必要な権限のビットフラグ
            # Send Messages(2048) + Embed Links(16384) + Read Message History(65536)
            # + Connect(1048576) + Speak(2097152) + Use Voice Activity(33554432)
            $permissions = 2048 + 16384 + 65536 + 1048576 + 2097152 + 33554432
            # = 36784128

            # OAuth2招待URL生成
            $inviteUrl = "https://discord.com/oauth2/authorize?client_id=$appId&scope=bot+applications.commands&permissions=$permissions"

            Write-Host ""
            Write-Host "  ============================================" -ForegroundColor Cyan
            Write-Host "    Discord Bot をサーバーに追加します" -ForegroundColor Cyan
            Write-Host "  ============================================" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  ブラウザが自動的に開きます。" -ForegroundColor White
            Write-Host "  以下の手順でBotをサーバーに追加してください：" -ForegroundColor White
            Write-Host ""
            Write-Host "    1. ブラウザで開いたページで、追加したいサーバーを選択" -ForegroundColor Yellow
            Write-Host "    2. 「はい」をクリック" -ForegroundColor Yellow
            Write-Host "    3. 「認証」をクリック" -ForegroundColor Yellow
            Write-Host "    4. 「私はロボットではありません」にチェックを入れて完了" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "    ※ サーバーの「管理者」権限が必要です" -ForegroundColor Gray
            Write-Host ""
            Write-Host "  招待URL: $inviteUrl" -ForegroundColor DarkGray
            Write-Host ""

            # ブラウザで招待URLを開く
            Start-Process $inviteUrl

            Write-Host "  ブラウザでBotの追加が完了したら、Enterキーを押して続行してください..." -ForegroundColor Green
            Read-Host | Out-Null

            Write-Done "Bot招待URLをブラウザで開きました"
        } else {
            Write-Host "  [スキップ] Application IDが入力されなかったためスキップします" -ForegroundColor Cyan
            Write-Log "[スキップ] Application IDが入力されなかったためスキップします"
            Write-Host "  後で以下のURLにアクセスしてBotをサーバーに追加してください：" -ForegroundColor Yellow
            Write-Host "  https://discord.com/developers/applications" -ForegroundColor Cyan
        }
    } catch {
        Write-Err "Bot追加ステップでエラーが発生しました: $_"
        Write-Log "[エラー] Bot追加ステップでエラーが発生しました: $_"
    }
} else {
    Write-Host "  [スキップ] .env設定をスキップしたため、このステップもスキップします。" -ForegroundColor Cyan
    Write-Log "[スキップ] .env設定スキップのためBot追加ステップをスキップ。"
    Write-Host "  後で以下のURLにアクセスしてBotをサーバーに追加してください：" -ForegroundColor Yellow
    Write-Host "  https://discord.com/developers/applications" -ForegroundColor Cyan
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ12: デスクトップショートカットの作成
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "デスクトップショートカットの作成"

try {
    $desktopPath  = [System.Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktopPath "AutoTrans Bot 起動.lnk"
    $targetBat    = Join-Path $InstallDir "start_bot.bat"

    Write-Running "デスクトップにショートカットを作成しています..."

    $wsh      = New-Object -ComObject WScript.Shell
    $lnk      = $wsh.CreateShortcut($shortcutPath)
    $lnk.TargetPath       = $targetBat
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description      = "AutoTrans Discord翻訳Bot を起動します"
    $lnk.WindowStyle      = 1

    $psIcon = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    if (Test-Path $psIcon) {
        $lnk.IconLocation = $psIcon + ",0"
    }

    $lnk.Save()
    Write-Done "ショートカットを作成しました: $shortcutPath"
    Write-Log "ショートカット作成完了: $shortcutPath"
} catch {
    Write-Err "ショートカットの作成に失敗しました: $_"
    Write-Log "ショートカット作成エラー: $_"
    Write-Info "手動で $InstallDir\start_bot.bat のショートカットをデスクトップに作成してください。"
}

# ─────────────────────────────────────────────────────────────────────────────
# ステップ13: 完了メッセージ
# ─────────────────────────────────────────────────────────────────────────────
Write-StepHeader "セットアップ完了"

Write-Host ""
if ($script:ErrorCount -eq 0) {
    Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║         セットアップが完了しました！                  ║" -ForegroundColor Green
    Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
} else {
    Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "║   セットアップが完了しました（エラーあり）             ║" -ForegroundColor Yellow
    Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Yellow
    Write-Host ""
    $ec = $script:ErrorCount
    Write-Host "  $ec 件のエラーが発生しました。" -ForegroundColor Yellow
    Write-Host "  詳細は setup_log.txt を確認してください。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  インストール先: $InstallDir" -ForegroundColor White
Write-Host "  起動方法: デスクトップの「AutoTrans Bot 起動」をダブルクリック" -ForegroundColor White
Write-Host ""
Write-Host "  次のステップ：" -ForegroundColor White
Write-Host ""
Write-Host "  1. デスクトップの AutoTrans Bot 起動 をダブルクリック" -ForegroundColor Cyan
Write-Host "     または $InstallDir\start_bot.bat を実行してBotを起動" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Discordで /join コマンドを実行して" -ForegroundColor Cyan
Write-Host "     BotをボイスチャンネルにJoinさせる" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. 日本語または韓国語で話すと自動翻訳されます！" -ForegroundColor Cyan
Write-Host ""
Write-Host "  -----------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  用語を追加したい場合は dictionary.json を編集し、" -ForegroundColor Gray
Write-Host "  Discordで /reload_dict コマンドを実行してください。" -ForegroundColor Gray
Write-Host ""
Write-Host "  何かお困りの場合は SETUP.md を参照してください。" -ForegroundColor Gray
Write-Host "  -----------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

$et  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$ec2 = $script:ErrorCount
Write-Log "セットアップ完了。終了時刻: $et。エラー数: $ec2"

Write-Host "  Enterキーを押して終了します..." -ForegroundColor DarkGray
Read-Host | Out-Null