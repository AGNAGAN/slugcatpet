"""键位表：动作与 Qt 键的对应，文件缺失或损坏时用默认。"""

from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import Qt

from .._paths import user_dir

# 动作 → Qt 键名（去掉 Key_ 前缀）
DEFAULT_KEYBINDS = {
    "left": "A",
    "right": "D",
    "up": "W",
    "down": "S",
    "jump": "Space",
    "grab": "K",
    "throw": "J",
    "hold": "F",
    "meow": "M",
}
ACTIONS = tuple(DEFAULT_KEYBINDS)
RESERVED = frozenset({"Escape", "Meta"})  # Esc 退出控制，Win 键被系统截走
_SPARE_KEYS = ("F", "G", "R", "T", "Y", "U", "I", "O", "L", "H")  # 新增动作的默认键被占时依次换用


def _default_path() -> Path:
    return user_dir() / "keybinds.json"


def _to_qt_key(name: str) -> int | None:
    key = getattr(Qt.Key, "Key_" + name, None)
    return None if key is None else int(key)


def normalize_key(qt_key: int) -> int:
    """Shift+Tab 产生的 Backtab 归为 Tab。"""
    return int(Qt.Key.Key_Tab) if qt_key == int(Qt.Key.Key_Backtab) else int(qt_key)


def key_name(qt_key: int) -> str | None:
    """Qt 键 → 键名；未知键和保留键返回 None。"""
    qt_key = normalize_key(qt_key)
    try:
        name = Qt.Key(qt_key).name
    except ValueError:
        return None
    if not name.startswith("Key_"):
        return None
    name = name[4:]
    return None if name in RESERVED or name == "unknown" else name


def load_key_names(path=None) -> dict[str, str]:
    """读动作 → 键名表；文件不存在时写入默认，损坏时用默认。"""
    p = Path(path) if path is not None else _default_path()
    names = dict(DEFAULT_KEYBINDS)
    if not p.exists():
        try:
            p.write_text(json.dumps(DEFAULT_KEYBINDS, indent=2), encoding="utf-8")
        except Exception:
            pass
        return names
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return names
    if isinstance(loaded, dict):
        missing = []
        for action in ACTIONS:
            v = loaded.get(action)
            if isinstance(v, str) and v not in RESERVED and _to_qt_key(v) is not None:
                names[action] = v
            else:
                missing.append(action)
        for action in missing:  # 默认键已被别的动作占了就换一个空闲的
            used = {names[a] for a in ACTIONS if a != action}
            if names[action] in used:
                names[action] = next(k for k in _SPARE_KEYS if k not in used)
    return names


def save_key_names(names: dict[str, str], path=None) -> bool:
    """写键位表，成功返回 True。"""
    p = Path(path) if path is not None else _default_path()
    data = {a: names.get(a, DEFAULT_KEYBINDS[a]) for a in ACTIONS}
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        return False
    return True


def load_keymap(path=None) -> dict[str, int]:
    names = load_key_names(path)
    return {action: _to_qt_key(name) for action, name in names.items()}
