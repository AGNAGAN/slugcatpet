# Phase 1 前置条件落实记录

- 日期：2026-10-20
- 范围：只落实 Phase 0 结论中进入 Phase 1 前必须解决的四项前置条件，不包含完整的 KWin 桥接、几何定位和置顶实现。
- 结论：**四项前置条件均已落地并在 KDE Plasma 6.8 / KWin 6.8 / Wayland 上实测通过**。
- 后续：完整的 KWin 桥、主表面几何和光标接入已在 `ai-docs/PHASE1_RESULTS.md` 完成。

---

## 1. 输入区域提交

新增 `slugcatpet/platform/wayland/input.py`：

- `set_input_region(window, region)` 统一执行：
  1. `window.setMask(region)`
  2. `window.requestUpdate()`
- `requestUpdate()` 是必需步骤；否则 Qt 只发送 `wl_surface.set_input_region`，没有对应的 `wl_surface.commit`。
- `region` 为空时自动改成表面外 1×1；不使用空 `QRegion`，避免被编码成 `set_input_region(nil)` 而变成整窗接收输入。

`PetWindow` 在 Wayland 下不再调用 Windows 的 `set_passthrough()`，改为动态输入区域：

- 宠物身体、物品、嵌入面板都计入区域；
- 宠物和物品使用渲染逻辑坐标乘以 `canvas_scale`；
- 嵌入控件已经是 overlay 本地坐标，不再乘 scale；
- 拖拽、抓取、放置模式和 debug 模式临时使用整窗区域；
- 无交互区域时完全穿透；
- 输入区域变化以约 30 Hz 节流，并在窗口显示、尺寸变化、面板显隐时强制刷新。

新增 `slugcatpet/platform/wayland/regions.py` 生成区域，新增 `tests/test_wayland_regions.py` 覆盖缩放、面板坐标、空区域和 `requestUpdate()` 提交。

---

## 2. 子控件本地坐标

`TabBar`、`HudPanel`、`ControlHud`、`RainDial` 新增 `embedded=` / `parent=` 模式。Wayland 下由 `main.py` 把它们作为 `PetWindow` 子控件创建，Windows 仍保持原来的顶层窗口路径。

改造内容：

- `TabBar._screen` 在嵌入时取 `overlay.rect()`，收起/展开/动画/箭头拖动全部使用 overlay 本地坐标；
- `HudPanel` 的 `_place()`、`_move_to()` 和拖动改为本地坐标，保存的 `hud_x/hud_y` 也变为 overlay 本地坐标；
- `ControlHud` 的 `_place()`、暂停后重心重排、鼠标拖动改为本地坐标；
- `RainDial` 的 `_place()` 和拖动改为本地坐标；卡片/提示的锚点通过 `mapToGlobal()` 转回全局坐标；
- 四个控件都监听 overlay 的 resize 事件重新布局；
- `EnvironmentWatcher` 在 Wayland 下只把 overlay 当作置顶窗口，嵌入控件放入 `plain`，避免对子控件调用 `winId()` 做置顶。

---

## 3. 目标输出 `setScreen()` 绑定

`PetWindow` 在 Wayland 下：

- 创建时先对目标 `QScreen` 调用 `setScreen(screen)`，再 `show()`；
- 不再调用无效的全局 `move(area.x(), area.y())`；
- 主屏变化时在 `_watch_screen()` 中重新绑定；
- `apply_workspace()` 根据工作区中心对应的屏幕重新绑定。

实测主屏 `eDP-1` 上窗口 DPR 为 2.0，未再出现“先落在 HDMI 后搬到 eDP，DPR 仍是 1.5”的问题。

---

## 4. 嵌入后 ControlHud 焦点 / 暂停复验

- 嵌入模式 `showEvent()` 激活 overlay 表面，再 `setFocus()`，不再调用子控件自身的顶层 `activateWindow()`；
- `focusOutEvent()` 仍暂停，`focusInEvent()` 恢复；
- 暂停时的文字切换和重心重排限制在 overlay 本地矩形内；
- 鼠标拖动使用 overlay 局部坐标。

实测结果：

```text
CTRL_GEO QRect(540, 752, 359, 124) CTRL_PARENT True CTRL_FOCUS True PAUSED False
CTRL_KEY 68 HELD [68] X 1
AFTER_CLEAR_FOCUS None PAUSED True X 0
AFTER_REFOCUS True PAUSED False
```

说明真实键盘事件到达 ControlHud，`D` 键正确得到 `x=1`；失焦后暂停并清空输入，重新聚焦后恢复。

---

## 5. 实测记录

### 5.1 输入区域与点击路由

用 KWin 脚本把目标窗口和桌宠窗口放在 `eDP-1`，用 uinput 绝对指针点击：

```text
click outside pet
TARGET_CLICK 500 72

click pet
PET_CLICK 720 846

click tab arrow
TAB_MID False GEO QRect(1416, 341, 24, 48)
```

结论：

- overlay 区域外的点击落到后面的目标窗口，说明输入区域生效且完成提交；
- 宠物区域内的点击落到 overlay；
- 展开状态点击 TabBar 收起箭头后正确收起，说明嵌入子控件也包含在输入区域中，且本地坐标命中正确。

### 5.2 子控件本地坐标

```text
TAB_SCREEN QRect(0, 0, 1440, 900)
TAB_GEO    QRect(1416, 341, 24, 48)
EXPANDED   QRect(1304, 341, 136, 285)
ARROW      QRect(0, 0, 16, 285)

HUD_GEO  QRect(24, 24, 216, 137)
DIAL_GEO QRect(1200, 660, 200, 200)
CTRL_GEO QRect(540, 752, 359, 124)
```

全部为 overlay 本地坐标，不再使用屏幕全局坐标。

### 5.3 自动化检查

```text
QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests -q
Ran 7 tests
OK

uv run ruff check .
All checks passed!

uv run ruff format --check .
274 files already formatted

uv run python tools/params_doc.py --check
ai-docs/PARAMS.md 是最新的
```

完整应用在 Wayland 下启动 12 秒，无 stderr 异常，随后由测试超时结束。

---

## 6. 仍未完成（不属于本次前置条件）

- KWin 几何桥接：overlay 目前仍依赖 KWin 的默认放置，尚未由脚本设置 `frameGeometry`；
- `keepAbove`、`skipTaskbar` 的 KWin 桥接；
- KWin 全局光标位置服务；
- 全局热键的 KWin 脚本注册；
- 物品拖拽在 Wayland 下的全局光标来源、冻结/放置模式的完整回归；
- Linux 打包与 CI。

在 KWin 桥接完成前，多屏全局定位、置顶和全局光标仍不能视为可用。
