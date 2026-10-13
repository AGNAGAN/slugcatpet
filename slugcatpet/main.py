"""启动应用，管理 PetWindow、TabBar、托盘、全局热键。"""

from __future__ import annotations
import sys
import os
import json
import signal
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter
from PySide6.QtCore import QTimer

from .characters import default_def
from .window import PetWindow
from .ui.panels.tabbar import TabBar
from .ui.panels.hud import HudPanel
from .ui.panels.settings import SettingsWindow
from .control.hotkey import HotkeyFilter, MOD_CONTROL, MOD_ALT, HK_PLACE_ESC
from .platform import cursorfx
from ._paths import user_dir
from .i18n import t

VK_Q = 0x51
VK_X = 0x58
VK_H = 0x48
HK_ABORT = 1
HK_QUIT = 2
HK_HUD = 3
_APP_PARAMS = user_dir() / "app.json"
SCHEMA_VERSION = 2  # pets[] 分猫存档
AUTOSAVE_MS = 60_000


def _tray_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setBrush(QColor(*default_def().body_color))
    p.setPen(QColor(40, 80, 20))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pm)


def _migrate_params(params: dict) -> dict:
    """旧 schema 迁移为 v2。"""
    if params.get("schema_version") == SCHEMA_VERSION and isinstance(params.get("pets"), list):
        return params
    from . import tuning

    old_keys = ("energy", "temper", "food", "karma", "cold", "dead")
    if any(k in params for k in old_keys) or not params.get("pets"):
        pet_state = {
            "id": "pet-0",
            "variant": "saint",
            "energy": params.pop("energy", 1.0),
            "temper": params.pop("temper", 0.0),
            "food": params.pop("food", tuning.FOOD_INIT),
            "karma": params.pop("karma", tuning.KARMA_INIT),
            "cold": params.pop("cold", 0.0),
            "dead": params.pop("dead", False),
        }
        params["pets"] = [pet_state]
    params["schema_version"] = SCHEMA_VERSION
    return params


_DROPPED_KEYS = (
    "music_water_enabled",
    "music_hud_enabled",
    "music_theme_loop",
    "music_hud_ambient_ms",
    "music_hud_ambient_ts",
)  # 不再读取的设置键，载入时丢弃


def _load_params(path: Path | None = None) -> dict:
    p = path or _APP_PARAMS
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    for k in _DROPPED_KEYS:
        raw.pop(k, None)
    return _migrate_params(raw)


def _save_params(params: dict, path: Path | None = None):
    """原子写盘，失败重试。"""
    p = path or _APP_PARAMS
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, p)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.01)
    except Exception as e:
        print("[slugcatpet] save failed:", ascii(e), file=sys.stderr)


def setup_signal_handling(app):
    def _h(sig, frame):
        app.quit()

    signal.signal(signal.SIGINT, _h)
    t = QTimer()
    t.timeout.connect(lambda: None)
    t.start(500)  # 唤醒让 CPython 跑 SIGINT handler
    return t


def _ensure_assets_interactive() -> bool:
    from .gameassets import atlases_present
    from ._paths import assets_dir

    if atlases_present(assets_dir()):
        return True
    from .ui.panels.setup_panel import SetupPanel

    return SetupPanel().run()


def _extract_scene_music_later(names):
    """缺游戏配乐且找得到游戏时在后台补提取；这次启动没赶上的下次就有。"""
    from .gameassets import detect_install, extract_music, music_missing, prune_music

    prune_music(names)
    if not music_missing(names):
        return

    def run():
        try:
            install = detect_install()
            if install is not None:
                extract_music(install, names)
        except Exception:
            pass

    import threading

    threading.Thread(target=run, name="scene-music", daemon=True).start()


def main():
    from .platform.appid import set_app_id

    set_app_id()  # 须在建任何窗口之前
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from .platform.singleton import SingleInstance

    si = SingleInstance()
    if not si.acquire():
        si.notify_primary()
        return
    app._singleton = si  # 保持引用

    _sig = setup_signal_handling(app)  # 保持引用

    params = _load_params()
    from . import i18n

    i18n.set_lang(params.get("lang"))
    params.setdefault("lang", i18n.LANG)  # 首次启动按系统语言定下，之后不随系统变

    if not _ensure_assets_interactive():
        return

    from . import skins

    skins.configure(params.get("skins_scan_external", True))
    skins.reload()
    from .skins.folder import ensure_folder

    ensure_folder()  # 不导出模板

    pet = PetWindow(params=params)
    pet.show()

    hud = HudPanel(pet, params)
    if params.get("hud_visible"):
        hud.toggle_visible()

    tab = TabBar(pet, app, params)
    tab.show()

    def _write_state():
        params["tab_y"] = tab._y
        params["tab_expanded"] = tab.expanded
        params["hud_x"] = hud.x()
        params["hud_y"] = hud.y()
        params["pets"] = [
            {
                "id": p.id,
                "variant": p.variant,
                **p.look_state(),
                "name": p.name,
                "hidden": p.hidden,
                "energy": p.body.energy,
                "temper": p.body.temper,
                "food": p.body.food,
                "karma": p.body.karma,
                "cold": p.body.cold,
                "dead": p.behavior is not None and p.behavior.is_truly_dead(),
            }
            for p in pet.all_pets()
        ]
        params["skins_scan_external"] = skins.scan_external()
        params["schema_version"] = SCHEMA_VERSION
        _save_params(params)

    settings = SettingsWindow(pet, hud, _write_state)
    pet._hud = hud  # 供增删猫后 rebuild_rows
    pet._pets_changed_cb = _write_state
    pet._open_settings_cb = settings.open
    app._settings = settings

    if params.get("tab_expanded", True):
        tab.toggle()

    def _watch_skins():
        if pet.reload_skins(force=False) and settings.isVisible():
            settings._rebuild()

    skin_timer = QTimer()
    skin_timer.timeout.connect(_watch_skins)
    skin_timer.start(4000)
    app._skin_timer = skin_timer

    tray = QSystemTrayIcon(_tray_icon())
    menu = QMenu()

    # 音乐：播放列表 = 音乐目录 + 导入的歌；游戏配乐是从游戏里提取到 assets/music 的
    from .audio import MusicDirector, MusicPlayer
    from .audio.director import GAME_TRACKS
    from .ui.panels.musicpanel import MusicPanel
    from ._paths import music_asset_dirs, user_music_dir

    def _save_music_state():
        params["music_mode"] = player.mode
        params["music_volume"] = player.volume
        params["mute_all"] = player.muted
        params["music_tracks"] = [str(tr.path) for tr in player.tracks]
        params["music_hidden"] = player.hidden
        params["music_sources"] = player.sources
        cur = player.current()
        if cur is not None:
            params["music_last_track"] = str(cur.path)
            params["music_last_ms"] = 0 if player.is_special_active else player.position()
        _save_params(params)

    player = MusicPlayer(params, on_change=_save_music_state, theme_dirs=music_asset_dirs())
    _extract_scene_music_later(GAME_TRACKS)
    saved_tracks = params.get("music_tracks")
    if isinstance(saved_tracks, list):
        player.add_paths([p for p in saved_tracks if Path(p).is_file()], record=False)
    player.add_paths([user_music_dir()])
    player.restore_state(params.get("music_last_track"), int(params.get("music_last_ms", 0) or 0))
    director = MusicDirector(player, params)
    pet.env_listeners.append(director.on_env)
    settings.visible_changed.connect(director.on_settings)
    music = MusicPanel(player, _write_state)
    pet._open_music_cb = music.open
    pet._music_player = player
    pet._music_director = director
    app._music = (player, director, music)

    def _start_scene_music():
        env = next((k for k in ("blizzard", "zerog", "water") if getattr(pet, f"{k}_on", False)), "none")
        director.start(env)

    QTimer.singleShot(300, _start_scene_music)

    def _build_tray_menu():
        tray.setToolTip(t("app_title"))
        menu.clear()
        menu.addAction(t("tray_settings"), settings.open)
        menu.addAction(t("tray_music"), music.open)
        menu.addAction(t("tray_hud"), hud.toggle_visible)
        menu.addAction(t("refresh_top"), pet.refresh_top)
        menu.addAction(t("tray_abort"), cursorfx.abort_all)
        menu.addSeparator()
        other = "en" if i18n.LANG == "zh" else "zh"
        menu.addAction(i18n.lang_name(other), lambda: _set_lang(other))
        menu.addSeparator()
        menu.addAction(t("tray_quit"), app.quit)

    def _set_lang(lang):
        if lang == i18n.LANG:
            return
        i18n.set_lang(lang)
        params["lang"] = lang
        tab.rebuild_ui()
        hud.rebuild_rows()
        settings._rebuild()
        music._rebuild()
        _build_tray_menu()
        from .skins.folder import ensure_folder, write_report

        ensure_folder()
        write_report()
        _write_state()

    pet._set_lang_cb = _set_lang
    _build_tray_menu()
    tray.setContextMenu(menu)
    tray.show()
    tray.showMessage(t("app_title"), t("tray_started"), QSystemTrayIcon.MessageIcon.Information, 4000)

    si.on_secondary_attempt = lambda: tray.showMessage(
        t("app_title"), t("already_running"), QSystemTrayIcon.MessageIcon.Information, 4000
    )

    hotkey = HotkeyFilter()
    app.installNativeEventFilter(hotkey)
    hotkey.register(HK_ABORT, MOD_CONTROL | MOD_ALT, VK_Q)
    hotkey.register(HK_QUIT, MOD_CONTROL | MOD_ALT, VK_X)
    hotkey.register(HK_HUD, MOD_CONTROL | MOD_ALT, VK_H)
    pet._hotkey_filter = hotkey  # 放置模式临时挂/摘 Esc

    def _on_hotkey(hk_id):
        if hk_id == HK_QUIT:
            app.quit()
        elif hk_id == HK_HUD:
            hud.toggle_visible()
        elif hk_id == HK_PLACE_ESC:
            pet._exit_place_mode()
        else:
            cursorfx.abort_all()

    hotkey.triggered.connect(_on_hotkey)
    app._hotkey = hotkey

    autosave = QTimer()
    autosave.timeout.connect(_write_state)
    autosave.start(AUTOSAVE_MS)
    app._autosave = autosave

    from .platform.envwatch import EnvironmentWatcher

    envwatch = EnvironmentWatcher([pet, tab, hud, settings, music], pet)
    envwatch.start()
    pet._refresh_top_cb = envwatch.force_top
    app._envwatch = envwatch

    def _cleanup():
        pet.shutdown()
        app.removeNativeEventFilter(hotkey)  # 关停期需先摘 filter，防虚方法 dispatch 崩溃
        cursorfx.abort_all()
        try:
            from .control.mouse import set_passthrough

            if pet._hwnd:
                set_passthrough(pet._hwnd, False)
        except Exception:
            pass
        envwatch.stop()
        autosave.stop()
        _write_state()
        hotkey.unregister_all()

    app.aboutToQuit.connect(_cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
