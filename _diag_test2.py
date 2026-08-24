import sys
import os

# bot.pyと同じディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 環境変数のモック（bot.pyがDISCORD_TOKENを必須とするため）
os.environ.setdefault('DISCORD_TOKEN', 'dummy_token_for_test')
os.environ.setdefault('TEXT_CHANNEL_ID', '123456789')

print('=== VADSink直接診断 ===')

# bot.pyをインポートせず、VADSinkクラスだけを再現してテスト
import discord
import asyncio
from typing import TYPE_CHECKING, ClassVar, Optional

class VADSink(discord.sinks.Sink):
    """bot.pyのVADSinkと同一の定義"""

    # py-cord master の SinkEventRouter が参照するクラス変数。
    __sink_listeners__: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, queue, loop):
        super().__init__(filters=None)
        self.queue = queue
        self.loop = loop

    def write(self, data, user):
        pass

    def cleanup(self):
        pass

    def walk_children(self):
        return iter([])

    def is_opus(self):
        return False

# インスタンス生成テスト
loop = asyncio.new_event_loop()
q = asyncio.Queue()
sink = VADSink(queue=q, loop=loop)

print('--- VADSinkクラス変数 ---')
print('VADSink.__dict__キー:', [k for k in VADSink.__dict__.keys()])
print()
print('--- VADSinkインスタンス ---')
print('has __sink_listeners__:', hasattr(sink, '__sink_listeners__'))
if hasattr(sink, '__sink_listeners__'):
    print('value:', sink.__sink_listeners__)
print('has walk_children:', hasattr(sink, 'walk_children'))
print()
print('--- インスタンス__dict__ ---')
print(sink.__dict__)
print()

# SinkEventRouterが実際に呼ぶ処理をシミュレート
print('--- _register_listeners シミュレーション ---')
try:
    listeners = sink.__sink_listeners__
    print('sink.__sink_listeners__ アクセス成功:', listeners)
    for name, method_name in listeners:
        func = getattr(sink, method_name)
        print(f'  イベント登録: {name} -> {method_name}')
    print('OK: エラーなし')
except AttributeError as e:
    print('AttributeError:', e)
except Exception as e:
    print('その他エラー:', type(e).__name__, e)

loop.close()
