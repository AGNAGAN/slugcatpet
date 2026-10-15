"""手动键盘操控。"""

from . import moves, keymap, session  # PyInstaller 靠静态 import 收集

__all__ = ["moves", "keymap", "session"]
