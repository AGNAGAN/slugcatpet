"""各前端面板的样式表，由 palette 拼出。"""

from __future__ import annotations

from .palette import (
    ACCENT,
    ACCENT_BTN,
    ACCENT_BTN_HOVER,
    ARROW_BG,
    ARROW_HOVER,
    BG_CARD,
    BG_PANEL,
    BG_TOAST,
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

# 下拉框字号用 pt（9pt = 12px）：px 字号在 Windows 上首次弹出列表时会触发 QFont 警告
_COMBO_FONT = "QComboBox{font-size:9pt;}"

MENU = (
    f"QMenu{{background:{BG_WINDOW};border:1px solid {BORDER};border-radius:6px;"
    f"color:{TEXT};font-size:12px;padding:4px;}}"
    "QMenu::item{padding:5px 18px;border-radius:4px;}"
    f"QMenu::item:selected{{background:{BTN_HOVER};}}"
    f"QMenu::item:disabled{{color:{TEXT_MENU_DISABLED};}}"
    f"QMenu::separator{{height:1px;background:{DIVIDER};margin:4px 6px;}}"
)


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
    )


CARD = (
    "#cardShell{background:transparent;}"
    f"#cardRoot{{background:{BG_CARD};border-radius:14px;border:1px solid {BORDER};}}"
    f"#cardTitle{{color:{TEXT_SOFT};font-size:15px;font-weight:600;background:transparent;}}"
    f"#cardText{{color:{TEXT};font-size:13px;background:transparent;}}"
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
    f"QWidget{{background:{BG_PANEL};border-radius:8px;}}"
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
