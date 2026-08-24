"""
discord_opus_dave_fix.py
========================
Pycord masterブランチの opus.py における DAVE (E2E暗号化) 復号バグを修正するパッチスクリプト。

【問題】
Pycord master (2.8.2.dev) の PacketDecoder._decode_packet() は、
DAVEセッションが存在する場合でも先にOpusデコードを実行し、
その後でDAVE復号を試みる（順序が逆）。

  現在の誤った順序:
    1. packet.decrypted_data をOpusデコード → corrupted stream エラー
    2. (エラーにならなかった場合のみ) DAVE復号

  正しい順序:
    1. packet.decrypted_data をDAVE復号（DAVEセッションが存在し、can_passthrough が True の場合）
    2. DAVE復号済みデータをOpusデコード

【パッチ内容】
PacketDecoder._decode_packet() をモンキーパッチで置き換え、
DAVE復号をOpusデコードの前に実行するよう修正する。

【使用方法】
  # bot.py の先頭付近でインポートするだけで自動適用される
  import patches.discord_opus_dave_fix  # noqa: F401

  # または単体で実行して適用確認
  python patches/discord_opus_dave_fix.py

【注意】
  - pip install --upgrade で Pycord を更新した場合、このパッチは引き続き有効
    （モンキーパッチはランタイムに適用されるため）
  - Pycord が公式に DAVE 音声受信を修正した場合は、このパッチを削除すること
  - 参照: https://github.com/Pycord-Development/pycord/issues/3139
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# パッチ適用
# ─────────────────────────────────────────────────────────────────────────────

def _patched_decode_packet(self, packet):
    """
    PacketDecoder._decode_packet() のパッチ版。

    修正内容:
      - DAVEセッションが存在し can_passthrough(user_id) が True の場合、
        Opusデコードの前に DAVE復号を実行する。
      - DAVEセッションが存在しない、または can_passthrough が False の場合は
        元の動作と同じ（Opusデコードのみ）。
      - DAVE復号に失敗した場合は元のデータでOpusデコードを試みる（フォールバック）。
    """
    import davey as _davey
    from discord.opus import HAS_DAVEY

    assert self._decoder is not None
    assert self.sink.client

    user_id = self._cached_id
    dave = self.sink.client._connection.dave_session
    in_dave = dave is not None

    _log.debug(
        "[DAVE patch] Decoding packet for user %s (DAVE enabled: %s, HAS_DAVEY: %s). "
        "Has decrypted data?: %s",
        user_id,
        in_dave,
        HAS_DAVEY,
        packet.decrypted_data is not None,
    )

    # ── Step 1: DAVE復号（Opusデコードの前に実行） ──
    # DAVEセッションが存在し、ユーザーが can_passthrough の場合のみ実行
    if HAS_DAVEY and in_dave and user_id is not None:
        try:
            if dave.can_passthrough(user_id):
                _log.debug(
                    "[DAVE patch] User %s can_passthrough=True, applying DAVE decrypt before Opus decode",
                    user_id,
                )
                decrypted = dave.decrypt(user_id, _davey.MediaType.audio, packet.decrypted_data)
                packet.decrypted_data = decrypted
                _log.debug("[DAVE patch] DAVE decrypt succeeded for user %s", user_id)
            else:
                _log.debug(
                    "[DAVE patch] User %s can_passthrough=False, skipping DAVE decrypt "
                    "(DAVE negotiation may still be in progress)",
                    user_id,
                )
        except Exception as exc:
            _log.debug(
                "[DAVE patch] DAVE decrypt failed for user %s (falling back to raw data): %s",
                user_id,
                exc,
            )
            # DAVE復号失敗時はフォールバック（元のデータでOpusデコードを試みる）

    # ── Step 2: Opusデコード ──
    other_code = True
    pcm = None

    if packet:
        other_code = False
        try:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
        except Exception as exc:
            _log.debug(
                "[DAVE patch] Opus decode failed for user %s (DAVE negotiation may be incomplete): %s",
                user_id,
                exc,
            )
            # Opusデコード失敗時は無音PCMを返す（エラーを上位に伝播させない）
            # 48kHz stereo 16bit, 20ms = 960 samples * 2ch * 2bytes = 3840 bytes
            pcm = b"\x00" * 3840

    if other_code:
        next_packet = self._buffer.peek_next()

        if next_packet is not None:
            nextdata = next_packet.decrypted_data

            _log.debug(
                "[DAVE patch] Generating fec packet: fake=%s, fec=%s",
                packet.sequence,
                next_packet.sequence,
            )
            try:
                pcm = self._decoder.decode(nextdata, fec=True)
            except Exception as exc:
                _log.debug("[DAVE patch] FEC decode failed: %s", exc)
                pcm = b"\x00" * 3840
        else:
            try:
                pcm = self._decoder.decode(None, fec=False)
            except Exception as exc:
                _log.debug("[DAVE patch] FEC (no next packet) decode failed: %s", exc)
                pcm = b"\x00" * 3840

    return packet, pcm


def apply_patch() -> bool:
    """
    Pycordの PacketDecoder._decode_packet() にパッチを適用する。

    Returns:
        True: パッチ適用成功
        False: パッチ適用失敗（Pycordのバージョンが変わった可能性）
    """
    try:
        from discord.opus import PacketDecoder

        # 既にパッチ適用済みかチェック
        if getattr(PacketDecoder._decode_packet, "_dave_patched", False):
            _log.info("[DAVE patch] パッチは既に適用済みです。スキップします。")
            return True

        # パッチを適用
        original = PacketDecoder._decode_packet
        _patched_decode_packet._dave_patched = True  # type: ignore[attr-defined]
        _patched_decode_packet._original = original  # type: ignore[attr-defined]
        PacketDecoder._decode_packet = _patched_decode_packet  # type: ignore[method-assign]

        _log.info(
            "[DAVE patch] PacketDecoder._decode_packet() にDAVEパッチを適用しました。"
            " (Pycord issue #3139 の回避策)"
        )
        return True

    except ImportError as e:
        _log.error("[DAVE patch] Pycordのインポートに失敗しました: %s", e)
        return False
    except AttributeError as e:
        _log.error(
            "[DAVE patch] パッチ対象のメソッドが見つかりません（Pycordのバージョンが変わった可能性）: %s",
            e,
        )
        return False
    except Exception as e:
        _log.error("[DAVE patch] パッチ適用中に予期しないエラーが発生しました: %s", e, exc_info=True)
        return False


def remove_patch() -> bool:
    """
    適用済みのパッチを元に戻す。

    Returns:
        True: パッチ除去成功
        False: パッチが適用されていない、または除去失敗
    """
    try:
        from discord.opus import PacketDecoder

        current = PacketDecoder._decode_packet
        if not getattr(current, "_dave_patched", False):
            _log.info("[DAVE patch] パッチは適用されていません。")
            return False

        original = getattr(current, "_original", None)
        if original is None:
            _log.warning("[DAVE patch] オリジナルメソッドが見つかりません。パッチを除去できません。")
            return False

        PacketDecoder._decode_packet = original  # type: ignore[method-assign]
        _log.info("[DAVE patch] パッチを除去しました。")
        return True

    except Exception as e:
        _log.error("[DAVE patch] パッチ除去中にエラーが発生しました: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# モジュールインポート時に自動適用
# ─────────────────────────────────────────────────────────────────────────────
apply_patch()


# ─────────────────────────────────────────────────────────────────────────────
# 単体実行時の動作確認
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print("=" * 60)
    print("discord_opus_dave_fix.py - パッチ適用確認")
    print("=" * 60)

    success = apply_patch()

    if success:
        from discord.opus import PacketDecoder
        is_patched = getattr(PacketDecoder._decode_packet, "_dave_patched", False)
        status = "適用済み" if is_patched else "未適用"
        print(f"\n[OK] パッチ適用状態: {status}")
        print(f"   対象メソッド: discord.opus.PacketDecoder._decode_packet")
        print(f"   修正内容: DAVE復号をOpusデコードの前に実行するよう変更")
        print(f"   参照: https://github.com/Pycord-Development/pycord/issues/3139")
        sys.exit(0)
    else:
        print("\n[FAIL] パッチの適用に失敗しました。ログを確認してください。")
        sys.exit(1)
