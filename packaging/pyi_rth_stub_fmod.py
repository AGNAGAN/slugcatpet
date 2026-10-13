"""PyInstaller 运行时钩子：用空 stub 顶替 UnityPy 顶层导入的 fmod_toolkit。"""

import sys
import types

if "fmod_toolkit" not in sys.modules:
    sys.modules["fmod_toolkit"] = types.ModuleType("fmod_toolkit")
