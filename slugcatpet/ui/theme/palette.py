"""界面调色板：前端面板共用的颜色值（字符串用于 QSS，QColor 用于自绘）。"""

from __future__ import annotations

from PySide6.QtGui import QColor

TEXT = "#e8f5d8"
TEXT_SOFT = "#cfe8b8"  # 标题 / 次要强调
TEXT_DIM = "#9fc080"  # 说明、幽灵按钮
TEXT_HINT = "#8fa878"  # 更弱的提示
TEXT_MENU_DISABLED = "#8a9a7a"
TEXT_DISABLED = "#777"
TEXT_ON_ACCENT = "#0f1a08"  # 主按钮上的字
TEXT_ON_DANGER = "#f5ded8"
TEXT_TOAST = "#fff"

ACCENT = "#aef156"  # 分区标题、选中
ACCENT_BTN = "#6aa34a"
ACCENT_BTN_HOVER = "#7cb45a"
DANGER = "#8c3b3b"
DANGER_HOVER = "#a34848"
WARN = "#e8c86a"
ERROR = "#e8a08a"

BORDER = "#4a5a3a"
RADIO_BORDER = "#52633f"
RADIO_BORDER_HOVER = "#7c9a52"
INPUT_BG = "#262b22"
TRACK_BG = "#2d3428"  # 进度条 / 卡片单选底

BG_WINDOW = "rgba(30,34,40,245)"  # 设置窗 / 菜单
BG_PANEL = "rgba(30,34,40,235)"  # HUD / 控制面板 / 标签栏
BG_CARD = "rgba(28,32,38,238)"  # 卡片弹窗 / 首次导入
BG_TOAST = "rgba(20,22,26,235)"
BTN_BG = "rgba(60,70,55,255)"
BTN_HOVER = "rgba(80,100,70,255)"
BTN_DISABLED = "rgba(45,48,52,255)"
HOVER_TINT = "rgba(120,150,100,40)"
DIVIDER = "rgba(120,150,100,90)"
ARROW_BG = "rgba(40,46,40,180)"
ARROW_HOVER = "rgba(60,72,55,255)"

BAR_BG = QColor(45, 52, 40)  # HUD 状态条底
BAR_FG = QColor(120, 180, 90)  # HUD 状态条
BAR_ICY = QColor(120, 200, 235)
BAR_OXY = QColor(110, 205, 195)
