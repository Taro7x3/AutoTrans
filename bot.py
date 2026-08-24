"""
AutoTrans Bot - Discord 音声翻訳Bot
====================================
py-cord[voice] + Silero VAD + faster-whisper + Ollama (qwen2.5:7b-instruct) を使用した
日韓リアルタイム音声翻訳Botです。

アーキテクチャ概要:
  1. VADSink: Discord音声パケットを受信 → Silero VADで発話区間を検出 → asyncio.Queueに投入
  2. TranslationWorker: Queueからチャンクを取り出し → faster-whisper(STT) → Ollama(翻訳) → Discord送信
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from discord.voice import VoiceData

import aiohttp
import discord
import numpy as np
import torch
from dotenv import load_dotenv
from faster_whisper import WhisperModel

# ─────────────────────────────────────────────
# 環境変数の読み込み
# ─────────────────────────────────────────────
load_dotenv()

# ─────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AutoTrans")

# ─────────────────────────────────────────────
# 設定値（環境変数 or デフォルト値）
# ─────────────────────────────────────────────
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
TEXT_CHANNEL_ID: int = int(os.environ["TEXT_CHANNEL_ID"])
GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")

# VAD設定
VAD_SILENCE_THRESHOLD_MS: int = int(os.getenv("VAD_SILENCE_THRESHOLD_MS", "400"))
VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))

# py-cordから受信する音声フォーマット
DISCORD_SAMPLE_RATE: int = 48000   # 48kHz
DISCORD_CHANNELS: int = 2          # ステレオ
DISCORD_SAMPLE_WIDTH: int = 2      # 16bit = 2bytes

# Silero VADが期待する音声フォーマット
VAD_SAMPLE_RATE: int = 16000       # 16kHz
VAD_CHUNK_SAMPLES: int = 512       # Silero VADの推奨チャンクサイズ（16kHz時）

# ─────────────────────────────────────────────
# カスタム用語辞書
# ─────────────────────────────────────────────
DICTIONARY: dict = {"ja_to_ko": {}, "ko_to_ja": {}}


def load_dictionary(path: str = "dictionary.json") -> dict:
    """
    dictionary.json を読み込み、用語マッピングを返す。
    ファイルが存在しない場合はデフォルト値を返す。

    Args:
        path: 辞書ファイルのパス

    Returns:
        {"ja_to_ko": {...}, "ko_to_ja": {...}} 形式の辞書
    """
    default: dict = {"ja_to_ko": {}, "ko_to_ja": {}}

    if not os.path.exists(path):
        logger.warning("辞書ファイルが見つかりません: %s（空の辞書を使用します）", path)
        return default

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        ja_to_ko: dict = data.get("ja_to_ko", {})
        ko_to_ja: dict = data.get("ko_to_ja", {})

        logger.info(
            "辞書読み込み完了 | JA→KO: %d語, KO→JA: %d語",
            len(ja_to_ko),
            len(ko_to_ja),
        )
        return {"ja_to_ko": ja_to_ko, "ko_to_ja": ko_to_ja}

    except json.JSONDecodeError as e:
        logger.error("辞書ファイルのJSONパースエラー: %s（空の辞書を使用します）", e)
        return default
    except OSError as e:
        logger.error("辞書ファイルの読み込みエラー: %s（空の辞書を使用します）", e)
        return default


def build_system_prompt(direction: str, dictionary: dict) -> str:
    """
    翻訳方向（'ja_to_ko' または 'ko_to_ja'）と辞書データから
    LLMシステムプロンプトを動的に生成する。

    Args:
        direction: 翻訳方向。'ja_to_ko'、'ko_to_ja'、またはその他の文字列
        dictionary: load_dictionary() が返す辞書データ

    Returns:
        LLMに渡すシステムプロンプト文字列
    """
    if direction == "ja_to_ko":
        direction_label = "日本語→韓国語"
        terms = dictionary.get("ja_to_ko", {})
        term_lines = "\n".join(f"  - {k} → {v}" for k, v in terms.items())
        term_section = f"\n{term_lines}" if term_lines else "\n  （登録用語なし）"
        return (
            f"あなたはFPSゲーム「オーバーウォッチ」の{direction_label}翻訳専門家です。\n"
            "以下のルールを厳守してください：\n"
            "1. ゲーム内コールは短く簡潔に翻訳する（1〜2語が理想）\n"
            "2. 以下の専門用語マッピングを優先的に使用する："
            f"{term_section}\n"
            "3. 翻訳結果のみを出力し、説明や注釈は一切付けない\n"
            "4. 原文のニュアンスと緊急感を保つ"
        )

    elif direction == "ko_to_ja":
        direction_label = "韓国語→日本語"
        terms = dictionary.get("ko_to_ja", {})
        term_lines = "\n".join(f"  - {k} → {v}" for k, v in terms.items())
        term_section = f"\n{term_lines}" if term_lines else "\n  （登録用語なし）"
        return (
            f"あなたはFPSゲーム「オーバーウォッチ」の{direction_label}翻訳専門家です。\n"
            "以下のルールを厳守してください：\n"
            "1. ゲーム内コールは短く簡潔に翻訳する（1〜2語が理想）\n"
            "2. 以下の専門用語マッピングを優先的に使用する："
            f"{term_section}\n"
            "3. 翻訳結果のみを出力し、説明や注釈は一切付けない\n"
            "4. 原文のニュアンスと緊急感を保つ"
        )

    else:
        # その他の言語 → 日本語
        return (
            "You are a translation expert for the FPS game 'Overwatch'.\n"
            "Translate short game calls from voice chat into natural Japanese.\n"
            "\n"
            "Rules:\n"
            "1. Keep translations short and natural for in-game voice communication\n"
            "2. Avoid verbose expressions; use concise language actually used in VC\n"
            "3. Keep proper nouns (hero names, map names) as-is\n"
            "4. Output only the translation result. No explanations or annotations needed."
        )


# ─────────────────────────────────────────────
# グローバルモデルインスタンス（on_ready内で初期化）
# ─────────────────────────────────────────────
vad_model: Optional[torch.nn.Module] = None
whisper_model: Optional[WhisperModel] = None
http_session: Optional[aiohttp.ClientSession] = None
models_loaded: bool = False  # on_ready再呼び出し時の二重ロード防止フラグ


# ─────────────────────────────────────────────
# VADSink: Discord音声受信 + Silero VAD統合
# ─────────────────────────────────────────────
class VADSink(discord.sinks.Sink):
    """
    py-cordのカスタムSink。
    受信した音声パケットをSilero VADでリアルタイム監視し、
    発話区間を検出してasyncio.Queueに投入する。

    音声フォーマット変換:
      Discord受信: 48kHz, stereo, 16bit PCM
      → Silero VAD入力: 16kHz, mono, float32

    py-cord master (DAVE対応) ブランチでは voice/receive/router.py の
    SinkEventRouter が __sink_listeners__ と walk_children() を参照するため、
    これらをクラス変数・メソッドとして定義する必要がある。
    """

    # py-cord master の SinkEventRouter が参照するクラス変数。
    # 形式: list[tuple[event_name, method_name]]
    # イベントリスナーを登録しない場合は空リストでよい。
    __sink_listeners__: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(filters=None)
        self.client = None  # VoiceClientへの参照（start_recording後に手動設定）
        self.queue = queue
        self.loop = loop

        # ユーザーごとの状態管理
        # key: user_id (int)
        # value: dict with keys:
        #   "buffer"        : list[np.ndarray] — 16kHz mono float32の音声チャンク蓄積バッファ
        #   "vad_buffer"    : list[np.ndarray] — VAD判定用の未処理サンプル蓄積
        #   "is_speaking"   : bool             — 現在発話中かどうか
        #   "silence_start" : float | None     — 無音開始時刻（time.monotonic()）
        #   "display_name"  : str              — Discordの表示名
        self._user_states: dict[int, dict] = defaultdict(lambda: {
            "buffer": [],
            "vad_buffer": [],
            "is_speaking": False,
            "silence_start": None,
            "display_name": "Unknown",
        })

        # 無音判定閾値（秒）
        self._silence_threshold_sec: float = VAD_SILENCE_THRESHOLD_MS / 1000.0

        logger.info(
            "VADSink初期化完了 | 無音閾値: %dms | VAD閾値: %.2f",
            VAD_SILENCE_THRESHOLD_MS,
            VAD_THRESHOLD,
        )

    def write(self, data: "VoiceData", user) -> None:
        """
        py-cordが音声パケットを受信するたびに呼び出されるメソッド。
        PCMデータをVADで処理し、発話区間を検出する。

        Args:
            data: 受信した音声データ（VoiceData: .pcm に48kHz stereo 16bit PCMバイト列）
            user: 発話しているDiscordユーザー（User | Member | None）
        """
        if vad_model is None:
            return

        # py-cord 2.8.1: userはNoneの場合がある（SSRCとユーザーの紐付けが未完了）
        if user is None:
            return

        user_id = user.id
        state = self._user_states[user_id]
        state["display_name"] = getattr(user, "display_name", str(user_id))

        # ── Step 1: 48kHz stereo 16bit PCM → 16kHz mono float32 に変換 ──
        # py-cord 2.8.1: PCMデータは data.pcm (bytes) でアクセス
        pcm_bytes = data.pcm
        if len(pcm_bytes) == 0:
            return

        try:
            # bytes → numpy int16配列
            samples_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)

            # stereo → mono（左右チャンネルの平均）
            if DISCORD_CHANNELS == 2 and len(samples_int16) % 2 == 0:
                # インターリーブされたステレオ: [L, R, L, R, ...]
                samples_int16 = samples_int16.reshape(-1, 2).mean(axis=1).astype(np.int16)

            # int16 → float32 (-1.0 〜 1.0 に正規化)
            samples_float32 = samples_int16.astype(np.float32) / 32768.0

            # 48kHz → 16kHz ダウンサンプリング（3分の1に間引き）
            # 簡易ダウンサンプリング: 3サンプルごとに1サンプルを取得
            downsample_ratio = DISCORD_SAMPLE_RATE // VAD_SAMPLE_RATE  # = 3
            samples_16k = samples_float32[::downsample_ratio]

        except Exception as e:
            logger.error("音声フォーマット変換エラー (user_id=%d): %s", user_id, e)
            return

        # ── Step 2: VAD判定用バッファに蓄積 ──
        state["vad_buffer"].append(samples_16k)

        # VAD_CHUNK_SAMPLES (512サンプル = 32ms @ 16kHz) 分溜まったら判定
        vad_buf_concat = np.concatenate(state["vad_buffer"])

        while len(vad_buf_concat) >= VAD_CHUNK_SAMPLES:
            chunk = vad_buf_concat[:VAD_CHUNK_SAMPLES]
            vad_buf_concat = vad_buf_concat[VAD_CHUNK_SAMPLES:]

            # ── Step 3: Silero VADで発話確率を計算 ──
            try:
                chunk_tensor = torch.from_numpy(chunk).unsqueeze(0)  # shape: (1, 512)
                with torch.no_grad():
                    speech_prob = vad_model(chunk_tensor, VAD_SAMPLE_RATE).item()
            except Exception as e:
                logger.error("VAD推論エラー (user_id=%d): %s", user_id, e)
                continue

            is_speech = speech_prob >= VAD_THRESHOLD

            if is_speech:
                # 発話中: バッファに追加、無音タイマーをリセット
                state["buffer"].append(chunk)
                state["is_speaking"] = True
                state["silence_start"] = None
            else:
                # 無音区間
                if state["is_speaking"]:
                    # 発話後の無音: タイマー開始
                    if state["silence_start"] is None:
                        state["silence_start"] = time.monotonic()

                    elapsed_silence = time.monotonic() - state["silence_start"]

                    if elapsed_silence >= self._silence_threshold_sec:
                        # ── Step 4: 発話終了を検出 → Queueに投入 ──
                        if state["buffer"]:
                            audio_data = np.concatenate(state["buffer"])
                            payload = {
                                "user_id": user_id,
                                "display_name": state["display_name"],
                                "audio_data": audio_data.tobytes(),
                                "sample_rate": VAD_SAMPLE_RATE,
                            }
                            # スレッドセーフにQueueへ投入
                            asyncio.run_coroutine_threadsafe(
                                self.queue.put(payload),
                                self.loop,
                            )
                            logger.debug(
                                "発話終了検出 → Queue投入 | user=%s | 音声長=%.2fs",
                                state["display_name"],
                                len(audio_data) / VAD_SAMPLE_RATE,
                            )

                        # バッファと状態をリセット
                        state["buffer"] = []
                        state["is_speaking"] = False
                        state["silence_start"] = None

        # 残りのVADバッファを保持（次のパケットと結合するため）
        state["vad_buffer"] = [vad_buf_concat] if len(vad_buf_concat) > 0 else []

    def cleanup(self) -> None:
        """Sink終了時のクリーンアップ処理"""
        self._user_states.clear()
        logger.info("VADSinkクリーンアップ完了")

    def walk_children(self):
        """
        py-cord master の SinkEventRouter が参照するメソッド。
        子Sinkが存在しない場合は空のイテレータを返す。
        """
        return iter([])

    def is_opus(self) -> bool:
        """OpusではなくPCMデータを受け取る（py-cord master API）"""
        return False


# ─────────────────────────────────────────────
# Ollama APIクライアント
# ─────────────────────────────────────────────
async def translate_with_ollama(
    text: str,
    source_lang: str,
    session: aiohttp.ClientSession,
) -> str:
    """
    Ollama APIを使用してテキストを翻訳する非同期関数。

    Args:
        text: 翻訳するテキスト
        source_lang: 検出された言語コード（"ja", "ko", その他）
        session: aiohttp.ClientSession

    Returns:
        翻訳されたテキスト
    """
    # 言語に応じてシステムプロンプトとユーザープロンプトを選択
    if source_lang == "ja":
        system_prompt = build_system_prompt("ja_to_ko", DICTIONARY)
        user_prompt = f"次の日本語ゲームコールを韓国語に翻訳してください:\n{text}"
    elif source_lang == "ko":
        system_prompt = build_system_prompt("ko_to_ja", DICTIONARY)
        user_prompt = f"다음 한국어 게임 콜을 일본어로 번역해주세요:\n{text}"
    else:
        system_prompt = build_system_prompt("other", DICTIONARY)
        user_prompt = f"Translate the following game call to Japanese:\n{text}"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,  # 翻訳の一貫性を高めるため低めに設定
            "num_predict": 200,  # ゲームコールは短いので上限を設定
        },
    }

    url = f"{OLLAMA_BASE_URL}/api/chat"

    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            result = await resp.json()
            translated = result["message"]["content"].strip()
            return translated
    except aiohttp.ClientError as e:
        logger.error("Ollama APIエラー: %s", e)
        raise
    except (KeyError, TypeError) as e:
        logger.error("Ollamaレスポンスのパースエラー: %s", e)
        raise


# ─────────────────────────────────────────────
# STT処理（faster-whisper）
# ─────────────────────────────────────────────
def transcribe_audio(audio_bytes: bytes, sample_rate: int) -> tuple[str, str]:
    """
    faster-whisperを使用して音声をテキストに変換する同期関数。
    asyncio.to_thread()で別スレッドから呼び出される。

    Args:
        audio_bytes: 16kHz mono float32 PCMのバイト列
        sample_rate: サンプルレート（16000）

    Returns:
        (transcribed_text, detected_language) のタプル
    """
    if whisper_model is None:
        raise RuntimeError("Whisperモデルが初期化されていません")

    # bytes → numpy float32配列
    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

    # faster-whisperで文字起こし
    # language=None で自動検出
    segments, info = whisper_model.transcribe(
        audio_array,
        language=None,          # 言語自動検出
        beam_size=5,
        vad_filter=False,       # VADはSileroで既に実施済み
        word_timestamps=False,
    )

    # セグメントを結合してテキストを生成
    text = " ".join(seg.text.strip() for seg in segments).strip()
    detected_lang = info.language  # 例: "ja", "ko", "en"

    return text, detected_lang


# ─────────────────────────────────────────────
# 翻訳方向の決定
# ─────────────────────────────────────────────
def get_translation_direction(source_lang: str) -> tuple[str, str, discord.Color]:
    """
    検出言語から翻訳方向と表示用ラベルを決定する。

    Args:
        source_lang: 検出された言語コード

    Returns:
        (direction_label, target_lang, embed_color) のタプル
        例: ("JA ⇒ KO", "ko", discord.Color.brand_green())
    """
    if source_lang == "ja":
        return "JA ⇒ KO", "ko", discord.Color.brand_green()
    elif source_lang == "ko":
        return "KO ⇒ JA", "ja", discord.Color.blue()
    else:
        lang_upper = source_lang.upper()
        return f"{lang_upper} ⇒ JA", "ja", discord.Color.og_blurple()


# ─────────────────────────────────────────────
# 翻訳ワーカータスク
# ─────────────────────────────────────────────
async def translation_worker(
    queue: asyncio.Queue,
    bot: discord.Bot,
) -> None:
    """
    asyncio.Queueから音声チャンクを取り出し、STT → 翻訳 → Discord送信を行う
    完全非同期ワーカータスク。

    処理フロー:
      1. Queueから音声ペイロードを取得
      2. faster-whisperでSTT（asyncio.to_thread()で別スレッド実行）
      3. Ollama APIで翻訳（aiohttp非同期リクエスト）
      4. Discordテキストチャンネルに結果を送信
    """
    logger.info("翻訳ワーカー起動")

    while True:
        try:
            # ── Step 1: Queueから音声ペイロードを取得 ──
            payload: dict = await queue.get()
            user_id: int = payload["user_id"]
            display_name: str = payload["display_name"]
            audio_bytes: bytes = payload["audio_data"]
            sample_rate: int = payload["sample_rate"]

            logger.info(
                "処理開始 | user=%s | 音声サイズ=%d bytes",
                display_name,
                len(audio_bytes),
            )

            # ── Step 2: STT（faster-whisper）— 別スレッドで実行 ──
            try:
                text, detected_lang = await asyncio.to_thread(
                    transcribe_audio,
                    audio_bytes,
                    sample_rate,
                )
                logger.info(
                    "STT完了 | user=%s | lang=%s | text='%s'",
                    display_name,
                    detected_lang,
                    text,
                )
            except Exception as e:
                logger.error("STTエラー | user=%s: %s", display_name, e)
                queue.task_done()
                continue

            # 空文字の場合はスキップ
            if not text:
                logger.debug("STT結果が空のためスキップ | user=%s", display_name)
                queue.task_done()
                continue

            # ── Step 3: 翻訳方向の決定 ──
            direction_label, target_lang, embed_color = get_translation_direction(detected_lang)

            # ── Step 4: Ollama APIで翻訳（非同期） ──
            if http_session is None:
                logger.error("HTTPセッションが初期化されていません")
                queue.task_done()
                continue

            try:
                translated_text = await translate_with_ollama(
                    text,
                    detected_lang,
                    http_session,
                )
                logger.info(
                    "翻訳完了 | user=%s | %s | '%s' → '%s'",
                    display_name,
                    direction_label,
                    text,
                    translated_text,
                )
            except Exception as e:
                logger.error("翻訳エラー | user=%s: %s", display_name, e)
                queue.task_done()
                continue

            # ── Step 5: Discordテキストチャンネルに送信 ──
            try:
                channel = bot.get_channel(TEXT_CHANNEL_ID)
                if channel is None:
                    channel = await bot.fetch_channel(TEXT_CHANNEL_ID)

                # メッセージ本文（出力フォーマット厳守）
                # フォーマット:
                #   {ユーザーの表示名} [{方向}]:
                #
                #   {翻訳前のオリジナルテキスト}
                #
                message_content = (
                    f"**{display_name}** [{direction_label}]:\n"
                    f"\n"
                    f"{text}\n"
                    f"\n"
                )

                # Embed（翻訳結果）
                embed = discord.Embed(
                    description=f"**{translated_text}**",
                    color=embed_color,
                )

                await channel.send(content=message_content, embed=embed)
                logger.info("Discord送信完了 | user=%s", display_name)

            except discord.DiscordException as e:
                logger.error("Discord送信エラー | user=%s: %s", display_name, e)

        except asyncio.CancelledError:
            logger.info("翻訳ワーカーがキャンセルされました")
            break
        except Exception as e:
            logger.error("翻訳ワーカー予期しないエラー: %s", e, exc_info=True)
        finally:
            try:
                queue.task_done()
            except ValueError:
                # task_done()が既に呼ばれている場合は無視
                pass


# ─────────────────────────────────────────────
# Discord Bot 本体
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = discord.Bot(intents=intents)

# 翻訳用asyncio.Queue（グローバル）
audio_queue: asyncio.Queue = asyncio.Queue()

# ギルドごとのVADSinkインスタンスを管理
# key: guild_id, value: VADSink
active_sinks: dict[int, VADSink] = {}

# 翻訳ワーカータスク
worker_task: Optional[asyncio.Task] = None


@bot.event
async def on_ready() -> None:
    """Bot起動時のイベントハンドラ（再接続時にも呼ばれる）"""
    global vad_model, whisper_model, http_session, models_loaded, DICTIONARY, worker_task

    logger.info("Bot起動完了 | ユーザー名: %s | ID: %d", bot.user.name, bot.user.id)
    logger.info("接続サーバー数: %d", len(bot.guilds))

    # 用語辞書の読み込み
    DICTIONARY = load_dictionary()

    # ── モデルロード（二重ロード防止） ──
    if not models_loaded:
        models_loaded = True

        logger.info("=" * 60)
        logger.info("AutoTrans Bot 初期化中...")
        logger.info("=" * 60)

        # Silero VADモデルの初期化（asyncio.to_thread()でイベントループをブロックしない）
        try:
            logger.info("Silero VADモデルをバックグラウンドスレッドでロード中...")
            vad_model = await asyncio.to_thread(initialize_vad_model)
        except Exception as e:
            logger.critical("Silero VADモデルの初期化に失敗しました: %s", e, exc_info=True)
            models_loaded = False  # 失敗時はフラグをリセットして再試行可能にする
            return

        # faster-whisperモデルの初期化（asyncio.to_thread()でイベントループをブロックしない）
        try:
            logger.info("faster-whisperモデルをバックグラウンドスレッドでロード中...")
            whisper_model = await asyncio.to_thread(initialize_whisper_model)
        except Exception as e:
            logger.critical("faster-whisperモデルの初期化に失敗しました: %s", e, exc_info=True)
            models_loaded = False  # 失敗時はフラグをリセットして再試行可能にする
            return

        # aiohttp.ClientSessionの作成（Botのライフサイクル全体で使い回す）
        connector = aiohttp.TCPConnector(limit=10)
        http_session = aiohttp.ClientSession(connector=connector)
        logger.info("aiohttp.ClientSession作成完了 | Ollama URL: %s", OLLAMA_BASE_URL)

        # Ollama接続確認
        try:
            async with http_session.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    logger.info("Ollama接続確認OK | model=%s", OLLAMA_MODEL)
                else:
                    logger.warning("Ollama接続確認: HTTPステータス %d", resp.status)
        except Exception as e:
            logger.warning("Ollama接続確認失敗（起動後に再試行されます）: %s", e)

        logger.info("AIモデルのロード完了")

    # 翻訳ワーカータスクを起動（既に起動済みの場合はスキップ）
    if worker_task is None or worker_task.done():
        worker_task = asyncio.create_task(
            translation_worker(audio_queue, bot),
            name="translation_worker",
        )
        logger.info("翻訳ワーカータスク起動完了")
    else:
        logger.info("翻訳ワーカータスクは既に起動中です（スキップ）")

    # スラッシュコマンドを同期（guild_ids未指定の場合のフォールバック）
    if not GUILD_ID:
        try:
            await bot.sync_commands()
            logger.info("スラッシュコマンドの同期完了（グローバル）")
        except Exception as e:
            logger.warning("スラッシュコマンドの同期に失敗しました: %s", e)


_GUILD_IDS = [GUILD_ID] if GUILD_ID else None


@bot.slash_command(
    name="reload_dict",
    description="用語辞書を再読み込みします",
    guild_ids=_GUILD_IDS,
)
async def reload_dict(ctx: discord.ApplicationContext) -> None:
    """
    /reload_dict コマンド:
    実行中のBotに dictionary.json を再読み込みさせる。
    再起動不要で用語を更新できる。
    """
    global DICTIONARY
    try:
        new_dict = load_dictionary()
        DICTIONARY = new_dict
        ja_count = len(DICTIONARY["ja_to_ko"])
        ko_count = len(DICTIONARY["ko_to_ja"])
        await ctx.respond(
            f"✅ 辞書を再読み込みしました。JA→KO: {ja_count}語, KO→JA: {ko_count}語",
            ephemeral=True,
        )
    except Exception as e:
        logger.error("辞書再読み込みエラー: %s", e)
        await ctx.respond(
            "❌ 辞書の読み込みに失敗しました。dictionary.json を確認してください。",
            ephemeral=True,
        )


@bot.slash_command(
    name="join",
    description="BotをVCに参加させて翻訳を開始します",
    guild_ids=_GUILD_IDS,
)
async def join_command(ctx: discord.ApplicationContext) -> None:
    """
    /join コマンド:
    コマンド実行者のいるボイスチャンネルにBotを参加させ、
    VADSinkを使った音声受信・翻訳を開始する。
    """
    await ctx.defer()

    # ── バリデーション ──
    if ctx.author.voice is None:
        await ctx.followup.send(
            "❌ まずボイスチャンネルに参加してください。",
            ephemeral=True,
        )
        return

    voice_channel = ctx.author.voice.channel

    # 既に同じサーバーのVCに参加している場合は切断してから再接続
    if ctx.guild.voice_client is not None:
        logger.info("既存のVC接続を切断 | guild=%s", ctx.guild.name)
        if ctx.guild.voice_client.is_listening():
            ctx.guild.voice_client.stop_recording()
        await ctx.guild.voice_client.disconnect(force=True)
        # 既存のSinkをクリーンアップ
        if ctx.guild_id in active_sinks:
            active_sinks[ctx.guild_id].cleanup()
            del active_sinks[ctx.guild_id]

    # ── VCに接続 ──
    try:
        voice_client = await voice_channel.connect()
        logger.info(
            "VC接続成功 | guild=%s | channel=%s",
            ctx.guild.name,
            voice_channel.name,
        )
    except discord.ClientException as e:
        logger.error("VC接続エラー: %s", e)
        await ctx.followup.send(f"❌ VC接続に失敗しました: {e}", ephemeral=True)
        return

    # ── VADSinkを作成して音声受信を開始 ──
    loop = asyncio.get_event_loop()
    sink = VADSink(queue=audio_queue, loop=loop)
    active_sinks[ctx.guild_id] = sink

    # py-cordの音声受信を開始
    # finished_callbackは stop_recording() 呼び出し後に実行される
    # py-cord master: start_recording(sink, callback) — ctx.channel は不要
    voice_client.start_recording(
        sink,
        finished_callback,
    )
    # reader.py の self.sink._client = client がコメントアウトされているため手動設定
    sink.client = voice_client

    logger.info(
        "音声受信開始 | guild=%s | channel=%s",
        ctx.guild.name,
        voice_channel.name,
    )

    await ctx.followup.send(
        f"✅ **{voice_channel.name}** に参加しました。翻訳を開始します。\n"
        f"翻訳結果は <#{TEXT_CHANNEL_ID}> に送信されます。"
    )


async def finished_callback(error: Exception | None) -> None:
    """
    py-cordの音声受信終了時に呼ばれるコールバック。
    stop_recording()が呼ばれた際に実行される。

    py-cord master の AfterCallback = Callable[[Exception | None], Any] に合わせて
    引数は error のみ（旧 py-cord 2.4.x の sink, channel, *args とは異なる）。
    """
    if error:
        logger.error("音声受信エラー: %s", error)
    logger.info("音声受信終了コールバック実行")
    # Sinkのクリーンアップは active_sinks 経由で leave_command が行う


@bot.slash_command(
    name="leave",
    description="BotをVCから退出させて翻訳を停止します",
    guild_ids=_GUILD_IDS,
)
async def leave_command(ctx: discord.ApplicationContext) -> None:
    """
    /leave コマンド:
    BotをVCから退出させ、音声受信・翻訳を停止する。
    """
    await ctx.defer()

    # ── バリデーション ──
    if ctx.guild.voice_client is None:
        await ctx.followup.send(
            "❌ Botはボイスチャンネルに参加していません。",
            ephemeral=True,
        )
        return

    voice_client = ctx.guild.voice_client

    # ── 音声受信を停止 ──
    if voice_client.is_listening():
        voice_client.stop_recording()
        logger.info("音声受信停止 | guild=%s", ctx.guild.name)

    # Sinkのクリーンアップ
    if ctx.guild_id in active_sinks:
        active_sinks[ctx.guild_id].cleanup()
        del active_sinks[ctx.guild_id]

    # ── VCから退出 ──
    channel_name = voice_client.channel.name
    await voice_client.disconnect(force=False)
    logger.info("VC退出完了 | guild=%s | channel=%s", ctx.guild.name, channel_name)

    await ctx.followup.send(f"👋 **{channel_name}** から退出しました。翻訳を停止しました。")


# ─────────────────────────────────────────────
# モデル初期化関数
# ─────────────────────────────────────────────
def initialize_vad_model() -> torch.nn.Module:
    """
    Silero VADモデルをtorch.hub経由でロードする。
    GPUが利用可能な場合はGPUにロードする。

    Returns:
        ロードされたSilero VADモデル
    """
    logger.info("Silero VADモデルをロード中...")

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    # utilsには (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) が含まれる
    # 今回はモデル本体のみ使用（VADIteratorは使わずモデルを直接呼び出す）

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    logger.info("Silero VADモデルロード完了 | device=%s", device)
    return model


def initialize_whisper_model() -> WhisperModel:
    """
    faster-whisperモデルをロードする。
    CUDAが利用可能な場合はGPU + float16で実行する。

    Returns:
        ロードされたWhisperModelインスタンス
    """
    logger.info("faster-whisperモデルをロード中... (model=%s)", WHISPER_MODEL)

    if torch.cuda.is_available():
        device = "cuda"
        compute_type = "float16"
    else:
        logger.warning("CUDAが利用できません。CPUで実行します（速度が低下します）")
        device = "cpu"
        compute_type = "int8"

    model = WhisperModel(
        WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )

    logger.info(
        "faster-whisperモデルロード完了 | model=%s | device=%s | compute_type=%s",
        WHISPER_MODEL,
        device,
        compute_type,
    )
    return model


# ─────────────────────────────────────────────
# メインエントリーポイント
# ─────────────────────────────────────────────
# bot.run() はブロッキング呼び出し。
# モデルロードは on_ready() 内の asyncio.to_thread() で実行されるため、
# voice_channel.connect() と同じイベントループを使用し、
# "attached to a different loop" エラーが発生しない。
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure as e:
        logger.critical("Discordログイン失敗（トークンを確認してください）: %s", e)
        raise
    except KeyboardInterrupt:
        logger.info("Ctrl+C で終了しました")
    except Exception as e:
        logger.critical("致命的なエラーが発生しました: %s", e, exc_info=True)
        raise