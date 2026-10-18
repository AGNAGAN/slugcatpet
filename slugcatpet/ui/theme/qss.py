"""各面板的样式表，颜色取自 palette。"""

from __future__ import annotations

from ..._paths import resource_dir
from .palette import (
    ACCENT,
    ACCENT_BTN,
    ACCENT_BTN_HOVER,
    ARROW_BG,
    ARROW_HOVER,
    BG_CARD,
    BG_PANEL,
    BG_TOAST,
    BG_TOOLTIP,
    BG_WINDOW,
    BORDER,
    BTN_BG,
    BTN_DISABLED,
    BTN_HOVER,
    DANGER,
    DANGER_HOVER,
    DIVIDER,
    ERROR,
    HOVER_TINT,
    INPUT_BG,
    RADIO_BORDER,
    RADIO_BORDER_HOVER,
    TEXT,
    TEXT_DIM,
    TEXT_DISABLED,
    TEXT_HINT,
    TEXT_MENU_DISABLED,
    TEXT_ON_ACCENT,
    TEXT_ON_DANGER,
    TEXT_SOFT,
    TEXT_TOAST,
    TRACK_BG,
    WARN,
)

DIVIDER_LINE = f"background:{DIVIDER};border:none;"
SCROLLBAR = (
    "QScrollBar:vertical{background:transparent;width:8px;margin:0;}"
    f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:4px;min-height:24px;}}"
    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
)
HUD_SCROLL = (
    "QScrollArea{background:transparent;border:none;}#hudViewport{background:transparent;}" + SCROLLBAR
)
SLIDER = (
    f"QSlider::groove:horizontal{{height:6px;background:{TRACK_BG};border-radius:3px;}}"
    f"QSlider::sub-page:horizontal{{background:{ACCENT_BTN};border-radius:3px;}}"
    "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;border-radius:6px;"
    f"background:{ACCENT};}}"
)
# 悬停提示样式，拼在各顶层样式后
TOOLTIP = (
    f"QToolTip{{color:{TEXT};background:{BG_TOOLTIP};border:1px solid {BORDER};"
    "border-radius:4px;padding:4px 6px;font-size:12px;}"
)
DIM_TEXT = f"color:{TEXT_DIM};"
ERROR_TEXT = f"color:{ERROR};"
PAUSED_TEXT = f"color:{WARN};font-weight:bold;"

_BTN_PRIMARY = (
    f"#btnPrimary{{background:{ACCENT_BTN};color:{TEXT_ON_ACCENT};font-weight:600;border:none;}}"
    f"#btnPrimary:hover{{background:{ACCENT_BTN_HOVER};}}"
)
_BTN_GHOST = (
    f"#btnGhost{{background:transparent;color:{TEXT_DIM};border:1px solid {BORDER};}}"
    f"#btnGhost:hover{{background:{HOVER_TINT};}}"
)

# 下拉框字号（用 pt）
_COMBO_FONT = "QComboBox{font-size:9pt;}"

MENU = (
    f"QMenu{{background:{BG_WINDOW};border:1px solid {BORDER};border-radius:6px;"
    f"color:{TEXT};font-size:12px;padding:4px;}}"
    "QMenu::item{padding:5px 18px;border-radius:4px;}"
    f"QMenu::item:selected{{background:{BTN_HOVER};}}"
    f"QMenu::item:disabled{{color:{TEXT_MENU_DISABLED};}}"
    f"QMenu::separator{{height:1px;background:{DIVIDER};margin:4px 6px;}}"
)


def icon_url(name: str) -> str:
    """resources/icons 下图标的路径，供 QSS 的 url() 用。"""
    return (resource_dir() / "icons" / name).as_posix()


def settings_window(check_icon_url: str) -> str:
    return (
        f"QWidget{{background:{BG_WINDOW};color:{TEXT};font-size:12px;}}"
        f"QLabel{{color:{TEXT};}}"
        f"#secHeader{{color:{ACCENT};font-size:13px;font-weight:bold;}}"
        f"#dim{{color:{TEXT_DIM};}}"
        f"QPushButton{{color:{TEXT};background:{BTN_BG};border:1px solid {BORDER};"
        "border-radius:5px;padding:4px 12px;}"
        f"QPushButton:enabled:hover{{background:{BTN_HOVER};}}"
        f"QPushButton:disabled{{color:{TEXT_DISABLED};background:{BTN_DISABLED};}}"
        f"QCheckBox{{color:{TEXT};}}"
        "QCheckBox::indicator{width:14px;height:14px;border-radius:3px;"
        f"border:1px solid {RADIO_BORDER};background:{INPUT_BG};}}"
        f"QCheckBox::indicator:hover{{border-color:{RADIO_BORDER_HOVER};}}"
        f"QCheckBox::indicator:checked{{border-color:{ACCENT};background:{ACCENT};"
        f"image:url({check_icon_url});}}"
        f"QLineEdit{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};"
        "border-radius:5px;padding:2px 6px;}"
        "QScrollArea{border:none;}" + SCROLLBAR + f"#rangeEnd{{color:{TEXT_DIM};font-size:11px;}}"
        f"#rangeValue{{color:{ACCENT};min-width:34px;}}"
        + SLIDER
        + f"QComboBox,QSpinBox{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};"
        "border-radius:5px;padding:2px 8px;}"
        + _COMBO_FONT
        + f"QComboBox QAbstractItemView{{background:{INPUT_BG};color:{TEXT};}}"
        f"QRadioButton{{color:{TEXT};spacing:8px;}}"
        "QRadioButton::indicator{width:16px;height:16px;border-radius:8px;"
        f"border:1px solid {RADIO_BORDER};background:{INPUT_BG};}}"
        f"QRadioButton::indicator:hover{{border-color:{RADIO_BORDER_HOVER};}}"
        f"QRadioButton::indicator:checked{{border:2px solid {ACCENT};background:{ACCENT};"
        f"image:url({check_icon_url});}}"
        "QSpinBox{padding-right:16px;}"
        "QSpinBox::up-button,QSpinBox::down-button{width:14px;border:none;background:transparent;}"
        f"QSpinBox::up-button:hover,QSpinBox::down-button:hover{{background:{HOVER_TINT};}}"
        f"QSpinBox::up-arrow{{image:url({icon_url('arrow_up.svg')});width:8px;height:5px;}}"
        f"QSpinBox::down-arrow{{image:url({icon_url('arrow_down.svg')});width:8px;height:5px;}}" + TOOLTIP
    )


CARD = (
    "#cardShell{background:transparent;}"
    f"#cardRoot{{background:{BG_CARD};border-radius:14px;border:1px solid {BORDER};}}"
    f"#cardTitle{{color:{TEXT_SOFT};font-size:15px;font-weight:600;background:transparent;}}"
    f"#cardText{{color:{TEXT};font-size:13px;background:transparent;}}"
    f"#cardNote{{color:{TEXT_SOFT};font-size:13px;background:{INPUT_BG};border:1px solid {BORDER};"
    "border-radius:8px;padding:8px 10px;}"
    "#cardNote QScrollBar:vertical{width:6px;background:transparent;margin:0;}"
    f"#cardNote QScrollBar::handle:vertical{{background:{BORDER};border-radius:3px;min-height:20px;}}"
    "#cardNote QScrollBar::add-line:vertical,#cardNote QScrollBar::sub-line:vertical{height:0;}"
    "QLabel{background:transparent;}"
    "QPushButton{font-size:12px;padding:6px 14px;border-radius:8px;}"
    + _BTN_PRIMARY
    + _BTN_GHOST
    + f"#btnDanger{{background:{DANGER};color:{TEXT_ON_DANGER};font-weight:600;border:none;}}"
    f"#btnDanger:hover{{background:{DANGER_HOVER};}}"
    f"QRadioButton{{color:{TEXT};font-size:12px;spacing:8px;background:transparent;}}"
    "QRadioButton::indicator{width:13px;height:13px;border-radius:7px;"
    f"border:1px solid {BORDER};background:{TRACK_BG};}}"
    f"QRadioButton::indicator:checked{{background:{ACCENT_BTN_HOVER};border-color:{ACCENT_BTN_HOVER};}}"
    + TOOLTIP
)

PEARL_EDITOR = (
    CARD + f"QPlainTextEdit{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};border-radius:6px;"
    "padding:4px 6px;font-size:13px;}"
    + f"QCheckBox{{color:{TEXT};font-size:12px;spacing:8px;background:transparent;}}"
    + "QCheckBox::indicator{width:13px;height:13px;border-radius:3px;"
    + f"border:1px solid {BORDER};background:{INPUT_BG};}}"
    + f"QCheckBox::indicator:checked{{background:{ACCENT_BTN_HOVER};border-color:{ACCENT_BTN_HOVER};}}"
    + f"#pearlCount{{color:{TEXT_HINT};font-size:11px;background:transparent;}}"
    + "#pearlSwatch{border:2px solid transparent;border-radius:12px;padding:0;"
    + "min-width:24px;max-width:24px;min-height:24px;max-height:24px;}"
    + f"#pearlSwatch:checked{{border-color:{TEXT};}}"
)

FORM = (
    f"QLineEdit,QComboBox{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};"
    "border-radius:5px;padding:3px 6px;font-size:12px;}"
    + _COMBO_FONT
    + f"QComboBox QAbstractItemView{{background:{INPUT_BG};color:{TEXT};}}"
    f"QCheckBox{{color:{TEXT};font-size:12px;background:transparent;}}"
    f"#swatch{{border:1px solid {BORDER};border-radius:5px;min-width:56px;padding:3px;}}"
)

SKIN_LIST = (
    f"QListWidget{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};"
    "border-radius:6px;font-size:12px;outline:none;}"
    "QListWidget::item{padding:4px 6px;}"
    f"QListWidget::item:disabled{{color:{ACCENT};}}"
    f"QListWidget::item:selected{{background:{ACCENT_BTN};color:{TEXT_ON_ACCENT};}}"
)

LOOK_DIALOG = (
    SKIN_LIST
    + FORM
    + f"QRadioButton{{color:{TEXT};font-size:12px;background:transparent;}}"
    + f"#lookHead{{color:{TEXT_SOFT};font-size:12px;font-weight:600;background:transparent;}}"
    + "QCheckBox::indicator{width:13px;height:13px;border-radius:3px;"
    + f"border:1px solid {BORDER};background:{INPUT_BG};}}"
    + f"QCheckBox::indicator:checked{{background:{ACCENT_BTN_HOVER};border-color:{ACCENT_BTN_HOVER};}}"
    + f"#partsToggle{{background:transparent;color:{TEXT_DIM};border:none;padding:0;font-size:12px;}}"
    + "#partsBox{background:transparent;}"
    + f"#partsToggle:hover{{color:{TEXT};}}"
    + f"#partPack{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};border-radius:5px;"
    "padding:2px 6px;font-size:12px;text-align:left;}"
    + f"#partPack:hover{{background:{HOVER_TINT};}}"
    + "#partSwatch{background:transparent;border:none;padding:0;}"
    + "#partsScroll,#partsScroll > QWidget,#partsScroll > QWidget > QWidget{background:transparent;}"
    + SCROLLBAR
    + f"#partMini{{background:transparent;color:{TEXT_DIM};border:none;padding:0 2px;font-size:14px;}}"
    + f"#partMini:hover{{color:{ACCENT};}}"
)

LOOK_POP = (
    TOOLTIP
    + f"#lookPop{{background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;}}"
    + f"#lookHead{{color:{TEXT_SOFT};font-size:12px;font-weight:600;background:transparent;}}"
    + f"#cardText{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    + "#lookPopScroll,#lookPopScroll > QWidget > QWidget{background:transparent;}"
    + f"#packTile{{background:transparent;color:{TEXT};border:1px solid transparent;border-radius:6px;"
    "font-size:11px;padding:2px;}"
    + f"#packTile:hover{{background:{HOVER_TINT};}}"
    + f"#packTile:checked{{border-color:{ACCENT};}}"
    + "QSlider{background:transparent;}"
    + f"QSlider::groove:horizontal{{height:6px;background:{TRACK_BG};border-radius:3px;}}"
    + f"QSlider::sub-page:horizontal{{background:{ACCENT_BTN};border-radius:3px;}}"
    + "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;border-radius:6px;"
    + f"background:{ACCENT};}}"
)

SCENE_MUSIC = (
    FORM
    + f"#sceneHead{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    + f"#sceneName{{color:{TEXT};font-size:12px;background:transparent;}}"
    + f"QComboBox:disabled{{color:{TEXT_DISABLED};}}"
    + f"#scenePreview{{background:transparent;border:1px solid {BORDER};border-radius:11px;padding:0;}}"
    + f"#scenePreview:hover{{background:{HOVER_TINT};}}"
    + f"#scenePreview:checked{{background:{ACCENT_BTN};border-color:{ACCENT_BTN};}}"
    + f"#scenePreview:checked:hover{{background:{ACCENT_BTN_HOVER};}}"
    + f"#scenePreview:disabled{{border-color:{TRACK_BG};}}"
    + f"#segLeft,#segRight{{background:{INPUT_BG};color:{TEXT_DIM};border:1px solid {BORDER};"
    "padding:3px 10px;font-size:12px;border-radius:0;}"
    "#segLeft{border-top-left-radius:6px;border-bottom-left-radius:6px;}"
    "#segRight{border-left:none;border-top-right-radius:6px;border-bottom-right-radius:6px;}"
    + f"#segLeft:hover,#segRight:hover{{background:{HOVER_TINT};}}"
    + f"#segLeft:checked,#segRight:checked{{background:{ACCENT_BTN};color:{TEXT_ON_ACCENT};font-weight:600;}}"
    + f"#segLeft:disabled,#segRight:disabled{{background:transparent;color:{TEXT_DISABLED};}}"
    + f"#segLeft:checked:disabled,#segRight:checked:disabled{{background:{TRACK_BG};}}"
    + f"#sceneVol{{background:{INPUT_BG};color:{ACCENT};border:1px solid {BORDER};"
    "border-radius:6px;padding:3px 0;font-size:12px;}"
    + f"#sceneVol:hover{{border-color:{RADIO_BORDER_HOVER};}}"
    + f"#sceneVol:disabled{{color:{TEXT_DISABLED};border-color:{TRACK_BG};}}"
)

KEYBINDS = (
    f"#kbHint{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    f"#kbGroup{{color:{TEXT_SOFT};font-size:12px;font-weight:600;background:transparent;}}"
    f"#kbAction{{color:{TEXT};font-size:12px;background:transparent;}}"
    f"#keyCap{{background:{INPUT_BG};color:{ACCENT};border:1px solid {BORDER};"
    f"border-bottom:3px solid {BORDER};border-radius:6px;padding:4px 10px;"
    "font-size:12px;font-weight:600;min-width:84px;}"
    f"#keyCap:hover{{border-color:{RADIO_BORDER_HOVER};}}"
    f'#keyCap[listening="true"]{{color:{WARN};border-color:{WARN};background:{TRACK_BG};}}'
    f'#keyCap[flash="true"]{{border-color:{ACCENT};}}'
    f"#keyCapFixed{{background:{TRACK_BG};color:{TEXT_SOFT};border:1px solid {BORDER};"
    f"border-bottom:3px solid {BORDER};border-radius:6px;padding:4px 6px;"
    "font-size:12px;font-weight:600;min-width:92px;}"
    f'#keyCapFixed[taken="true"]{{color:{WARN};border-color:{WARN};text-decoration:line-through;}}'
    "#kbReset{background:transparent;border:none;padding:2px;border-radius:4px;}"
    f"#kbReset:hover{{background:{HOVER_TINT};}}"
    f"#kbStatus{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    f'#kbStatus[warn="true"]{{color:{WARN};}}'
)

BLUEPRINTS = (
    FORM + f"#bpHint{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    f"#bpCount{{color:{TEXT_DIM};font-size:12px;background:transparent;}}"
    "QScrollArea,#bpList{background:transparent;border:none;}"
    f"#bpCard{{background:{TRACK_BG};border:1px solid {BORDER};border-radius:8px;}}"
    f"#bpCard:hover{{border-color:{RADIO_BORDER_HOVER};}}"
    f'#bpCard[selected="true"]{{border:2px solid {ACCENT};}}'
    f"#bpName{{color:{TEXT};font-size:13px;font-weight:600;background:transparent;}}"
    f"#bpMeta{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    f'#bpMeta[warn="true"]{{color:{WARN};}}'
    f"#bpTag{{color:{ACCENT};font-size:11px;background:transparent;}}"
    "#bpCard QPushButton{font-size:11px;padding:3px 10px;border-radius:6px;}"
    f"#bpStatus{{color:{TEXT_DIM};font-size:11px;background:transparent;}}"
    f'#bpStatus[warn="true"]{{color:{WARN};}}'
    f"#btnGhost:disabled{{color:{TEXT_DISABLED};border-color:{BORDER};}}"
)

VOLUME_POP = (
    f"#volPop{{background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;}}"
    f"#volPopVal{{color:{ACCENT};font-size:11px;background:transparent;}}"
    "QSlider{background:transparent;}"
    f"QSlider::groove:vertical{{width:6px;background:{TRACK_BG};border-radius:3px;}}"
    f"QSlider::add-page:vertical{{background:{ACCENT_BTN};border-radius:3px;}}"
    "QSlider::handle:vertical{width:12px;height:12px;margin:0 -4px;border-radius:6px;"
    f"background:{ACCENT};}}"
)

HUD_PANEL = (
    f"#hudPanel{{background:{BG_PANEL};border-radius:10px;border:1px solid {BORDER};}}"
    f"QLabel{{color:{TEXT};font-size:12px;}}"
    f"#hudName{{color:{TEXT_DIM};font-size:12px;}}"
    f"#hudVal{{color:{TEXT_SOFT};font-size:11px;}}"
    f"#hudRowName{{color:{ACCENT};font-size:13px;font-weight:bold;}}"
)

CONTROL_PANEL = (
    f"#ctrlPanel{{background:{BG_PANEL};border-radius:10px;border:1px solid {BORDER};}}"
    f"#ctrlTitle{{color:{ACCENT};font-size:13px;font-weight:bold;}}"
    f"#ctrlKeys{{color:{TEXT_SOFT};font-size:11px;}}"
    f"QPushButton{{background:transparent;color:{TEXT_DIM};border:1px solid {BORDER};"
    "border-radius:8px;font-size:12px;padding:5px 12px;}"
    f"QPushButton:hover{{background:{HOVER_TINT};}}"
)

SETUP_CARD = (
    f"#setupCard{{background:{BG_CARD};border-radius:14px;"
    f"border:1px solid {BORDER};}}"
    f"#setupTitle{{color:{TEXT_SOFT};font-size:17px;font-weight:600;}}"
    f"#setupStatus{{color:{TEXT};font-size:13px;}}"
    f"#setupHint{{color:{TEXT_HINT};font-size:11px;}}"
    f"#setupBar{{background:{TRACK_BG};border:none;border-radius:3px;}}"
    f"#setupBar::chunk{{background:{ACCENT_BTN_HOVER};border-radius:3px;}}"
    "QPushButton{font-size:12px;padding:6px 14px;border-radius:8px;}" + _BTN_PRIMARY + _BTN_GHOST
)

TABBAR_PANEL = (
    f"#tabPanel{{background:{BG_PANEL};border-radius:8px;"
    "border-top-left-radius:0;border-bottom-left-radius:0;}"
    f"QPushButton{{color:{TEXT};background:{BTN_BG};border:1px solid {BORDER};"
    "border-radius:5px;font-size:12px;}"
    f"QPushButton:enabled:hover{{background:{BTN_HOVER};}}"
    f"QPushButton:disabled{{color:{TEXT_DISABLED};background:{BTN_DISABLED};}}"
)
TABBAR_ARROW = (
    f"QPushButton{{color:{TEXT_SOFT};background:{ARROW_BG};"
    "border:none;border-top-left-radius:8px;border-bottom-left-radius:8px;font-size:18px;}"
    f"QPushButton:hover{{background:{ARROW_HOVER};}}"
)

RAIN_CARD = (
    f"#rainCard{{background:{BG_CARD};border:1px solid {BORDER};border-radius:10px;}}"
    "QLabel{background:transparent;font-size:12px;}"
    f"#rainHead{{color:{TEXT_SOFT};font-size:13px;font-weight:600;}}"
    f"#rainLabel{{color:{TEXT_DIM};}}"
    f"#rainPreview{{color:{TEXT_SOFT};}}"
    f"QPushButton{{color:{TEXT};background:{BTN_BG};border:1px solid {BORDER};"
    "border-radius:5px;padding:4px 10px;font-size:12px;}"
    f"QPushButton:hover{{background:{BTN_HOVER};}}"
    f"QPushButton:checked{{background:{ACCENT_BTN};color:{TEXT_ON_ACCENT};border-color:{ACCENT_BTN};}}"
    f"QPushButton:checked:hover{{background:{ACCENT_BTN_HOVER};}}"
    "#rainChip{padding:4px 0;min-width:30px;}"
    f"QLineEdit{{background:{INPUT_BG};color:{TEXT};border:1px solid {BORDER};"
    "border-radius:5px;padding:3px 4px;font-size:12px;}"
    f'QLineEdit[bad="true"]{{border-color:{ERROR};}}'
    f"QCheckBox{{color:{TEXT_DIM};font-size:12px;background:transparent;}}"
    "QCheckBox::indicator{width:13px;height:13px;border-radius:3px;"
    f"border:1px solid {RADIO_BORDER};background:{INPUT_BG};}}"
    f"QCheckBox::indicator:checked{{border-color:{ACCENT};background:{ACCENT};"
    f"image:url({icon_url('check.svg')});}}"
    f"#rainDivider{{{DIVIDER_LINE}}}" + TOOLTIP
)

TOAST = (
    f"QLabel{{color:{TEXT_TOAST};background:{BG_TOAST};border-radius:6px;padding:5px 9px;font-size:12px;}}"
)

MUSIC_EXTRA = (
    f"#nowPlaying{{color:{ACCENT};font-weight:bold;}}"
    f"QListWidget{{background:{INPUT_BG};border:1px solid {BORDER};border-radius:6px;"
    f"color:{TEXT};padding:2px;outline:none;}}"
    "QListWidget::item{padding:4px 6px;border-radius:4px;}"
    f"QListWidget::item:selected{{background:{BTN_HOVER};}}"
    f"QListWidget::item:hover{{background:{HOVER_TINT};}}"
    "#transport{background:transparent;border:none;border-radius:15px;padding:0;}"
    f"#transport:hover{{background:{HOVER_TINT};}}"
    f"#transport:pressed{{background:{BTN_HOVER};}}"
    f"#transportMain{{background:{ACCENT_BTN};border:none;border-radius:18px;padding:0;}}"
    f"#transportMain:hover{{background:{ACCENT_BTN_HOVER};}}"
    f"#transportMain:pressed{{background:{ACCENT};}}"
)
