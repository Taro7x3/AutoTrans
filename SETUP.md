# AutoTrans Bot — セットアップガイド

Discord上でオーバーウォッチの日韓リアルタイム音声翻訳を行うBotの導入手順書です。

---

## 目次

1. [前提条件](#1-前提条件)
2. [Ollamaのインストールとモデルのダウンロード](#2-ollamaのインストールとモデルのダウンロード)
3. [FFmpegのインストール](#3-ffmpegのインストール)
4. [Python仮想環境の構築](#4-python仮想環境の構築)
5. [Discord Botの作成と設定](#5-discord-botの作成と設定)
6. [.envファイルの設定](#6-envファイルの設定)
7. [faster-whisperモデルのダウンロード](#7-faster-whisperモデルのダウンロード)
8. [起動方法](#8-起動方法)
9. [使い方](#9-使い方)
10. [トラブルシューティング](#10-トラブルシューティング)

---

## 1. 前提条件

以下のハードウェア・ソフトウェアが必要です。

### ハードウェア

| 項目 | 最小要件 | 推奨 |
|------|----------|------|
| GPU | NVIDIA GPU (VRAM 6GB以上) | RTX 3070 / RTX 4070 以上 (VRAM 8GB以上) |
| RAM | 16GB | 32GB以上 |
| ストレージ | 20GB以上の空き容量 | SSD推奨 |

> **注意:** `large-v3-turbo` モデルはVRAM約6GBを使用します。Ollamaの `qwen2.5:7b-instruct` はVRAM約5GBを使用します。合計で約11GB以上のVRAMが必要です。VRAM不足の場合は[トラブルシューティング](#10-トラブルシューティング)を参照してください。

### ソフトウェア

- **OS:** Windows 10/11 または Ubuntu 20.04/22.04/24.04
- **NVIDIA ドライバー:** CUDA 12.x 対応版（ドライバーバージョン 525.60.13以上）
- **Python:** 3.10 〜 3.12（3.11推奨）
- **Git:** 最新版

### CUDAドライバーの確認

```bash
nvidia-smi
```

出力例:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 537.13       Driver Version: 537.13       CUDA Version: 12.2    |
+-----------------------------------------------------------------------------+
```

`CUDA Version: 12.x` と表示されていれば問題ありません。

---

## 2. Ollamaのインストールとモデルのダウンロード

Ollamaはローカルでの大規模言語モデル実行環境です。

### Windows へのインストール

1. [https://ollama.com/download](https://ollama.com/download) にアクセス
2. **Windows** 用インストーラーをダウンロードして実行
3. インストール完了後、タスクトレイにOllamaアイコンが表示されます

または、wingetを使用:

```powershell
winget install Ollama.Ollama
```

### Linux へのインストール

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

インストール後、サービスを起動:

```bash
sudo systemctl start ollama
sudo systemctl enable ollama  # 自動起動を有効化
```

### 翻訳モデルのダウンロード

Ollamaが起動している状態で以下を実行します:

```bash
ollama pull qwen2.5:7b-instruct
```

> ダウンロードサイズ: 約4.7GB。完了まで数分〜数十分かかります。

ダウンロード確認:

```bash
ollama list
```

出力例:
```
NAME                       ID              SIZE    MODIFIED
qwen2.5:7b-instruct        ...             4.7 GB  ...
```

### Ollamaの動作確認

```bash
ollama run qwen2.5:7b-instruct "こんにちは"
```

応答が返ってくれば正常です。`Ctrl+D` で終了します。

---

## 3. FFmpegのインストール

py-cord の音声機能にFFmpegが必要です。

### Windows

**方法1: winget（推奨）**

```powershell
winget install Gyan.FFmpeg
```

**方法2: 手動インストール**

1. [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) → Windows builds → [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) にアクセス
2. `ffmpeg-release-essentials.zip` をダウンロード
3. `C:\ffmpeg\` に展開
4. `C:\ffmpeg\bin` をシステムのPATHに追加:
   - スタートメニュー → 「環境変数を編集」を検索
   - 「システム環境変数」→「Path」→「編集」→「新規」
   - `C:\ffmpeg\bin` を追加して「OK」

**インストール確認:**

```powershell
ffmpeg -version
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y ffmpeg
```

**インストール確認:**

```bash
ffmpeg -version
```

---

## 4. Python仮想環境の構築

### リポジトリのクローン（または既存ディレクトリへ移動）

```bash
git clone https://github.com/Taro7x3/AutoTrans.git
cd AutoTrans
```

### 仮想環境の作成と有効化

**Windows:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> PowerShellで実行ポリシーエラーが出る場合:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Linux/Mac:**

```bash
python3 -m venv venv
source venv/bin/activate
```

仮想環境が有効化されると、プロンプトに `(venv)` が表示されます。

### PyTorch CUDA版のインストール（最重要）

> **必ずこのステップを先に実行してください。** `requirements.txt` より前にインストールする必要があります。

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

> CUDA 12.4以降を使用している場合は `cu124` に変更してください:
> ```bash
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
> ```

インストール確認:

```python
python -c "import torch; print(torch.cuda.is_available()); print(torch.version.cuda)"
```

出力例:
```
True
12.1
```

### 残りの依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### Silero VADのキャッシュ事前ダウンロード（オプション）

初回起動時に自動ダウンロードされますが、事前にダウンロードしておく場合:

```python
python -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"
```

---

## 5. Discord Botの作成と設定

### Discord Developer Portalでのアプリ作成

1. [https://discord.com/developers/applications](https://discord.com/developers/applications) にアクセス
2. 右上の **「New Application」** をクリック
3. アプリ名（例: `AutoTrans`）を入力して **「Create」**

### Botの設定

1. 左メニューの **「Bot」** をクリック
2. **「Add Bot」** → **「Yes, do it!」**
3. 以下のIntentsを有効化:
   - ✅ **SERVER MEMBERS INTENT**
   - ✅ **MESSAGE CONTENT INTENT**
4. **「Save Changes」** をクリック

### Botトークンの取得

1. **「Bot」** ページの **「Token」** セクション
2. **「Reset Token」** → **「Yes, do it!」**
3. 表示されたトークンをコピーして安全な場所に保存

> ⚠️ **トークンは絶対に公開しないでください。** GitHubにアップロードしないよう注意してください。

### BotをサーバーへのOAuth2 URL生成

1. 左メニューの **「OAuth2」** → **「URL Generator」**
2. **Scopes** で以下を選択:
   - ✅ `bot`
   - ✅ `applications.commands`
3. **Bot Permissions** で以下を選択:
   - ✅ `Read Messages/View Channels`
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Connect`（ボイスチャンネル接続）
   - ✅ `Speak`（ボイスチャンネル発話）
   - ✅ `Use Voice Activity`
4. 生成されたURLをブラウザで開き、Botを招待するサーバーを選択

### テキストチャンネルIDの取得

1. Discordの設定 → 「詳細設定」→「開発者モード」をON
2. 翻訳結果を送信したいテキストチャンネルを右クリック
3. **「チャンネルIDをコピー」** をクリック

---

## 6. `.env` ファイルの設定

プロジェクトルートに `.env` ファイルを作成します。

### `.env.example`

```env
# ─────────────────────────────────────────────
# 必須設定
# ─────────────────────────────────────────────

# Discord Botトークン（Developer Portalから取得）
DISCORD_TOKEN=your_discord_bot_token_here

# 翻訳結果を送信するテキストチャンネルのID
TEXT_CHANNEL_ID=123456789012345678

# ─────────────────────────────────────────────
# オプション設定（デフォルト値で動作します）
# ─────────────────────────────────────────────

# OllamaサーバーのURL（デフォルト: http://localhost:11434）
# OLLAMA_BASE_URL=http://localhost:11434

# 使用するOllamaモデル（デフォルト: qwen2.5:7b-instruct）
# OLLAMA_MODEL=qwen2.5:7b-instruct

# 使用するWhisperモデル（デフォルト: large-v3-turbo）
# WHISPER_MODEL=large-v3-turbo

# VAD無音検知閾値（ミリ秒）（デフォルト: 400）
# VAD_SILENCE_THRESHOLD_MS=400

# VAD発話判定閾値（0.0〜1.0）（デフォルト: 0.5）
# VAD_THRESHOLD=0.5
```

### `.env` ファイルの作成手順

**Windows:**

```powershell
Copy-Item .env.example .env
notepad .env
```

**Linux:**

```bash
cp .env.example .env
nano .env
```

`DISCORD_TOKEN` と `TEXT_CHANNEL_ID` を実際の値に書き換えて保存してください。

> ⚠️ `.env` ファイルは `.gitignore` に追加してGitで管理しないようにしてください。

---

## 7. faster-whisperモデルのダウンロード

### 自動ダウンロード（推奨）

`bot.py` を初回起動すると、`large-v3-turbo` モデルが自動的にダウンロードされます。

- **ダウンロードサイズ:** 約1.6GB
- **キャッシュ先:** `~/.cache/huggingface/hub/`（Windows: `C:\Users\<ユーザー名>\.cache\huggingface\hub\`）

### 手動ダウンロード（オプション）

オフライン環境や事前ダウンロードが必要な場合:

```bash
pip install huggingface_hub
python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='Systran/faster-whisper-large-v3-turbo',
    local_dir='./models/faster-whisper-large-v3-turbo'
)
"
```

手動ダウンロードしたモデルを使用する場合は `.env` に以下を追加:

```env
WHISPER_MODEL=./models/faster-whisper-large-v3-turbo
```

---

## 8. 起動方法

### 起動コマンド

仮想環境が有効化されていることを確認してから実行:

```bash
python bot.py
```

### 正常起動時のログ出力例

```
2024-01-15 10:00:00 [INFO] AutoTrans: ============================================================
2024-01-15 10:00:00 [INFO] AutoTrans: AutoTrans Bot 起動中...
2024-01-15 10:00:00 [INFO] AutoTrans: ============================================================
2024-01-15 10:00:00 [INFO] AutoTrans: Silero VADモデルをロード中...
2024-01-15 10:00:03 [INFO] AutoTrans: Silero VADモデルロード完了 | device=cuda
2024-01-15 10:00:03 [INFO] AutoTrans: faster-whisperモデルをロード中... (model=large-v3-turbo)
2024-01-15 10:00:15 [INFO] AutoTrans: faster-whisperモデルロード完了 | model=large-v3-turbo | device=cuda | compute_type=float16
2024-01-15 10:00:15 [INFO] AutoTrans: aiohttp.ClientSession作成完了 | Ollama URL: http://localhost:11434
2024-01-15 10:00:15 [INFO] AutoTrans: Ollama接続確認OK | model=qwen2.5:7b-instruct
2024-01-15 10:00:15 [INFO] AutoTrans: Discord Botを起動します...
2024-01-15 10:00:17 [INFO] AutoTrans: Bot起動完了 | ユーザー名: AutoTrans#1234 | ID: 987654321098765432
2024-01-15 10:00:17 [INFO] AutoTrans: 接続サーバー数: 1
2024-01-15 10:00:17 [INFO] AutoTrans: 翻訳ワーカータスク起動完了
```

### バックグラウンド実行（Linux）

```bash
nohup python bot.py > autotrans.log 2>&1 &
echo $! > bot.pid
```

停止する場合:

```bash
kill $(cat bot.pid)
```

---

## 9. 使い方

### Botをボイスチャンネルに参加させる

1. Discordで翻訳したいボイスチャンネルに参加する
2. テキストチャンネルで `/join` コマンドを実行する
3. Botが同じボイスチャンネルに参加し、翻訳を開始する

```
✅ 一般 に参加しました。翻訳を開始します。
翻訳結果は #翻訳チャンネル に送信されます。
```

### 翻訳の動作確認

1. ボイスチャンネルで日本語または韓国語を話す
2. 約400ms（デフォルト）の無音後、翻訳処理が開始される
3. 翻訳結果が設定したテキストチャンネルに送信される

**出力例（日本語 → 韓国語）:**

```
AutoTransUser [JA ⇒ KO]:

ナノ使うよ、前に出て！

┌─────────────────────────────┐
│ **뽕 쓸게, 앞으로 나와!**   │  ← 緑色のEmbed
└─────────────────────────────┘
```

**出力例（韓国語 → 日本語）:**

```
KoreanPlayer [KO ⇒ JA]:

힐밴 조심해!

┌─────────────────────────────┐
│ **阻害に気をつけて！**       │  ← 青色のEmbed
└─────────────────────────────┘
```

### Botをボイスチャンネルから退出させる

```
/leave
```

```
👋 一般 から退出しました。翻訳を停止しました。
```

---

## 10. トラブルシューティング

### CUDAが認識されない場合

**症状:** `torch.cuda.is_available()` が `False` を返す

**対処法:**

1. NVIDIAドライバーのバージョン確認:
   ```bash
   nvidia-smi
   ```
   `CUDA Version: 12.x` が表示されない場合はドライバーを更新してください。

2. PyTorchのCUDAバージョンとドライバーの対応確認:
   ```python
   import torch
   print(torch.__version__)        # 例: 2.5.1+cu121
   print(torch.version.cuda)       # 例: 12.1
   ```

3. CUDA 12.4以降の場合は `cu124` でインストール:
   ```bash
   pip uninstall torch torchaudio
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
   ```

4. Windowsの場合、Visual C++ 再頒布可能パッケージが必要な場合があります:
   [https://aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

### Ollamaに接続できない場合

**症状:** `Ollama接続確認失敗` のログが出る / 翻訳が実行されない

**対処法:**

1. Ollamaが起動しているか確認:
   ```bash
   # Windows
   tasklist | findstr ollama

   # Linux
   systemctl status ollama
   ```

2. Ollamaを手動起動:
   ```bash
   ollama serve
   ```

3. ポート11434が使用可能か確認:
   ```bash
   # Windows
   netstat -ano | findstr 11434

   # Linux
   ss -tlnp | grep 11434
   ```

4. ファイアウォールの設定を確認（ローカル接続のみなので通常は不要）

5. モデルが正しくダウンロードされているか確認:
   ```bash
   ollama list
   ```

---

### 音声が受信されない場合

**症状:** VCに参加しているのに翻訳が実行されない

**対処法:**

1. FFmpegが正しくインストールされているか確認:
   ```bash
   ffmpeg -version
   ```

2. BotのVoice Intentsが有効か確認:
   - Discord Developer Portal → Bot → 「GUILD VOICE STATES INTENT」が有効になっているか

3. BotがVCに参加できているか確認:
   - `/join` コマンド後にBotがVCに表示されているか

4. VAD閾値を調整する（感度が低い場合）:
   ```env
   VAD_THRESHOLD=0.3
   VAD_SILENCE_THRESHOLD_MS=300
   ```

5. ログレベルをDEBUGに変更して詳細を確認:
   `bot.py` の `logging.basicConfig` の `level` を `logging.DEBUG` に変更

---

### メモリ不足エラーの対処法

**症状:** `CUDA out of memory` エラー

**対処法:**

1. **Whisperモデルを小さくする:**
   ```env
   WHISPER_MODEL=medium
   ```
   モデルサイズとVRAM使用量の目安:
   | モデル | VRAM |
   |--------|------|
   | `large-v3-turbo` | ~6GB |
   | `medium` | ~3GB |
   | `small` | ~1.5GB |
   | `base` | ~0.7GB |

2. **OllamaをCPUで実行する:**
   ```bash
   OLLAMA_NUM_GPU=0 ollama serve
   ```
   ※ 速度は低下しますが、VRAMを節約できます。

3. **compute_typeをint8に変更する:**
   `bot.py` の `initialize_whisper_model()` 内の `compute_type` を `"int8"` に変更:
   ```python
   compute_type = "int8"  # float16 → int8 に変更
   ```

4. **Ollamaモデルを小さくする:**
   ```bash
   ollama pull qwen2.5:3b-instruct
   ```
   `.env` を更新:
   ```env
   OLLAMA_MODEL=qwen2.5:3b-instruct
   ```

---

### その他のよくある問題

**`py-cord` と `discord.py` の競合:**

```bash
pip uninstall discord.py discord py-cord
pip install py-cord[voice]
```

**`silero-vad` のダウンロードが失敗する:**

プロキシ環境下の場合、環境変数を設定:
```bash
# Windows
set HTTPS_PROXY=http://proxy.example.com:8080

# Linux
export HTTPS_PROXY=http://proxy.example.com:8080
```

または、torch.hubのキャッシュディレクトリを確認:
```python
import torch
print(torch.hub.get_dir())
```

**スラッシュコマンドが表示されない:**

Botを招待する際に `applications.commands` スコープが含まれているか確認してください。
コマンドが反映されるまで最大1時間かかる場合があります（グローバルコマンドの場合）。

---

## 付録: 推奨システム構成

| コンポーネント | 推奨スペック |
|---------------|-------------|
| GPU | NVIDIA RTX 3070 / RTX 4070 (VRAM 8GB) |
| CPU | Intel Core i7 / AMD Ryzen 7 以上 |
| RAM | 32GB |
| ストレージ | NVMe SSD 50GB以上の空き |
| OS | Windows 11 / Ubuntu 22.04 LTS |
| Python | 3.11.x |
| CUDA | 12.1 〜 12.4 |

---

## 用語辞書のカスタマイズ

`dictionary.json` を編集することで、翻訳に使用する専門用語を自由に追加・変更できます。

### 辞書ファイルの構造

- `ja_to_ko`: 日本語→韓国語の用語マッピング
- `ko_to_ja`: 韓国語→日本語の用語マッピング

### 用語の追加方法

1. `dictionary.json` をテキストエディタで開く
2. 対応するセクションにキーと値を追加する
   ```json
   "ja_to_ko": {
     "新しい用語": "새로운 용어"
   }
   ```
3. ファイルを保存する
4. Discordで `/reload_dict` コマンドを実行して即時反映（再起動不要）

### 注意事項

- JSONの構文エラーがあると読み込みに失敗します。編集後は [JSONLint](https://jsonlint.com/) などで検証してください
- `_comment` と `_instructions` キーはシステム用です。削除しないでください
