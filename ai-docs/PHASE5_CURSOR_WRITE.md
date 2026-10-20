# Phase 5：Wayland/KWin 光标写入

- 日期：2026-10-20
- 环境：KDE Plasma 6.8 / KWin 6.8 / Qt 6.12.0 / PySide6 6.12.0
- 测试输出：HDMI-A-1 `1707x1067`，逻辑坐标 `0,900`；eDP-1 `1440x900`
- 结论：**已实现 best-effort 光标写入**。能移动光标、按住期间持续重定位、显示应用级忙碌样式；**不是系统级光标锁定**，指针一旦离开目标输出就会失去焦点。

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
  - `on_release()`
- 默认仍使用 Win32 的 `ClipCursor` / `SetCursorPos` / 系统忙光标；
- Wayland 传入 `clip=lambda: False`，状态机自动从“先尝试约束”退化为“逐 tick 重新定位”；
- `release()` 负责恢复光标并回调 `on_release()`；旧句柄被新劫持替换时会先释放，避免忙碌光标栈泄漏。

### 2.2 临时捕获面

`slugcatpet/window.py`：

- 新增 `CURSOR_CAPTURE_TITLE = "SlugcatPet Cursor Capture"`；
- `_show_cursor_capture()`：
  - 创建/复用 `Qt.Tool + FramelessWindowHint + WindowStaysOnTopHint`；
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
- 34 个测试通过；
- 新增 `tests/test_cursor_write.py`：
  - 自定义驱动替代 `ClipCursor`；
  - 释放回调与忙碌光标恢复；
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

### 3.3 复现命令

```bash
SLUGCATPET_HOME=/tmp/opencode/phase3-home \
XDG_CONFIG_HOME=/tmp/opencode/phase4-config \
uv run python /tmp/opencode/test_pet_cursor.py
```

该脚本只用于本地验收，不属于仓库测试。

---

## 4. 限制

1. **不是真正的锁光标**：Qt/PySide6 没有暴露 `zwp_pointer_constraints_v1`，只能 40 Hz 重定位。
2. **只在目标输出内有效**：捕获面覆盖目标输出；指针移到 eDP-1 等其他输出后，指针焦点离开捕获面，后续 `QCursor.setPos()` 无法把它拉回。
3. **依赖临时捕获面**：如果 KWin 脚本没有把捕获面设为 `keepAbove`，或捕获面创建失败，写入会失效。当前脚本已处理 `SlugcatPet Cursor Capture`。
4. **需要 Qt 6.12+ 和合成器支持**：Qt 6.11 及以下、没有 `wp_pointer_warp_v1` 的合成器会关闭设置项。
5. **忙碌样式不是系统级替换**：只在指针位于本应用捕获面时显示；离开应用表面后恢复系统光标。
6. **捕获期间拦截点击**：这是抢光标的预期行为；释放后捕获面隐藏，点击穿透恢复。
7. **KWin 脚本安装尚未完成**：目前仍由应用运行时加载；Phase 5 的安装/启用流程完成后，才能保证登录后自动可用。
8. **全屏隐藏时**：主窗口隐藏会一并隐藏捕获面，避免全屏程序被透明输入面挡住。

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
