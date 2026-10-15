"""猫菜单，右键猫身和左键 HUD 行共用。"""

from __future__ import annotations
from PySide6.QtWidgets import QMenu

from ...characters import REGISTRY
from ... import i18n
from ...i18n import t
from ..theme import qss

_MENU_QSS = qss.MENU


def variant_label(variant: str) -> str:
    d = REGISTRY.get(variant)
    if d is not None and d.names:
        names = d.names
        return names.get(i18n.LANG) or names.get("en") or next(iter(names.values()))
    if variant in REGISTRY:
        return t(f"variant_{variant}")
    return variant


def pet_label(pet, pets, use_name=True) -> str:
    """猫的显示名：起了名字就用名字，否则猫种名，同种加序号。"""
    if use_name and getattr(pet, "name", ""):
        return pet.name
    base = variant_label(pet.variant)
    same = [p for p in pets if p.variant == pet.variant]
    if len(same) > 1:
        return f"{base} #{same.index(pet) + 1}"
    return base


def _add_hold(menu, pet, enabled):
    """定身开关；定身时再加姿势、视线子菜单。"""
    from ...behaviors.hold import AROUND, CURSOR, LIE, LOCK, SLEEP, STAND

    spec = pet.held
    act = menu.addAction(t("menu_hold"))
    act.setCheckable(True)
    act.setChecked(spec is not None)
    act.setEnabled(enabled or spec is not None)
    act.triggered.connect(lambda on: pet.set_held(on))
    if spec is None:
        return

    def pick(sub, items, current, apply):
        for key, label in items:
            a = sub.addAction(t(label))
            a.setCheckable(True)
            a.setChecked(current == key)
            a.triggered.connect(lambda _c=False, k=key: apply(k))

    pose = menu.addMenu(t("menu_hold_pose"))
    pose.setEnabled(not pet.body.on_pole)
    pick(
        pose,
        ((STAND, "hold_pose_stand"), (LIE, "hold_pose_lie"), (SLEEP, "hold_pose_sleep")),
        spec.pose,
        lambda k: setattr(spec, "pose", k),
    )

    def set_gaze(k):
        spec.gaze, spec.lock = k, None

    gaze = menu.addMenu(t("menu_hold_gaze"))
    pick(
        gaze,
        ((CURSOR, "hold_gaze_cursor"), (AROUND, "hold_gaze_around"), (LOCK, "hold_gaze_lock")),
        spec.gaze,
        set_gaze,
    )


def build_cat_menu(pet, pets=None, open_settings=None, parent=None) -> QMenu:
    pets = pets if pets is not None else list(getattr(pet.window, "pets", [pet]))
    label = pet_label(pet, pets)
    menu = QMenu(parent)
    menu.setTitle(label)
    menu.setStyleSheet(_MENU_QSS)
    header = menu.addAction(label)
    header.setEnabled(False)
    menu.addSeparator()

    if getattr(pet.window, "frozen", False):
        # 定格时只能解除定格
        menu.addAction(t("menu_unfreeze")).triggered.connect(lambda: pet.window.set_frozen(False))
        s = menu.addAction(t("menu_open_settings"))
        if open_settings is not None:
            s.triggered.connect(lambda: open_settings())
        return menu

    beh = pet.behavior
    reinc = beh is not None and beh.is_reincarnating()
    dead = beh is not None and beh.is_truly_dead()
    blocked = beh is not None and beh.blocks_interaction()  # 独占特效期禁杀
    if getattr(pet, "controlled", False):
        # 受控猫仅退出控制；闭包现查防重入
        exit_act = menu.addAction(t("menu_exit_control"))
        exit_act.triggered.connect(
            lambda: pet.window.stop_control() if getattr(pet, "controlled", False) else None
        )
    elif reinc:
        menu.addAction(t("menu_reincarnating")).setEnabled(False)
    elif dead:
        menu.addAction(t("menu_reset_pet")).triggered.connect(lambda: pet.respawn())
    else:
        act = menu.addAction(t("menu_kill_pet"))
        # 飞升/挂确认期置灰
        act.setEnabled(not blocked and pet._kill_dialog is None)
        act.triggered.connect(lambda: pet.window.request_kill(pet))
        ctl = menu.addAction(t("menu_control_pet"))
        ctl.setEnabled(not blocked and pet._kill_dialog is None)
        ctl.triggered.connect(lambda: pet.window.start_control(pet))
        _add_hold(menu, pet, not blocked and pet._kill_dialog is None)

    w = pet.window
    if not getattr(pet, "controlled", False):
        hide = menu.addAction(t("menu_hide_pet"))
        hide.setEnabled(len(w.pets) > 1)
        hide.triggered.connect(lambda: w.hide_pet(pet))
    if len(w.held_pets()) > 1:
        menu.addAction(t("menu_release_all_held")).triggered.connect(w.release_all_held)
    if getattr(w, "_hidden_pets", None):
        menu.addAction(t("menu_show_all")).triggered.connect(w.show_all_pets)
    menu.addAction(t("refresh_top")).triggered.connect(lambda: pet.window.refresh_top())
    s = menu.addAction(t("menu_open_settings"))
    if open_settings is not None:
        s.triggered.connect(lambda: open_settings())
    return menu
