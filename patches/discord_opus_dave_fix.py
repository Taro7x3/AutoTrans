"""
discord_opus_dave_fix.py
========================
Pycord masterブランチの音声受信における DAVE (E2E暗号化) 復号バグを修正するパッチスクリプト。

【問題の根本原因】
Pycord master (2.8.2.dev) の PacketDecryptor.decrypt_rtp() は、
dave.ready が False の間（MLS鍵交換が未完了の間）DAVE復号をスキップし、
packet.decrypted_data を None のまま返す。

その後 PacketDecoder._decode_packet() が None をOpusデコードしようとして
"corrupted stream" エラーが発生する。

  現在の誤った動作:
    1. decrypt_rtp(): dave.ready=False → DAVE復号スキップ → decrypted_data=None
    2. _decode_packet(): decode(None) → OpusError: corrupted stream

  正しい動作:
    1. decrypt_rtp(): dave.ready に関わらず DAVE復号を試みる
       → 失敗時は OPUS_SILENCE にフォールバック
    2. _decode_packet(): 有効なデータをOpusデコード

【パッチ内容】
1. PacketDecryptor.decrypt_rtp() をモンキーパッチで置き換え、
   dave.ready チェックを除去して常にDAVE復号を試みるよう修正する。
2. PacketDecoder._decode_packet() をモンキーパッチで置き換え、
   decrypted_data が None の場合に OPUS_SILENCE にフォールバックするよう修正する。

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
# 診断カウンター（INFOレベルで定期的に状態を報告するため）
# ─────────────────────────────────────────────────────────────────────────────
_diag_counters: dict = {
    "total": 0,
    "dave_skipped_no_session": 0,
    "dave_skipped_no_user": 0,
    "dave_skipped_no_passthrough": 0,
    "dave_decrypt_ok": 0,
    "dave_decrypt_fail": 0,
    "opus_ok": 0,
    "opus_fail": 0,
    "write_called": 0,
    # decrypt_rtp パッチ用
    "decrypt_rtp_total": 0,
    "decrypt_rtp_dave_ok": 0,
    "decrypt_rtp_dave_fail": 0,
    "decrypt_rtp_dave_skipped_no_session": 0,
    "decrypt_rtp_dave_skipped_no_uid": 0,
    "decrypt_rtp_dave_ready_false": 0,
}
_DIAG_REPORT_INTERVAL = 50  # 50パケットごとにINFOログで状態を報告


# ─────────────────────────────────────────────────────────────────────────────
# パッチ1: PacketDecryptor.decrypt_rtp()
# ─────────────────────────────────────────────────────────────────────────────

def _patched_decrypt_rtp(self, packet):
    """
    PacketDecryptor.decrypt_rtp() のパッチ版。

    修正内容:
      - dave.ready が False でも DAVE復号を試みる。
        （オリジナルは dave.ready=True の場合のみDAVE復号を実行する）
      - DAVE復号に失敗した場合は OPUS_SILENCE にフォールバック。
      - dave_session が None の場合は元の動作と同じ（NaCl復号のみ）。
      - can_passthrough=True のユーザーは DAVE 暗号化なしで送信しているため
        DAVE復号をスキップする（オリジナルの decrypt_rtp() と同じ動作）。

    診断ログ:
      - 50パケットごとにINFOレベルで処理統計を出力する。
    """
    import davey as _davey
    from discord.voice.packets.core import OPUS_SILENCE

    state = self.client._connection
    dave = state.dave_session

    # NaCl復号（元の動作と同じ）
    raw_payload = self._decryptor_rtp(packet)

    _diag_counters["decrypt_rtp_total"] += 1
    total = _diag_counters["decrypt_rtp_total"]

    if dave is not None:
        uid = state.ssrc_user_map.get(packet.ssrc)
        if uid:
            # can_passthrough=True のユーザーは DAVE 暗号化なしで送信しているため
            # DAVE復号をスキップする。スキップしないと Opus データを破壊する。
            # オリジナルの decrypt_rtp() は can_passthrough チェックをしていないが、
            # _decode_packet() で can_passthrough チェックをしている。
            # パッチは _decode_packet() も置き換えているため、ここでチェックする。
            if dave.can_passthrough(uid):
                _log.debug(
                    "[DAVE patch decrypt_rtp] uid=%s can_passthrough, skipping DAVE decrypt",
                    uid,
                )
                # パススルーユーザー: NaCl復号済みデータをそのまま使用
                if packet.extended:
                    offset = packet.update_extended_header(raw_payload)
                    packet.decrypted_data = raw_payload[offset:]
                else:
                    packet.decrypted_data = raw_payload
                # 定期診断レポート
                if total % _DIAG_REPORT_INTERVAL == 0:
                    _log.info(
                        "[DAVE patch decrypt_rtp 診断] パケット数=%d | "
                        "DAVEセッションなし=%d | uid不明=%d | dave.ready=False時の試行=%d | "
                        "DAVE復号成功=%d | DAVE復号失敗=%d",
                        total,
                        _diag_counters["decrypt_rtp_dave_skipped_no_session"],
                        _diag_counters["decrypt_rtp_dave_skipped_no_uid"],
                        _diag_counters["decrypt_rtp_dave_ready_false"],
                        _diag_counters["decrypt_rtp_dave_ok"],
                        _diag_counters["decrypt_rtp_dave_fail"],
                    )
                return packet.decrypted_data

            if not dave.ready:
                # dave.ready=False: MLS鍵交換が未完了
                # オリジナルはここでスキップするが、パッチでは復号を試みる
                _diag_counters["decrypt_rtp_dave_ready_false"] += 1
                _log.debug(
                    "[DAVE patch decrypt_rtp] dave.ready=False for ssrc=%s uid=%s, "
                    "attempting DAVE decrypt anyway",
                    packet.ssrc,
                    uid,
                )

            # ── 修正: 拡張ヘッダーのオフセットを事前計算し、復号後にスライスする ──
            #
            # 正しい処理フロー:
            #   1. raw_payload から拡張ヘッダーのオフセットを「事前に」計算する
            #   2. davey.DaveSession.decrypt には raw_payload をそのまま渡す
            #      （davey は拡張ヘッダーを AAD として内部参照するため、切り落とすと認証失敗）
            #   3. 復号後の decrypted_audio に事前計算したオフセットを適用してスライスする
            #
            # 誤った処理（旧実装）:
            #   - decrypted_audio（復号後の Opus データ）に update_extended_header を呼ぶ
            #     → Opus データを拡張ヘッダーと誤認してスライスし、フレームを破壊
            #     → Opus デコード失敗率 ~50% の根本原因
            offset = 0
            if packet.extended:
                offset = packet.update_extended_header(raw_payload)

            try:
                # davey に raw_payload をそのまま渡して復号
                # ※ davey は拡張ヘッダーを AAD として処理し、
                #    復号結果として「拡張ヘッダーを除去した純粋な Opus フレーム」を返します。
                decrypted_audio = _davey.DaveSession.decrypt(
                    dave, uid, _davey.MediaType.audio, raw_payload
                )
                _diag_counters["decrypt_rtp_dave_ok"] += 1
                _log.debug(
                    "[DAVE patch decrypt_rtp] DAVE decrypt OK for ssrc=%s uid=%s (extended=%s)",
                    packet.ssrc,
                    uid,
                    packet.extended,
                )

                # 復号結果をそのまま代入（手動スライスは不要）
                packet.decrypted_data = decrypted_audio

            except Exception as exc:
                _diag_counters["decrypt_rtp_dave_fail"] += 1
                _log.error(
                    "[DAVE patch decrypt_rtp] DAVE decrypt FAILED for ssrc=%s uid=%s: %s (%s)",
                    packet.ssrc,
                    uid,
                    exc,
                    type(exc).__name__,
                    exc_info=True,
                )
                packet.decrypted_data = OPUS_SILENCE
        else:
            _diag_counters["decrypt_rtp_dave_skipped_no_uid"] += 1
            _log.debug(
                "[DAVE patch decrypt_rtp] No uid for ssrc=%s, skipping DAVE decrypt",
                packet.ssrc,
            )
            # uid が不明な場合: NaCl復号済みデータをそのまま使用
            if packet.extended:
                offset = packet.update_extended_header(raw_payload)
                packet.decrypted_data = raw_payload[offset:]
            else:
                packet.decrypted_data = raw_payload
    else:
        _diag_counters["decrypt_rtp_dave_skipped_no_session"] += 1
        # DAVEセッションなし: NaCl復号済みデータをそのまま使用
        if packet.extended:
            offset = packet.update_extended_header(raw_payload)
            packet.decrypted_data = raw_payload[offset:]
        else:
            packet.decrypted_data = raw_payload

    # 定期診断レポート（50パケットごと）
    if total % _DIAG_REPORT_INTERVAL == 0:
        _log.info(
            "[DAVE patch decrypt_rtp 診断] パケット数=%d | "
            "DAVEセッションなし=%d | uid不明=%d | dave.ready=False時の試行=%d | "
            "DAVE復号成功=%d | DAVE復号失敗=%d",
            total,
            _diag_counters["decrypt_rtp_dave_skipped_no_session"],
            _diag_counters["decrypt_rtp_dave_skipped_no_uid"],
            _diag_counters["decrypt_rtp_dave_ready_false"],
            _diag_counters["decrypt_rtp_dave_ok"],
            _diag_counters["decrypt_rtp_dave_fail"],
        )

    return packet.decrypted_data


# ─────────────────────────────────────────────────────────────────────────────
# パッチ2: PacketDecoder._decode_packet()
# ─────────────────────────────────────────────────────────────────────────────

def _patched_decode_packet(self, packet):
    """
    PacketDecoder._decode_packet() のパッチ版。

    修正内容:
      - packet.decrypted_data が None の場合に OPUS_SILENCE にフォールバック。
        （オリジナルは None をそのまま decode() に渡して corrupted stream エラーを出す）
      - Opusデコード失敗時は無音PCMを返す（エラーを上位に伝播させない）。

    診断ログ:
      - 50パケットごとにINFOレベルで処理統計を出力する。
    """
    from discord.voice.packets.core import OPUS_SILENCE

    assert self._decoder is not None
    assert self.sink.client

    user_id = self._cached_id

    # ── 診断カウンター更新 ──
    _diag_counters["total"] += 1
    total = _diag_counters["total"]

    # decrypted_data が None の場合は OPUS_SILENCE にフォールバック
    # （PacketDecryptor.decrypt_rtp() が dave.ready=False でスキップした場合に発生）
    if packet and packet.decrypted_data is None:
        _log.debug(
            "[DAVE patch decode] decrypted_data is None for user %s, "
            "using OPUS_SILENCE as fallback",
            user_id,
        )
        packet.decrypted_data = OPUS_SILENCE

    # ── Opusデコード ──
    other_code = True
    pcm = None

    if packet:
        other_code = False
        try:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
            _diag_counters["opus_ok"] += 1
        except Exception as exc:
            _diag_counters["opus_fail"] += 1
            data = packet.decrypted_data
            _log.info(
                "[DAVE patch decode] Opus decode FAILED for user %s: %s (type=%s) | "
                "data_len=%d | data_head=%s | data_tail=%s",
                user_id,
                exc,
                type(exc).__name__,
                len(data) if data else 0,
                data[:8].hex() if data and len(data) >= 8 else (data.hex() if data else "None"),
                data[-8:].hex() if data and len(data) >= 8 else "",
            )
            # Opusデコード失敗時は無音PCMを返す（エラーを上位に伝播させない）
            # 48kHz stereo 16bit, 20ms = 960 samples * 2ch * 2bytes = 3840 bytes
            pcm = b"\x00" * 3840

    if other_code:
        next_packet = self._buffer.peek_next()

        if next_packet is not None:
            nextdata = next_packet.decrypted_data

            _log.debug(
                "[DAVE patch decode] Generating fec packet: fake=%s, fec=%s",
                packet.sequence,
                next_packet.sequence,
            )
            try:
                pcm = self._decoder.decode(nextdata, fec=True)
                _diag_counters["opus_ok"] += 1
            except Exception as exc:
                _diag_counters["opus_fail"] += 1
                _log.debug("[DAVE patch decode] FEC decode failed: %s", exc)
                pcm = b"\x00" * 3840
        else:
            try:
                pcm = self._decoder.decode(None, fec=False)
                _diag_counters["opus_ok"] += 1
            except Exception as exc:
                _diag_counters["opus_fail"] += 1
                _log.debug("[DAVE patch decode] FEC (no next packet) decode failed: %s", exc)
                pcm = b"\x00" * 3840

    # ── 定期診断レポート（50パケットごと） ──
    if total % _DIAG_REPORT_INTERVAL == 0:
        opus_total = _diag_counters["opus_ok"] + _diag_counters["opus_fail"]
        opus_fail_rate = (
            _diag_counters["opus_fail"] / opus_total * 100 if opus_total > 0 else 0
        )
        _log.info(
            "[DAVE patch decode 診断] パケット数=%d | "
            "Opusデコード成功=%d | Opusデコード失敗=%d (失敗率=%.1f%%) | "
            "write()呼び出し=%d",
            total,
            _diag_counters["opus_ok"],
            _diag_counters["opus_fail"],
            opus_fail_rate,
            _diag_counters["write_called"],
        )

    return packet, pcm


# ─────────────────────────────────────────────────────────────────────────────
# パッチ適用
# ─────────────────────────────────────────────────────────────────────────────

def apply_patch() -> bool:
    """
    Pycordの PacketDecryptor.decrypt_rtp() と PacketDecoder._decode_packet() に
    パッチを適用する。

    Returns:
        True: パッチ適用成功
        False: パッチ適用失敗（Pycordのバージョンが変わった可能性）
    """
    success = True

    # ── パッチ1: PacketDecryptor.decrypt_rtp() ──
    try:
        from discord.voice.receive.reader import PacketDecryptor

        if getattr(PacketDecryptor.decrypt_rtp, "_dave_patched", False):
            _log.info("[DAVE patch] PacketDecryptor.decrypt_rtp パッチは既に適用済みです。スキップします。")
        else:
            original_decrypt_rtp = PacketDecryptor.decrypt_rtp
            _patched_decrypt_rtp._dave_patched = True  # type: ignore[attr-defined]
            _patched_decrypt_rtp._original = original_decrypt_rtp  # type: ignore[attr-defined]
            PacketDecryptor.decrypt_rtp = _patched_decrypt_rtp  # type: ignore[method-assign]
            _log.info(
                "[DAVE patch] PacketDecryptor.decrypt_rtp() にDAVEパッチを適用しました。"
                " (dave.ready=False でもDAVE復号を試みるよう修正)"
            )

    except ImportError as e:
        _log.error("[DAVE patch] PacketDecryptor のインポートに失敗しました: %s", e)
        success = False
    except AttributeError as e:
        _log.error(
            "[DAVE patch] PacketDecryptor.decrypt_rtp が見つかりません"
            "（Pycordのバージョンが変わった可能性）: %s",
            e,
        )
        success = False
    except Exception as e:
        _log.error(
            "[DAVE patch] PacketDecryptor パッチ適用中に予期しないエラー: %s",
            e,
            exc_info=True,
        )
        success = False

    # ── パッチ2: PacketDecoder._decode_packet() ──
    try:
        from discord.opus import PacketDecoder

        if getattr(PacketDecoder._decode_packet, "_dave_patched", False):
            _log.info("[DAVE patch] PacketDecoder._decode_packet パッチは既に適用済みです。スキップします。")
        else:
            original_decode_packet = PacketDecoder._decode_packet
            _patched_decode_packet._dave_patched = True  # type: ignore[attr-defined]
            _patched_decode_packet._original = original_decode_packet  # type: ignore[attr-defined]
            PacketDecoder._decode_packet = _patched_decode_packet  # type: ignore[method-assign]
            _log.info(
                "[DAVE patch] PacketDecoder._decode_packet() にDAVEパッチを適用しました。"
                " (decrypted_data=None 時の OPUS_SILENCE フォールバック追加)"
            )

    except ImportError as e:
        _log.error("[DAVE patch] PacketDecoder のインポートに失敗しました: %s", e)
        success = False
    except AttributeError as e:
        _log.error(
            "[DAVE patch] PacketDecoder._decode_packet が見つかりません"
            "（Pycordのバージョンが変わった可能性）: %s",
            e,
        )
        success = False
    except Exception as e:
        _log.error(
            "[DAVE patch] PacketDecoder パッチ適用中に予期しないエラー: %s",
            e,
            exc_info=True,
        )
        success = False

    return success


def remove_patch() -> bool:
    """
    適用済みのパッチを元に戻す。

    Returns:
        True: パッチ除去成功
        False: パッチが適用されていない、または除去失敗
    """
    success = True

    # PacketDecryptor.decrypt_rtp のパッチ除去
    try:
        from discord.voice.receive.reader import PacketDecryptor

        current = PacketDecryptor.decrypt_rtp
        if getattr(current, "_dave_patched", False):
            original = getattr(current, "_original", None)
            if original is not None:
                PacketDecryptor.decrypt_rtp = original  # type: ignore[method-assign]
                _log.info("[DAVE patch] PacketDecryptor.decrypt_rtp パッチを除去しました。")
            else:
                _log.warning("[DAVE patch] PacketDecryptor.decrypt_rtp のオリジナルが見つかりません。")
                success = False
        else:
            _log.info("[DAVE patch] PacketDecryptor.decrypt_rtp パッチは適用されていません。")
    except Exception as e:
        _log.error("[DAVE patch] PacketDecryptor パッチ除去中にエラー: %s", e)
        success = False

    # PacketDecoder._decode_packet のパッチ除去
    try:
        from discord.opus import PacketDecoder

        current = PacketDecoder._decode_packet
        if getattr(current, "_dave_patched", False):
            original = getattr(current, "_original", None)
            if original is not None:
                PacketDecoder._decode_packet = original  # type: ignore[method-assign]
                _log.info("[DAVE patch] PacketDecoder._decode_packet パッチを除去しました。")
            else:
                _log.warning("[DAVE patch] PacketDecoder._decode_packet のオリジナルが見つかりません。")
                success = False
        else:
            _log.info("[DAVE patch] PacketDecoder._decode_packet パッチは適用されていません。")
    except Exception as e:
        _log.error("[DAVE patch] PacketDecoder パッチ除去中にエラー: %s", e)
        success = False

    return success


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
        from discord.voice.receive.reader import PacketDecryptor
        from discord.opus import PacketDecoder

        is_decrypt_patched = getattr(PacketDecryptor.decrypt_rtp, "_dave_patched", False)
        is_decode_patched = getattr(PacketDecoder._decode_packet, "_dave_patched", False)

        print(f"\n[OK] パッチ適用状態:")
        print(f"   PacketDecryptor.decrypt_rtp: {'適用済み' if is_decrypt_patched else '未適用'}")
        print(f"   PacketDecoder._decode_packet: {'適用済み' if is_decode_patched else '未適用'}")
        print(f"\n   修正内容1: dave.ready=False でもDAVE復号を試みるよう変更")
        print(f"   修正内容2: decrypted_data=None 時に OPUS_SILENCE フォールバック追加")
        print(f"   参照: https://github.com/Pycord-Development/pycord/issues/3139")
        sys.exit(0 if (is_decrypt_patched and is_decode_patched) else 1)
    else:
        print("\n[FAIL] パッチの適用に失敗しました。ログを確認してください。")
        sys.exit(1)
