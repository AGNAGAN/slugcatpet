# Phase 5：Wayland/KWin 光标写入

- 日期：2026-10-20；多输出逃逸补充于 2026-10-21
- 环境：KDE Plasma 6.8 / KWin 6.8 / Qt 6.12.0 / PySide6 6.12.0
- 测试输出：HDMI-A-1 `1707x1067`，逻辑坐标 `0,900`；eDP-1 `1440x900`
- 结论：**已实现 best-effort 光标写入**。能移动光标、按住期间持续重定位、显示应用级忙碌样式；左/右键单击会解除劫持，且不改变原有键盘焦点。**不是系统级光标锁定**：指针持续移动到其他输出时会通过捕获面 `leaveEvent` 或 KWin 光标位置检查结束劫持，并留在新输出。

---

## 1. 调查结论

### 1.1 KWin 脚本不能写光标

在 KWin 6.8 的脚本 API 中直接赋值：

```js
workspace.cursorPos = { x: 100, y: 100 };
```

会报：

```text
TypeError: Cannot assign to read-only property "cursorPos"
```

因此不能通过现有 KWin DBus 脚本实现光标写入。脚本仍只负责读取 `workspace.cursorPos` 并推送 `CursorMoved`。

### 1.2 Qt 6.12 提供 pointer-warp

KWin 6.8 在测试会话中注册了：

```text
wp_pointer_warp_v1 version 1
```

Qt 6.12 的 Wayland 客户端插件在 `QWaylandCursor::setPos()` 中实现了该协议。调用链要求：

1. 当前客户端至少有一个 seat 的 `pointer()->focusSurface()`；
2. 传入坐标落在这个焦点表面的 `windowFrameGeometry()` 内；
3. 合成器接受 `wp_pointer_warp_v1` 请求。

满足后，`QCursor.setPos()` 可以移动全局指针。普通 Qt 窗口在以下情况下可用：窗口新显示、指针已经在窗口输入区域上、或窗口本身拥有指针焦点。

### 1.3 只扩大已有 overlay 的输入区域不够

实测把主 overlay 的 `QWindow.setMask()` 从猫身区域扩大到整窗后：

- `WAYLAND_DEBUG=1` 能看到 `wl_surface.set_input_region` 和后续 `commit`；
- 但 KWin 不会因为输入区域变化而立即把指针焦点转给该表面；
- 光标静止时没有 `enter`，`QCursor.setPos()` 仍然不生效。

这是本次实现最关键的限制：**动态改大 mask 不能“抢回”指针焦点**。

### 1.4 临时全屏捕获面可以取得焦点

新映射一个全屏、透明、无边框的 `Qt.Tool` 表面后，即使指针在桌面空白处，KWin 也会把指针焦点交给这个新表面。随后：

```python
QCursor.setPos(...)
```

可以移动指针。捕获面消失后，焦点自然回到主 overlay 或桌面上。

因此最终方案是：

- **常驻主表面仍然只有一个**，负责绘制、猫、面板和动态输入区域；
- 抢光标期间额外显示一个**临时全屏输入捕获面**，只负责取得指针焦点和承接输入，不参与绘制；
- 捕获面在劫持结束时立即隐藏。

---

## 2. 实现

### 2.1 `CursorHijack` 可插拔驱动

`slugcatpet/platform/cursorfx.py`：

- 构造函数新增关键字参数：
  - `clip(x, y) -> bool`
  - `unclip()`
  - `setpos(x, y)`
  - `busy_cursor()`
  - `restore_cursor()`
  - `button_down() -> bool`（Windows 用于轮询左/右键；Wayland 由捕获面事件处理）
  - `on_release()`
- 默认仍使用 Win32 的 `ClipCursor` / `SetCursorPos` / 系统忙光标；
- Wayland 传入 `clip=lambda: False`，状态机自动从“先尝试约束”退化为“逐 tick 重新定位”；
- `release()` 负责恢复光标并回调 `on_release()`；旧句柄被新劫持替换时会先释放，避免忙碌光标栈泄漏。

### 2.2 临时捕获面

`slugcatpet/window.py`：

- 新增 `CURSOR_CAPTURE_TITLE = "SlugcatPet Cursor Capture"`；
- `_show_cursor_capture()`：
  - 创建/复用 `CursorCaptureWindow`（`Qt.Tool + FramelessWindowHint + WindowStaysOnTopHint`）；
  - `WA_TranslucentBackground`、`WA_ShowWithoutActivating`；
  - 放到目标输出的 overlay 几何；
  - 显示后把输入区域设为整个表面，确保指针落在捕获面内；
- `_hide_cursor_capture()`：释放时隐藏，不销毁，便于下次复用；
- `hideEvent()` 和 `shutdown()` 会一并隐藏/销毁捕获面；
- 切换输出时，如果捕获面正在显示，会重新定位。

`slugcatpet/platform/wayland/kwin_script/contents/code/main.js`：

- 新增 `CAPTURE_CAPTION`；
- `applyCapture(w)` 对捕获面设置 `keepAbove`、`skipTaskbar`、`skipSwitcher`，并固定到 overlay 几何；
- `isOwnWindow()` 排除捕获面，避免它进入挡雨窗口快照。

### 2.3 坐标换算

内部 `CursorHijack` 仍使用“overlay 物理坐标”：

```text
global_logical = internal_physical / devicePixelRatio
```

Qt 的 Wayland `QCursor.setPos()` 有一个容易踩坑的行为：它把传入点当作全局坐标，再减去**当前焦点窗口**的 `windowFrameGeometry().topLeft()`。

- 主 overlay 由 KWin 脚本移动，Qt 侧几何原点通常是 `(0,0)`，而 KWin 实际放在 `(0,900)`；
- 临时捕获面的 Qt 几何原点却可能是 `(0,900)`。

所以写入前统一做：

```text
target_local = global_logical - capture_global_origin
qt_input = target_local + capture_window.frameGeometry().topLeft()
QCursor.setPos(qt_input)
```

并 clamp 到捕获面尺寸。这样无论 Qt 是否知道真实全局位置，都能落到正确的表面本地坐标。

### 2.4 忙碌样式

Wayland 不再强制关闭 `cursor_shape`：

- 劫持开始：`QApplication.setOverrideCursor(Qt.WaitCursor)`；
- 劫持结束：`QApplication.restoreOverrideCursor()`；
- 只影响本应用表面，不替换系统全局光标；指针在捕获面内时可看到忙碌样式。

### 2.5 能力开关

- `DesktopBackend.supports_cursor_write`；Win32 为 `True`，Wayland 由 KWin 桥判断。
- `WaylandKWinBackend.supports_cursor_write` 要求：
  - DBus 服务已注册；
  - KWin 脚本已加载；
  - Qt 版本 `>= 6.12`（`_qt_supports_pointer_warp()`）。
- `PetWindow.cursor_hijack_available` / `cursor_shape_available` 使用该能力。
- 设置页只在能力可用时启用两个勾选框；不可用时灰显并显示更新后的说明。
- Windows 的 `ClipCursor` 优先路径不变。

### 2.6 焦点保持与点击解除

Wayland/xdg-shell 没有“只接收指针、不接受键盘焦点”的顶层窗口标志。临时捕获面映射时，KWin 仍会把它设为活动窗口；仅设置 `WA_ShowWithoutActivating` 不够。因此分两层处理：

1. **捕获面吞掉解除点击**：`window.py` 新增 `CursorCaptureWindow`，在 `mousePressEvent()` 中拦截左键/右键，发出 `clicked` 后 `accept()`，不把事件传给下层窗口；`clicked` 连接到 `stop_cursor_hijack()`。释放流程会恢复忙碌光标、隐藏捕获面并清空 `cursor_hijack`。
2. **KWin 脚本恢复原焦点**：脚本维护 `lastActive` 与 `lastExternalActive`。捕获面激活时把 `workspace.activeWindow` 设回激活前的窗口；overlay 首次映射时也把焦点还给原来的外部窗口。overlay 映射后 1 秒内视为“映射抢焦点”，超过宽限期后的激活（例如用户打开 ControlHud）则按正常焦点处理，不会被脚本抢走。

Windows 路径没有捕获面，`CursorHijack.update()` 用 `GetAsyncKeyState()` 轮询左/右键；如果劫持开始时触发点击还没有松开，会先等按键释放，避免刚抢到就立即解除。

3. **多输出逃逸**：捕获面只覆盖目标输出。`CursorCaptureWindow.leaveEvent()` 连接到 `stop_cursor_hijack()`；同时 `CursorHijack` 接受 `cursor_inside` 回调，KWin 报告光标落在目标输出外时结束劫持。`_inside_seen` 记录是否已经进入过目标输出：如果一开始在别的输出，给捕获面约 0.5 秒取得指针焦点，仍失败则放弃；已经进入后一旦离开就立即释放，避免 40 Hz 重定位把用户拉回。

残余限制：KWin 仍可能先短暂激活捕获面，再由脚本在同一个激活信号中恢复焦点；最终活动窗口不变，但理论上存在极短的焦点过渡窗口。短促的跨输出移动可能被 40 Hz 重定位抵消；持续移动可以逃逸，因此仍不是内核级 pointer lock。

---

## 3. 验证

### 3.1 自动检查

```text
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
```

结果：

- ruff / format 通过；
- 46 个测试通过；
- 新增 `tests/test_cursor_write.py`：
  - 自定义驱动替代 `ClipCursor`；
  - 释放回调与忙碌光标恢复；
  - 左/右键按下解除劫持，且触发劫持的那次按键不会立即自解除；
  - 光标离开目标输出时在 `setpos` 前释放劫持；
  - 起始在目标输出外时保留约 0.5 秒捕获宽限，仍失败则释放；
  - 物理坐标 → 目标表面坐标；
  - Qt frame 原点补偿；
  - Qt 6.11/6.12 能力门控；
  - `PetWindow.cursor_hijack_available` 跟随后端 `supports_cursor_write`。

### 3.2 KWin 实机验证

测试方式：

1. 用临时全屏程序把指针放到 HDMI-A-1 的桌面空白处 `(700,1500)`；
2. 启动只包含 `PetWindow` 的测试实例；
3. 调用 `start_cursor_hold()`，初始目标为当前光标；
4. 900 ms 后把 hold 目标改到 overlay 内 `(569,1256)`；
5. 用独立的 KWin 探测脚本读取 `workspace.cursorPos`。

结果：

```text
START  cursor (700, 1500) capture False busy False
HOLD1  cursor (700, 1500) capture True  busy True
HOLD2  cursor (569, 1256) capture True  busy True
STOP   cursor (569, 1256) capture False busy False
KWin probe: CURSORPROBE2 moved 569 1256
```

说明：

- 从桌面空白处启动也能取得焦点；
- 捕获面显示后 `QCursor.setPos()` 成功移动真实光标；
- hold 的每个 tick 持续重定位；
- 释放后捕获面隐藏、忙碌样式恢复。

截图验证没有完成：当前会话的 `grim` 报 `compositor doesn't support the screen capture protocol`。忙碌样式通过 `QApplication.overrideCursor()` 状态确认，未做像素级截图验收。

### 3.3 焦点保持与真实点击验收

用 `evdev`/`uinput` 模拟真实指针移动和按键；用独立 KWin 脚本记录活动窗口。先把 Alacritty 设为活动窗口，再启动测试实例：

```text
FOCUSPROBE activated SlugcatPet Overlay
FOCUSPROBE activated OC | 仓库分析
slugcatpet restored focus overlay OC | 仓库分析
FOCUSPROBE activated SlugcatPet Cursor Capture
FOCUSPROBE activated OC | 仓库分析
slugcatpet restored focus capture OC | 仓库分析
```

说明：

- overlay 首次映射抢走的焦点被脚本还给原窗口；
- 捕获面激活后，键盘焦点同样恢复为 `OC | 仓库分析`；
- 整个 hold 期间，最终活动窗口没有停留在 `SlugcatPet Overlay` 或捕获面。

真实左键验收：

```text
T2500 capture True  busy True  hijack True
T4000 capture True  busy True  hijack True
T6000 capture False busy False hijack False
wl_pointer.button(... 272, 1)  # BTN_LEFT
wl_pointer.leave(capture_surface)
```

真实右键验收：

```text
T4000 capture True
T6000 capture False busy False hijack False
wl_pointer.button(... 273, 1)  # BTN_RIGHT
wl_pointer.leave(capture_surface)
```

两次都在按键按下后立即结束劫持、隐藏捕获面并恢复忙碌光标；这次点击不会继续传给下面的窗口。

同轮验收中，hold 目标仍能把光标移动到 `(569,1256)`，第二次 hold 移动到 `(427,1434)`；说明恢复键盘焦点不会破坏指针焦点和 `QCursor.setPos()`。

### 3.4 多输出逃逸验收

先把指针停在 HDMI-A-1 的 `(1558,1966)`，启动 hold 到 `(569,1434)`，然后用 uinput 持续向上移动。捕获面收到 `leaveEvent`，劫持立即结束，指针留在 eDP-1：

```text
START (1558, 1966)
created True
CURSOR (569, 1434)
CAP_MOVE ... (569, 314) / (569, 74)
CAP_LEAVE
CURSOR (569, 354)
DONE (569, 354) hijack False
```

说明：

- 捕获面离开目标输出时，`pointer_left` 立即结束劫持；
- 释放后指针停在 eDP-1 `(569,354)`，没有被 40 Hz `setpos` 拉回；
- 短促移动可能被重定位抵消；需要持续移动才能跨输出。这是 best-effort 行为，不是 pointer lock。

### 3.5 复现命令

```bash
SLUGCATPET_HOME=/tmp/opencode/phase3-home \
XDG_CONFIG_HOME=/tmp/opencode/phase4-config \
uv run python /tmp/opencode/test_pet_cursor.py

SLUGCATPET_HOME=/tmp/opencode/phase3-home \
XDG_CONFIG_HOME=/tmp/opencode/phase4-config \
uv run python /tmp/opencode/test_cursor_focus_click.py

# 真实按键验收（另开终端，需可写 /dev/uinput）
python /tmp/opencode/mouse_click.py
```

这些脚本只用于本地验收，不属于仓库测试。

---

## 4. 限制

1. **不是真正的锁光标**：Qt/PySide6 没有暴露 `zwp_pointer_constraints_v1`，只能 40 Hz 重定位。
2. **只在目标输出内有效**：捕获面覆盖目标输出；指针持续移到 eDP-1 等其他输出后，捕获面 `leaveEvent` 或光标位置检查会结束劫持，光标留在新输出。短促移动仍可能被 40 Hz 重定位抵消，不能当作系统级 pointer lock。
3. **依赖临时捕获面**：如果 KWin 脚本没有把捕获面设为 `keepAbove`，或捕获面创建失败，写入会失效。当前脚本已处理 `SlugcatPet Cursor Capture`。
4. **需要 Qt 6.12+ 和合成器支持**：Qt 6.11 及以下、没有 `wp_pointer_warp_v1` 的合成器会关闭设置项。
5. **忙碌样式不是系统级替换**：只在指针位于本应用捕获面时显示；离开应用表面后恢复系统光标。
6. **解除点击会被吞掉**：捕获期间左/右键只用于解除劫持，不会继续传给下层窗口；解除后捕获面隐藏，点击穿透恢复。
7. **焦点恢复有极短过渡**：KWin 仍会短暂把捕获面设为活动窗口，脚本随后在同一个激活信号内恢复原焦点；最终活动窗口不变。
8. **KWin 脚本安装已完成，但登录时可能先用旧几何**：设置页可显式安装到 `~/.local/share/kwin/scripts/slugcatpet` 并写 `kwinrc`；登录时 KWin 会先按上次保存的几何加载持久脚本，应用启动后立即用当前输出重新加载运行时脚本。详见 `PHASE5_PACKAGING.md`。
9. **全屏隐藏时**：主窗口隐藏会一并隐藏捕获面，避免全屏程序被透明输入面挡住。

---

## 5. 涉及文件

- `slugcatpet/platform/cursorfx.py`
- `slugcatpet/world/effects.py`
- `slugcatpet/window.py`
- `slugcatpet/platform/backend.py`
- `slugcatpet/platform/wayland/kwin_bridge.py`
- `slugcatpet/platform/wayland/kwin_script/contents/code/main.js`
- `slugcatpet/ui/panels/settings.py`
- `slugcatpet/i18n.py`
- `tests/test_cursor_write.py`
- `tests/test_wayland_backend.py`
- `ai-docs/REMAINING_WORK.md`
- `ai-docs/NATIVE_WAYLAND_PORT_PLAN.md`
