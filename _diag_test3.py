import sys
import os

# 環境変数のモック
os.environ.setdefault('DISCORD_TOKEN', 'dummy_token_for_test')
os.environ.setdefault('TEXT_CHANNEL_ID', '123456789')

print('=== Python バージョン確認 ===')
print('Python:', sys.version)
print()

# bot.pyのVADSinkクラス定義を完全に再現（bot.pyのimport文も含む）
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from discord.voice import VoiceData

import discord

print('=== bot.pyと完全同一のVADSink定義テスト ===')

class VADSink(discord.sinks.Sink):
    """
    py-cordのカスタムSink。
    """

    # py-cord master の SinkEventRouter が参照するクラス変数。
    # 形式: list[tuple[event_name, method_name]]
    __sink_listeners__: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(filters=None)
        self.queue = queue
        self.loop = loop
        self._user_states: dict[int, dict] = defaultdict(lambda: {
            "buffer": [],
            "vad_buffer": [],
            "is_speaking": False,
            "silence_start": None,
            "display_name": "Unknown",
        })
        self._silence_threshold_sec: float = 0.4

    def write(self, data: "VoiceData", user) -> None:
        pass

    def cleanup(self) -> None:
        self._user_states.clear()

    def walk_children(self):
        return iter([])

    def is_opus(self) -> bool:
        return False

print('VADSinkクラス定義完了')
print('__sink_listeners__ in VADSink.__dict__:', '__sink_listeners__' in VADSink.__dict__)
print('VADSink.__sink_listeners__:', VADSink.__sink_listeners__)
print()

loop = asyncio.new_event_loop()
q = asyncio.Queue()
sink = VADSink(queue=q, loop=loop)

print('インスタンス生成完了')
print('hasattr(sink, "__sink_listeners__"):', hasattr(sink, '__sink_listeners__'))
print('sink.__sink_listeners__:', sink.__sink_listeners__)
print()

# SinkEventRouterの_register_listenersを完全再現
import logging as _logging
_log = _logging.getLogger('test')

print('=== _register_listeners 完全再現 ===')
try:
    _log.debug("Registering events for %s: %s", sink, sink.__sink_listeners__)
    print('sink.__sink_listeners__ アクセス成功:', sink.__sink_listeners__)
    print('OK')
except AttributeError as e:
    print('AttributeError:', e)

loop.close()
