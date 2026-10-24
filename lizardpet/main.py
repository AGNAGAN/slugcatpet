"""蜥蜴桌宠入口：无猫的 PetWindow + 精简侧边栏 + 托盘；场上物品存到 lizardpet.json。"""

from __future__ import annotations

import json
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

APP_ID = "LizardPet"
SCENE_FILE = "lizardpet.json"
AUTOSAVE_MS = 30_000
TRAY_SPRITE = "Kill_Green_Lizard"  # 原版生物图标，颜色取绿蜥蜴的 standard_color
TRAY_TINT = QColor.fromRgbF(0.2, 1.0, 0.0)
TRAY_SIZE = 32


def _tray_icon(atlas) -> QIcon:
    """游戏图集里的绿蜥蜴生物图标着色；取不到时画个绿圆。"""
    pm = QPixmap(TRAY_SIZE, TRAY_SIZE)
    pm.fill(QColor(0, 0, 0, 0))
    try:
        spr = atlas.sprite("ui", TRAY_SPRITE, TRAY_TINT, padded=False)
        spr = spr.scaled(
            TRAY_SIZE,
            TRAY_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p = QPainter(pm)
        p.drawPixmap((TRAY_SIZE - spr.width()) // 2, (TRAY_SIZE - spr.height()) // 2, spr)
        p.end()
    except Exception:
        p = QPainter(pm)
        p.setBrush(TRAY_TINT)
        p.drawEllipse(4, 4, TRAY_SIZE - 8, TRAY_SIZE - 8)
        p.end()
    return QIcon(pm)


def _ensure_assets() -> bool:
    """缺图集或蜥蜴音效时，用引导面板提取完再启动，和蛞蝓猫首次启动一样。"""
    from slugcatpet._paths import assets_dir
    from slugcatpet.gameassets import atlases_present
    from slugcatpet.items.lizard.assets import extract_lizard_sounds, lizard_sounds_missing

    if atlases_present(assets_dir()) and not lizard_sounds_missing():
        return True
    from slugcatpet.ui.panels.setup_panel import SetupPanel

    return SetupPanel(extras=(extract_lizard_sounds,)).run()


def _load(path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def main():
    from slugcatpet.platform.appid import set_app_id

    set_app_id(APP_ID)  # 须在建任何窗口之前
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from slugcatpet._paths import user_dir
    from slugcatpet.platform.singleton import SingleInstance

    si = SingleInstance(key="lizardpet-single-instance", lock_path=user_dir() / "lizardpet.lock")
    if not si.acquire():
        si.notify_primary()
        return
    app._singleton = si  # 保持引用

    from slugcatpet.platform import autostart

    autostart.configure(APP_ID, "run_lizardpet.py")
    autostart.sync_path()

    from slugcatpet import i18n, items
    from slugcatpet.main import _save_params, setup_signal_handling

    items.set_app(items.LIZARD)  # 须在建 PetWindow 之前
    _sig = setup_signal_handling(app)  # 保持引用

    path = user_dir() / SCENE_FILE
    params = _load(path)
    i18n.set_lang(params.get("lang"))
    params.setdefault("lang", i18n.LANG)
    i18n.alias("app_title", "lz_app_title")
    i18n.alias("already_running", "lz_already_running")

    if not _ensure_assets():
        return

    from slugcatpet.items.lizard import sfx

    sfx.set_muted(not params.get("sound", True))
    sfx.warmup()  # 建音频设备要几百毫秒，趁还没开始 tick
    sfx.load_all()

    from slugcatpet.items import scene
    from slugcatpet.platform.topmost import own_by
    from slugcatpet.window import PetWindow

    from .sidebar import LizardSideBar

    pet = PetWindow(params=params, catless=True)
    pet.show()
    sfx.set_listener_width(lambda: pet._WL)
    if "scene" in params:
        scene.restore(pet, params["scene"])
    else:  # 首次启动放一只绿蜥蜴
        pet.place("lizard_green", pet._WL * 0.5, pet._HL - 30.0)

    tab = LizardSideBar(pet, app, params)
    own_by(pet, tab)
    params.pop("sidebar_visible", None)  # 不记显隐：每次启动都显示侧边栏
    tab.show()
    if params.get("tab_expanded", True):
        tab.toggle()

    def _write_state():
        params["scene"] = scene.capture(pet)
        params["tab_y"] = tab._y
        params["tab_expanded"] = tab.expanded
        _save_params(params, path)

    tray = QSystemTrayIcon(_tray_icon(pet.atlas))
    tray.setToolTip(i18n.t("app_title"))
    menu = QMenu()

    def _toggle_sidebar():
        tab.setVisible(not tab.isVisible())

    def _set_autostart(on):
        autostart.set_enabled(on)

    def _set_sound(on):
        sfx.set_muted(not on)
        params["sound"] = bool(on)

    def _build_menu():
        menu.clear()
        menu.addAction(i18n.t("lz_tray_sidebar"), _toggle_sidebar)
        menu.addAction(i18n.t("lz_tray_clear"), pet.clear_all_items)
        snd = menu.addAction(i18n.t("lz_tray_sound"))
        snd.setCheckable(True)
        snd.setChecked(not sfx.is_muted())
        snd.triggered.connect(_set_sound)
        menu.addSeparator()
        other = "en" if i18n.LANG == "zh" else "zh"
        menu.addAction(i18n.lang_name(other), lambda: _set_lang(other))
        auto = menu.addAction(i18n.t("lz_tray_autostart"))
        auto.setCheckable(True)
        auto.setChecked(autostart.is_enabled())
        auto.triggered.connect(_set_autostart)
        menu.addSeparator()
        menu.addAction(i18n.t("tray_quit"), app.quit)

    def _set_lang(lang):
        if lang == i18n.LANG:
            return
        i18n.set_lang(lang)
        params["lang"] = lang
        tab.rebuild_ui()
        tray.setToolTip(i18n.t("app_title"))
        _build_menu()
        _write_state()

    _build_menu()
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: _toggle_sidebar() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.show()
    tray.showMessage(
        i18n.t("app_title"), i18n.t("lz_tray_started"), QSystemTrayIcon.MessageIcon.Information, 4000
    )
    si.on_secondary_attempt = lambda: tray.showMessage(
        i18n.t("app_title"), i18n.t("already_running"), QSystemTrayIcon.MessageIcon.Information, 4000
    )

    # 放置模式下 Esc 退出
    from slugcatpet.control.hotkey import HK_PLACE_ESC, HotkeyFilter

    hotkey = HotkeyFilter()
    hotkey.install(app)
    pet._hotkey_filter = hotkey
    hotkey.triggered.connect(lambda hk_id: pet._exit_place_mode() if hk_id == HK_PLACE_ESC else None)
    app._hotkey = hotkey

    autosave = QTimer()
    autosave.timeout.connect(_write_state)
    autosave.start(AUTOSAVE_MS)
    app._autosave = autosave

    from slugcatpet.platform.envwatch import EnvironmentWatcher

    envwatch = EnvironmentWatcher([pet, tab], pet)  # 先下后上：侧边栏盖在桌宠层上
    envwatch.start()
    pet._refresh_top_cb = envwatch.force_top
    app._envwatch = envwatch

    def _cleanup():
        pet.shutdown()
        hotkey.uninstall(app)  # 先摘掉原生事件过滤器，免得关停时回调进来崩溃
        try:
            from slugcatpet.control.mouse import set_passthrough

            if pet._hwnd:
                set_passthrough(pet._hwnd, False)
        except Exception:
            pass
        envwatch.stop()
        sfx.shutdown()
        autosave.stop()
        _write_state()
        hotkey.unregister_all()

    app.aboutToQuit.connect(_cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
