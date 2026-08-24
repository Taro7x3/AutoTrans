import discord
import sys
from typing import ClassVar

print('=== 診断ログ ===')
print('py-cord version:', discord.__version__)
print()

# Sink基底クラスの属性確認
print('--- Sink基底クラスの属性 ---')
print('has __sink_listeners__:', hasattr(discord.sinks.Sink, '__sink_listeners__'))
print('has walk_children:', hasattr(discord.sinks.Sink, 'walk_children'))
print()

# VADSinkと同等のクラスを定義してテスト（ClassVar注釈あり）
class TestSink1(discord.sinks.Sink):
    __sink_listeners__: ClassVar[list] = []
    def write(self, data, user): pass
    def cleanup(self): pass
    def walk_children(self): return iter([])

# VADSinkと同等のクラスを定義してテスト（注釈なし）
class TestSink2(discord.sinks.Sink):
    __sink_listeners__ = []
    def write(self, data, user): pass
    def cleanup(self): pass
    def walk_children(self): return iter([])

print('--- TestSink1 (ClassVar注釈あり) ---')
s1 = TestSink1(filters=None)
print('has __sink_listeners__:', hasattr(s1, '__sink_listeners__'))
if hasattr(s1, '__sink_listeners__'):
    print('value:', s1.__sink_listeners__)
print()

print('--- TestSink2 (注釈なし) ---')
s2 = TestSink2(filters=None)
print('has __sink_listeners__:', hasattr(s2, '__sink_listeners__'))
if hasattr(s2, '__sink_listeners__'):
    print('value:', s2.__sink_listeners__)
print()

# __dict__確認
print('--- TestSink1クラスの__dict__キー ---')
print([k for k in TestSink1.__dict__.keys()])
print()
print('--- TestSink2クラスの__dict__キー ---')
print([k for k in TestSink2.__dict__.keys()])
print()

# Sink.__init__が何をするか確認
print('--- Sink.__init__後のインスタンス__dict__ ---')
print('s1.__dict__:', s1.__dict__)
print()

# __annotations__確認
print('--- TestSink1.__annotations__ ---')
print(getattr(TestSink1, '__annotations__', 'なし'))
