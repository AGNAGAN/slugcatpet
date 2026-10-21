# 原生 Wayland 移植方案（KDE Plasma / KWin 6.8）

- 日期：2026-10-21
- 依据：`ai-docs/PORTABILITY_ANALYSIS.md` 的路线 B
- 决策：**采用原生 Wayland 客户端，不使用 XWayland**
- 目标环境：当前机器上的 KDE Plasma 6.8 / KWin 6.8 / Qt 6.12 / PySide6 6.12
- 性质：**方案与实施计划**；实际结果见各阶段 `PHASE*_RESULTS.md`
- Phase 0 状态：**已完成，Go（有条件）**；实测记录见 `ai-docs/PHASE0_RESULTS.md`
- Phase 1 状态：**已完成**；主表面、KWin 几何/置顶、输入区域和光标桥实测见 `ai-docs/PHASE1_RESULTS.md`
- Phase 2 状态：**已完成（第一版）**；UI 嵌入、局部坐标、卡片/菜单/提示与坐标迁移见 `ai-docs/PHASE2_RESULTS.md`
- Phase 3 状态：**已完成**；全屏、窗口快照、全局热键、冲突提示和设置页状态已实测，持久安装/启用在 Phase 5 完成；见 `ai-docs/PHASE3_RESULTS.md`
- Phase 4 状态：**已完成**；XDG 自启、输出选择、光标只读/写入能力、托盘锚点与 transient 设置/音乐窗已实测，desktop/图标在 Phase 5 完成；见 `ai-docs/PHASE4_RESULTS.md`
- Phase 5 状态：**接近完成**；Wayland/KWin 光标写入、焦点保持、左/右键解除、多输出逃逸、Linux 打包、KWin 持久安装/启用、desktop/图标、Linux/Windows CI 和 README 已完成；剩余真实猫行为、Rain World 全屏和注销登录验收；见 `ai-docs/PHASE5_CURSOR_WRITE.md`、`ai-docs/PHASE5_PACKAGING.md`
- 剩余工作清单：`ai-docs/REMAINING_WORK.md`

---

## 0. 结论先行

原生 Wayland 可以做，但**不是“加几个 `sys.platform` 分支”就能完成**。它需要同时解决四个问题：

1. **窗口定位**：Wayland 不允许普通客户端把顶层窗口放到任意屏幕坐标。
2. **置顶/全屏覆盖**：Wayland 没有通用的 always-on-top 协议。
3. **全局光标**：Wayland 不向普通客户端暴露全局指针位置。
4. **输入穿透**：全屏透明窗口必须只让猫身和 UI 区域接收鼠标，其余区域穿透到桌面。

本方案的选择是：

| 问题 | 方案 |
| --- | --- |
| 主表面定位、置顶、全屏尺寸 | **KWin 脚本**设置 `frameGeometry`、`keepAbove`、`skipTaskbar` |
| 输入穿透 | **单个主表面 + `QWindow.setMask()` 动态输入区域**；光标劫持期间临时显示全屏捕获面 |
| 全局光标 | 读取：**KWin 脚本 `workspace.cursorPos` → DBus → Python**；写入：Qt 6.12 `QCursor.setPos()` + `wp_pointer_warp_v1` |
| 全部浮动 UI | **嵌入主表面**，不再使用多个可自由定位的 `Qt.Tool` 顶层窗口 |
| 全屏检测、挡雨窗口 | KWin 脚本推送活动窗口和窗口矩形快照 |
| 全局热键 | KWin `registerShortcut`；不可用时降级或后续接 GlobalShortcuts portal |
| 开机自启 | XDG autostart `.desktop` |
| 设置/音乐窗口 | 保留普通 `xdg_toplevel`，由合成器放置，不再自己 `move()` |

**适用边界：**

- 本方案完整功能面向 **KDE Plasma 6 + KWin**，因为定位、置顶、光标、窗口枚举都依赖 KWin 脚本。
- 在 GNOME、Sway、Hyprland 等合成器上，只能提供**降级模式**：没有全局光标跟随、没有可靠的置顶/全屏覆盖，窗口位置由合成器决定。
- 如果未来要求“所有 Wayland 合成器一致可用”，应重新评估 **layer-shell + PyQt6/系统 Qt** 或自定义 QPA 插件；这不是本计划第一版的目标。

---

## 1. 为什么不直接用 layer-shell

当前系统其实具备 layer-shell 条件：

- KWin 注册了 `zwlr_layer_shell_v1`，版本 5。
- 系统安装了 `layer-shell-qt 6.8.0` 和 `/usr/lib/qt6/plugins/wayland-shell-integration/liblayer-shell.so`。
- 系统 Qt 6.12 可以加载该插件。

但项目使用的是 **PySide6 wheel 自带的 Qt**：

- PySide6 6.12 的 `wayland-shell-integration` 目录只有 `xdg-shell`、`ivi-shell`、`qt-shell`、`wl-shell`、`fullscreen-shell`，**没有 `layer-shell`**。
- 设置 `QT_WAYLAND_SHELL_INTEGRATION=layer-shell` 会直接失败：
  `No shell integration named "layer-shell" found`。
- 系统插件链接的是系统 Qt 库；强行把系统插件塞进 PySide6 进程会引入两套 Qt，ABI/私有 API 风险很高。
- 迁移到系统 PyQt6 可以使用 layer-shell，但那是**绑定层迁移**，会波及大量 UI 文件，不应和 Wayland 移植同时做。

因此第一版**不用 layer-shell**，改用 KWin 脚本补齐 Wayland 缺失的窗口管理能力。这样：

- 仍然是原生 Wayland 客户端；
- 不需要迁移 PySide6；
- 不需要自己写 QPA 插件；
- 代价是 KDE 专用。

如果以后必须支持 GNOME/Sway，建议单独开分支：系统 PyQt6 + LayerShellQt，或写一个只负责 overlay 的小型 C++/Qt 辅助进程。

---

## 2. 目标架构

```text
┌──────────────────────────────────────────────────────────────┐
│ KWin 6.8                                                      │
│  - frameGeometry = 目标输出几何                              │
│  - keepAbove / skipTaskbar / skipSwitcher                     │
│  - workspace.cursorPos → DBus                                 │
│  - 活动窗口 fullScreen / 窗口矩形快照 → DBus                   │
│  - registerShortcut → DBus                                    │
└──────────────────────────────┬───────────────────────────────┘
                               │ session DBus
┌──────────────────────────────▼───────────────────────────────┐
│ Python / PySide6                                              │
│                                                               │
│  OverlayWindow（唯一全屏顶层表面，Qt.Tool + Frameless）        │
│   ├─ 场景画布：paintEvent（现有物理/渲染代码不动）              │
│   ├─ TabBar（子控件）                                          │
│   ├─ HudPanel（子控件）                                        │
│   ├─ RainDial（子控件）                                        │
│   ├─ RainCard（子控件，替代 Qt.Popup）                         │
│   ├─ ControlHud（子控件，键盘焦点）                             │
│   └─ ConfirmDialog / 提示层（子控件或 transient QDialog）       │
│                                                               │
│  SettingsWindow / MusicPanel / SetupPanel                     │
│   └─ 普通 xdg_toplevel，由 KWin 放置，不再自己 move()          │
│                                                               │
│  PlatformBackend                                               │
│   ├─ WaylandKWinBackend                                        │
│   ├─ Win32Backend（包装现有代码，Windows 路径不变）             │
│   └─ NullBackend（非 KDE Wayland 降级）                        │
└───────────────────────────────────────────────────────────────┘
```

核心原则：

1. **主表面只有一个**，所有需要精确位置的东西都画进这个表面。
2. **输入区域由主表面统一管理**，不再每个面板单独切换穿透。唯一的例外是光标劫持期间的临时全屏捕获面：它不绘制、只取得指针焦点，劫持结束立即隐藏；详见 `PHASE5_CURSOR_WRITE.md`。
3. **物理、行为、渲染核心不改**；改的是窗口、输入、平台适配和面板父子关系。
4. **KWin 不可用时显式降级**，不能静默假装“已置顶/已跟随光标”。

---

## 3. 分阶段实施计划

### Phase 0：可行性闸门（2–3 人日）

先做最小验证，避免直接重构到一半才发现 KWin 路径不可行。

| 验证项 | 方法 | 通过标准 |
| --- | --- | --- |
| KWin 脚本能设置窗口几何 | 创建 `Qt.Tool` 测试窗，脚本用 `Object.assign({}, output.geometry)` 后赋给 `frameGeometry` | 应用侧 `QWidget.geometry()` 尺寸变为目标输出尺寸 |
| KWin 脚本能置顶 | 脚本设 `keepAbove = true`、`skipTaskbar = true` | 普通窗口不遮挡测试窗；任务栏不显示 |
| KWin → DBus 光标 | 脚本 `callDBus` 调用 Python `QtDBus` 服务 | Python 收到 `workspace.cursorPos` 坐标 |
| 输入区域 | `QWindow.setMask(QRegion)` 后 `requestUpdate()` 提交，用 `WAYLAND_DEBUG=1` 看协议 | 出现 `set_input_region` + commit；区域外不接收输入 |
| 子控件嵌入 | 把 `TabBar`/`HudPanel` 作为主窗子控件显示 | 绘制、点击、动画、拖动正常 |
| 键盘焦点 | `ControlHud` 子控件 `activateWindow()` | 能收到按键；失焦暂停逻辑可复用 |
| 全局热键 | KWin `registerShortcut` 在 `loadScript` 模式下注册 | 按键触发 Python DBus 回调；冲突时有日志 |
| 托盘 | `QSystemTrayIcon` 在 KDE 下显示/点击 | 能打开设置/音乐/退出 |
| DPR/坐标 | 1.5 和 2.0 缩放下比较 KWin 逻辑坐标与 Qt 坐标 | 光标、窗口矩形换算误差 ≤ 1 px |

**Go/No-Go：**

- 全部通过：进入 Phase 1。
- 只有“全局热键”失败：继续，热键降级或改 portal。
- 只有“KWin 脚本加载/几何”失败：停止原生路线，回到 XWayland 方案，不要把 UI 重构做完再回退。

> Phase 0 已完成，实测记录见 `ai-docs/PHASE0_RESULTS.md`。几何、置顶、DBus 光标、输入区域/穿透、子控件、键盘焦点、热键、托盘、DPR 和窗口快照均已验证；进入 Phase 1 前需落实“输入区域提交、子控件本地坐标、窗口级 DPR”三项条件。

---

### Phase 1：主表面与输入区域（4–6 人日）

目标：先让“全屏透明、可穿透、可点击猫”的底座跑起来，暂不迁移全部 UI。

#### 1.1 新增平台后端接口

新增 `slugcatpet/platform/backend.py`（或 `platform/desktop/base.py`）：

```python
class DesktopBackend(Protocol):
    name: str
    supports_geometry: bool
    supports_topmost: bool
    supports_cursor: bool
    supports_hotkeys: bool
    supports_fullscreen: bool
    supports_shelters: bool

    def attach_overlay(self, window): ...
    def set_input_region(self, window, region): ...
    def cursor_pos(self): ...  # 全局逻辑坐标或 None
    def overlay_origin(self): ...  # 主表面左上角逻辑坐标
    def set_overlay_geometry(self, rect): ...
    def foreground_fullscreen(self): ...  # bool | None
    def window_rects(self): ...  # overlay-local 逻辑矩形
    def set_autostart(self, on): ...
    def install_hotkeys(self, callbacks): ...
```

第一版只要求：

- `Win32Backend` 包装现有 Windows 实现；
- `WaylandKWinBackend` 实现 KWin 路径；
- `NullBackend` 在非 KDE Wayland 下返回不可用。

Windows 代码先保持原样，避免回归。

#### 1.2 改造 `PetWindow` 主表面

文件：`slugcatpet/window.py`

- 保留 `FramelessWindowHint | Tool`；移除对 `WindowStaysOnTopHint` 的依赖（Wayland 下不可靠，置顶交给 KWin）。
- 初始化时：
  - 使用 `QGuiApplication.primaryScreen().geometry()` 作为目标表面；
  - 在 `show()` 前对目标 `QScreen` 调用 `setScreen()`，让 Qt 采用该输出的 DPR；不要只靠 KWin 改 `frameGeometry` 把窗口移到另一块屏，否则窗口 DPR 可能停留在旧屏（Phase 0 实测 HDMI 1.5 → eDP 仍为 1.5）；
  - `resize()` 到目标尺寸；
  - **不再 `move(area.x(), area.y())`**；
  - 由 KWin 脚本设置实际 `frameGeometry`。
- 第一版以整块输出为表面；当前环境 `availableGeometry == geometry`，所以猫的地板线与现有行为一致。如果用户的任务栏不是自动隐藏，Phase 4 需要把工作区高度/面板占用纳入 `compute_geometry()`，不要直接把整屏高度当地板线。
- `apply_workspace(area, geo)`：
  - 保留 `_WL/_HL/_ground_inset` 计算；
  - 保留 `resize()`；
  - 在 Wayland 分支去掉 `move()`；
  - `_area`/`_geo` 以 `QScreen` 逻辑几何为准。
- `_watch_screen()`：主屏变化时重新计算 canvas，不尝试移动顶层窗口；如果目标输出变化，先 `setScreen()` 或重建表面，再让 KWin 重设 `frameGeometry`，避免 DPR 与输出不一致。
- 调试模式仍可保留可交互行为，但不能依赖全局坐标。

#### 1.3 用输入区域替换 `_update_passthrough()`

文件：`slugcatpet/window.py`、`slugcatpet/control/mouse.py`

当前 `control/mouse.py::set_passthrough()` 在非 Windows 直接返回，这是 Linux 挡住桌面的根因。新实现：

```python
def _input_region(self) -> QRegion:
    # 拖拽/放置/控制/菜单期间，整窗接收输入，避免快速移动丢事件
    if self._drag or self._place_mode or self._control_hud or self._menu_open:
        return QRegion(self.rect())

    region = QRegion()
    for pet in self._interactive_pets():
        region = region.united(self._pet_hit_region(pet))
    for item in self._interactive_items():
        region = region.united(self._item_hit_region(item))
    for w in self._overlay_panels():
        if w is not None and w.isVisible():
            region = region.united(QRegion(w.geometry()))
    return region
```

关键细节：

- `QWindow.setMask(QRegion)` 在 Qt Wayland 下映射到 `wl_surface.set_input_region`，**不是裁剪绘制**；本机 `WAYLAND_DEBUG` 已验证。
- **setMask 后必须提交表面**：Qt 6.12 只调用 `windowHandle().setMask()` 时，可能只发送 `set_input_region` 而不立即 `wl_surface.commit()`；实测未提交时输入区域不生效，整窗仍接收输入。统一在 mask 更新后调用 `windowHandle().requestUpdate()`（必要时再 `update()`），并在窗口尺寸/输出变化后重算区域并重新提交。
- **不要传空 `QRegion`**：Wayland 空区域等价于“整个表面接收输入”。没有可交互区域时，使用表面外的一个 1×1 区域：
  ```python
  QRegion(self.width(), self.height(), 1, 1)
  ```
  按协议合成器会忽略表面外区域；Phase 0 必须用手工点击确认实际穿透效果。
- 不要依赖运行时反复切换 `Qt.WindowTransparentForInput`；Qt 6.12 下该 flag 的动态更新行为不够稳定。用 mask 方案即可。
- 输入区域更新要节流：
  - 每 tick 或每 2 tick 更新一次；
  - 缓存上一次 `QRegion`，只有变化超过 1 px 才调用 `setMask`；
  - 拖拽/放置/控制时直接整窗，松手后恢复。
- `QWidget` 子控件的 `geometry()` 是主表面局部坐标，正好用于 `QRegion`。

`control/mouse.py` 不再负责 Win32 穿透；保留 `is_over()`、`hit_test()` 等纯几何函数，新增/转调后端 `set_input_region()`。

#### 1.4 光标输入

`window.cursor_logical()` 现在是：

```python
g = self.mapFromGlobal(QCursor.pos())
```

在原生 Wayland 下 `QCursor.pos()` 不可靠，改为：

```python
pos = self.backend.cursor_pos()  # 全局逻辑坐标或 None
if pos is None:
    return None
ox, oy = self.backend.overlay_origin()
return self.to_logical(pos[0] - ox, pos[1] - oy)
```

- `backend.cursor_pos()` 由 KWin 脚本推送。
- 同时维护 `self._last_local_pointer`，在 `mouseMoveEvent`/`enterEvent` 更新；KWin 不可用时用它作为降级光标。
- 行为层要能接受 `None`：
  - 光标跟随、舔光标、扑咬、后空翻等依赖光标的动作，在 `cursor_available=False` 时跳过或改用最近位置；
  - 设置页显示“当前环境不支持全局光标”，不静默失败。

#### 1.5 Phase 1 退出标准

- 主表面覆盖目标屏幕，猫可见。
- 桌面空白区域点击穿透；猫身、物品、面板可点击。
- 输入区域更新后已提交表面（`WAYLAND_DEBUG` 可见 `set_input_region` 后的 `commit`），不是只改内存状态。
- 拖拽猫时输入区域足够大，不会因快速移动丢事件。
- 不启动 KWin 桥时，应用仍能运行，只是光标跟随降级。
- offscreen 行为测试不回归。

---

### Phase 2：UI 嵌入主表面（8–12 人日）

这是工作量最大的部分。当前大量 UI 是“独立顶层窗口 + `move()`”，Wayland 下必须改成“主表面子控件 + 局部坐标”。

#### 2.1 迁移矩阵

| 组件 | 当前形态 | 目标形态 | 主要改动 |
| --- | --- | --- | --- |
| `PetWindow` 场景 | 全屏 `Qt.Tool` 顶层 | 唯一全屏 overlay | 保留画布，增加子控件层 |
| `TabBar` | `Qt.Tool` 顶层，`setGeometry()` 到屏幕右侧 | overlay 子控件 | 去掉顶层 flags；`screen` 改 overlay rect；拖动用局部坐标 |
| `HudPanel` | `Qt.Tool` 顶层，可拖动 | overlay 子控件 | `_place`/`_move_to` 用局部坐标；拖动用 `ev.position()` |
| `ControlHud` | `Qt.Tool` 顶层，键盘输入窗 | overlay 子控件 | 去掉顶层 flags；`activateWindow()` 改为 `window().activateWindow()`；焦点/失焦逻辑保留 |
| `RainDial` | `Qt.Tool` 顶层，可拖动 | overlay 子控件 | 局部坐标；`_tip` 改成子 label；拖动用局部 delta |
| `RainCard` | `Qt.Popup` 顶层 | overlay 子卡片 | 去掉 `Qt.Popup`；由 overlay 事件过滤器处理“点外面关闭”和 Esc |
| `ConfirmDialog` | `QDialog` + 自定义居中/拖动 | overlay 内模态层，或 transient `QDialog` | 第一版建议做成 overlay 内卡片；不要 `place_center()`/`move()` |
| `SettingsWindow` | 普通 `Qt.Window` | 保持普通 `xdg_toplevel` | 去掉自定义 `move()`；由 KWin 放置 |
| `MusicPanel` | 普通 `Qt.Window` | 保持普通 `xdg_toplevel` | 同上 |
| `SetupPanel` | 首次启动窗口 | 普通 `QDialog` | 不要按屏幕坐标居中；用 transient parent |
| `CatMenu` | `QMenu` | 以 overlay 为 parent 的 popup | `exec(globalPos)` 改为 `popup(overlay.mapToGlobal(localPos))`；验证 Wayland popup 定位 |
| 工具提示 | 顶层 `QLabel` + `mapToGlobal` | 子 label 或 `QToolTip` | 去掉全局定位；限制在 overlay 内 |
| `hudrow` 右键/拖动 | 全局坐标 | 局部坐标 | `globalPosition()` 改 `position()` + `mapTo` |
| `appearance` / `scenemusic` 弹出层 | `mapToGlobal` | overlay 子控件 | 局部锚点 |
| TabBar toast | 顶层 label | 子 label | 局部定位 |
| 雨循环卡片（托盘） | 依赖 `tray.geometry()`/全局坐标 | overlay 内固定锚点或光标附近 | 托盘没有几何时用右下角/标签栏锚点 |

#### 2.2 统一坐标规则

嵌入后只允许三种坐标：

1. **overlay 局部逻辑坐标**：所有子控件、命中测试、拖动、卡片锚点。
2. **全局逻辑坐标**：只用于 KWin 光标、托盘/菜单等必须与合成器交互的地方。
3. **物理像素**：仅 Windows 平台内部使用；Wayland 路径不再混用 `dpr`。

需要清理的典型代码：

- `window.py`：`mapFromGlobal(QCursor.pos())`、`self.x()/self.y()` 用于挡雨换算、`open_cat_menu(global_pos)`、`mousePressEvent` 的 `globalPosition()`。
- `tabbar.py`：`ev.globalPosition().y() - self.y()`、`setGeometry(self._edge_x, ...)`。
- `hud.py`：`ev.globalPosition() - frameGeometry().topLeft()`。
- `controlhud.py`：同上。
- `dial.py`：`ev.globalPosition()` 拖动、`mapToGlobal` 提示。
- `tips.py`：`mapToGlobal`。
- `hudrow.py`：右键菜单的 `globalPosition()`。
- `appearance.py`、`scenemusic.py`：`mapToGlobal` 锚点。
- `dialogs.py`：`place_center()` / 自定义拖动。

建议先加一个 `OverlayHost` 辅助类，统一提供：

```python
class OverlayHost:
    def local_rect(self): ...
    def clamp_local(self, rect): ...
    def map_to_overlay(self, child, point): ...
    def show_card(self, card, anchor_rect): ...
    def close_on_outside(self, card): ...
```

避免每个面板各写一套。

#### 2.3 位置持久化

现有存档里 `hud_x/hud_y`、`tab_y`、`dial_x/dial_y` 很可能是**全局屏幕坐标**。迁移时：

- 首次在 Wayland 启动时，读取旧值；
- 减去 overlay 原点，clamp 到 overlay 范围；
- 写回为新局部坐标；
- 增加一个 `ui_coord_space: "overlay"` 标记，避免重复迁移。

如果旧值明显越界，回退到默认位置。

#### 2.4 设置/音乐/首次启动

这些窗口不需要“贴在猫旁边”，保留普通顶层即可：

- `SettingsWindow`：普通 `Qt.Window`，由 KWin 居中/放置；不要调用 `move()`。
- `MusicPanel`：同上。
- `SetupPanel`：普通 `QDialog`，以 overlay 为 transient parent；让合成器决定位置。
- 这样既减少迁移量，也符合 Wayland 的窗口管理模型。

#### 2.5 Phase 2 退出标准

- 除 overlay、设置、音乐、首次启动外，不再有需要 `move()` 的 `Qt.Tool` 顶层。
- TabBar/HUD/控制条/雨表盘/雨卡片都能在 overlay 内显示、拖动、保存位置。
- 右键猫菜单、工具提示、确认框都能正常弹出和关闭。
- 控制模式能拿到键盘焦点，失焦暂停仍然有效。
- 窗口大小/屏幕变化后，所有面板仍在可见范围。

---

### Phase 3：KWin 桥（4–6 人日）

#### 3.1 Python 侧 DBus 服务

新增 `slugcatpet/platform/wayland/kwin_bridge.py`：

```python
class KWinBridge(QObject):
    cursor_moved = Signal(int, int)
    overlay_geometry_changed = Signal(int, int, int, int)
    fullscreen_changed = Signal(bool, int, int, int, int)
    window_list_changed = Signal(str)  # JSON
    hotkey_pressed = Signal(int)
```

- 用 `PySide6.QtDBus` 注册 session bus 服务：
  - service：`org.slugcatpet.Bridge`
  - path：`/Bridge`
  - interface：`org.slugcatpet.Bridge`
- 必须给 `QObject` 加：
  ```python
  Q_CLASSINFO("D-Bus Interface", "org.slugcatpet.Bridge")
  ```
  否则 QtDBus 会按 Python 类名生成接口，KWin 脚本调用会找不到方法。
- 槽函数参数用 `int`/`bool`/`str`，避免复杂类型。
- 服务注册失败时 `available=False`，应用进入降级模式。

DBus 方法建议：

| 方法 | 来源 | 参数 | 用途 |
| --- | --- | --- | --- |
| `CursorMoved` | KWin | `int x, int y` | 全局光标逻辑坐标 |
| `OverlayGeometryChanged` | KWin | `int x, int y, int w, int h` | 主表面实际几何 |
| `FullscreenChanged` | KWin | `bool full, int x, int y, int w, int h` | 活动窗口全屏状态 |
| `WindowListChanged` | KWin | `str json` | 挡雨窗口矩形快照 |
| `HotkeyPressed` | KWin | `int id` | 全局热键 |

#### 3.2 KWin 脚本

新增资源：

```text
slugcatpet/platform/wayland/kwin_script/
  metadata.json
  contents/code/main.js
```

脚本职责：

1. **找主表面**
   - 通过 `desktopFileName == "org.slugcatpet.SlugcatPet"` 或固定 caption 识别。
   - 应用启动时调用 `QGuiApplication.setDesktopFileName("org.slugcatpet.SlugcatPet")`。

2. **设置几何**
   - 目标输出：第一版用 `workspace.screens[0]`，与当前应用“只支持主屏”一致。
   - 使用 `target.geometry`；**不要用 `workspace.clientArea(option, output, desktop)`**：本机 KWin 6.8 实测该重载返回整个虚拟桌面，而不是单屏工作区。
   - `frameGeometry` 是 `QRectF`，直接赋 `output.geometry`（`QRect`）会报
     `Cannot assign KWin::Rect to KWin::RectF`。
   - 必须用普通对象中转：
     ```js
     var target = workspace.screens[0];
     var g = Object.assign({}, target.geometry);
     g.x = target.geometry.x; // 显式写出，避免只复制可枚举字段的坑
     g.y = target.geometry.y;
     g.width = target.geometry.width;
     g.height = target.geometry.height;
     w.frameGeometry = g;
     ```
   - 设置 `keepAbove = true`、`skipTaskbar = true`、`skipSwitcher = true`。
   - 在 `windowAdded`、`windowActivated`、输出变化时重新应用；不要调用 `activateWindow()`，避免抢焦点。

3. **推送光标**
   - `workspace.cursorPosChanged` → 节流到 20–30 Hz → `callDBus(..., "CursorMoved", x, y)`。
   - 初次加载时发送一次当前位置。

4. **推送全屏/窗口快照**
   - 活动窗口变化/`fullScreenChanged` → `FullscreenChanged`。
   - 窗口新增/删除/几何变化 → 生成 JSON 列表 → `WindowListChanged`。
   - 过滤：own overlay、dock/panel、tooltip、notification、desktop、skipTaskbar、最小化窗口。
   - 每条包含：`caption`、`resourceClass`、`x/y/w/h`、`fullscreen`、`pid`。

5. **注册热键**
   - 为 `GLOBAL_KEYS` + `FROZEN_KEYS` 注册 KWin shortcut。
   - 回调只做 `callDBus(..., "HotkeyPressed", id)`。
   - `loadScript` 模式下 `registerShortcut` 已实测生效；但快捷键冲突时 KWin 仍返回成功，因此加载后再用 KGlobalAccel `action(keyCode)` 检查最终归属，冲突项在设置页显示。

#### 3.3 脚本加载/卸载

运行时脚本（应用每次启动）：

```text
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript <abs path> slugcatpet-runtime
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.start
```

退出时：

```text
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript slugcatpet-runtime
```

运行时脚本使用独立 ID `slugcatpet-runtime`；加载前还会卸载可能由登录加载的持久插件 `slugcatpet`，避免重复回调。

持久安装（设置页显式启用）：

- 安装到 `$XDG_DATA_HOME/kwin/scripts/slugcatpet/`；
- `metadata.json` 必须包含 `KPackageStructure: "KWin/Script"`；
- 写 `kwinrc` 的 `[Plugins] slugcatpetEnabled=true/false`；
- 调 `org.kde.KWin.reconfigure`；
- 设置页提供「登录后自动加载 KWin 脚本」、状态显示和「重新加载 KWin 脚本」。

**注意：** KWin 脚本是特权集成，必须由用户明确安装/启用；应用不会在未告知的情况下修改 `kwinrc`。持久插件只影响下次登录，本次会话始终使用运行时脚本。实现与实测见 `ai-docs/PHASE5_PACKAGING.md`。

#### 3.4 坐标换算

KWin 给的是**全局逻辑坐标**，应用需要：

```text
overlay_local = global - overlay_origin
canvas_local = overlay_local / canvas_scale
```

- `overlay_origin` 优先用 `OverlayGeometryChanged`，启动前用目标 `QScreen.geometry().topLeft()`。
- 窗口矩形传给 `rain.set_shelters()` 前，一次性换算成 overlay-local 逻辑坐标；`window._poll_shelters()` 不再使用 `self.x()/self.y()/dpr`。
- 光标在别的屏幕时，返回 `None` 或越界坐标；行为层要显式处理，不要默认 `(0,0)`。

#### 3.5 Phase 3 退出标准

- 主表面稳定覆盖目标屏并保持置顶。
- 光标移动能驱动猫的跟随/交互；关闭 KWin 桥时明确降级。
- 全屏程序能触发 hide/sink（按现有 `fullscreen_mode`）。
- 挡雨窗口能按 KWin 快照工作；没有快照时返回空列表。
- 全局热键能触发冻结/HUD/退出/步进；冲突时有可见提示。

---

### Phase 4：平台功能补齐（3–5 人日，已完成开发期）

#### 4.1 开机自启

文件：`slugcatpet/platform/autostart.py`

新增 Linux 分支：

```text
~/.config/autostart/org.slugcatpet.SlugcatPet.desktop
```

内容：

```ini
[Desktop Entry]
Type=Application
Name=SlugcatPet
Exec=/path/to/slugcatpet
Icon=slugcatpet
Terminal=false
X-GNOME-Autostart-enabled=true
```

- 源码运行：`Exec` 指向 `.venv/bin/python` + `run_slugcatpet.py`。
- 打包运行：`Exec` 指向可执行文件。
- `sync_path()` 在启动时更新旧路径。
- `set_enabled()` 写/删该文件，返回是否成功。

#### 4.2 应用标识与桌面文件

文件：`slugcatpet/platform/appid.py`、`main.py`

- 在创建 `QApplication` 前/后设置：
  ```python
  QGuiApplication.setDesktopFileName("org.slugcatpet.SlugcatPet")
  QGuiApplication.setApplicationName("SlugcatPet")
  ```
- 安装 `org.slugcatpet.SlugcatPet.desktop` 和图标，KWin 才能按 app id 识别主表面。
- 托盘、任务栏、KWin 脚本都依赖这个 id。

#### 4.3 全屏检测

文件：`slugcatpet/platform/envwatch.py`

- 保留现有 `EnvironmentWatcher` 和 debounce。
- 增加可选 `fullscreen_provider`：
  ```python
  def fullscreen_provider():
      return bridge.active_fullscreen  # bool | None
  ```
- KWin 快照没有更新时返回 `None`，保持原状态，避免误隐藏。
- `state_provider`/`foreground_provider` 的 Windows 路径不变；Linux 不调用 `SHQueryUserNotificationState`。

#### 4.4 挡雨窗口

文件：`slugcatpet/platform/shelters.py`、`window.py`

- 新增 `KWinShelterProvider`，读取 bridge 的窗口列表。
- 返回 overlay-local 逻辑矩形；`window._poll_shelters()` 直接使用。
- 排除主表面、设置/音乐窗、dock/panel、tooltip。
- KWin 桥不可用时返回 `[]`，雨不挡窗口，但应用不崩。

#### 4.5 置顶/从属窗口

文件：`slugcatpet/platform/topmost.py`

- `TopmostKeeper` 在 Wayland 下不做 Win32 操作；主表面置顶由 KWin 脚本负责。
- `raise_topmost()` 对 overlay 可调用 `raise_()`，但不能保证 Wayland 层级；不要把它当置顶实现。
- `own_by()` 在嵌入 UI 后不需要；`ControlHud` 不再作为独立从属窗口。设置/音乐用 transient parent 即可。

#### 4.6 光标劫持/形状

文件：`slugcatpet/platform/cursorfx.py`

- 原生 Wayland 不支持 `SetCursorPos`/`ClipCursor`/系统光标替换。
- 第一版明确禁用：
  - 设置项灰显或加说明；
  - `CursorHijack` 保持 `mock=True`；
  - 不调用 `restore_cursors()` 的 Windows 路径。
- 如果未来必须做，需要 KWin effect 或 portal InputCapture，成本高，另立项目。

#### 4.7 托盘与雨循环卡片

文件：`main.py`、`ui/raintimer/tray.py`、`ui/raintimer/card.py`

- `QSystemTrayIcon` 在 KDE 下可用；`tray.geometry()` 可能无效。
- 卡片改为 overlay 子控件后，托盘点击的锚点按优先级：
  1. 标签栏可见 → 标签栏旁；
  2. KWin 光标可用 → 光标附近；
  3. 默认 → overlay 右下角。
- 不再依赖 `tray.geometry()` 的全局坐标。

#### 4.8 帧同步

文件：`slugcatpet/platform/vsync.py`

- 第一版可继续使用现有定时器降级路径（`supported()` 返回 False）。
- 若性能不足，Phase 4 再加 Wayland frame callback / `QWindow.frameSwapped` 的节拍器；不要为了 vsync 阻塞主功能。

#### 4.9 Phase 4 退出标准

- 自启开关可写/删 `.desktop`，重启后生效。
- 全屏程序能隐藏/沉底；退出全屏恢复。
- 挡雨窗口近似正确。
- 托盘可用；托盘卡片在合理位置出现。
- 不支持的功能在设置页有明确说明，不静默失败。

---

### Phase 5：打包、测试、文档（4–6 人日）

#### 5.1 Linux 打包

新增：

```text
packaging/linux/
  org.slugcatpet.SlugcatPet.desktop
  slugcatpet.svg
  install.sh
  uninstall.sh
  slugcatpet.spec          # PyInstaller，可选
```

要求：

- 不打包 Rain World 游戏素材；首次启动仍走 `gameassets` 导入。
- 安装 KWin 脚本、desktop 文件、图标。
- 保留 `uv run slugcatpet` 源码运行方式。
- `pyproject.toml` 增加 Linux classifier；`Environment :: Win32` 改为可选/多平台描述。

#### 5.2 测试

新增/调整：

| 测试 | 内容 |
| --- | --- |
| `tests/test_input_region.py` | 不同猫/面板/拖拽状态下的区域并集；空区域使用表面外 1×1；坐标 clamp |
| `tests/test_wayland_coords.py` | 全局→overlay→canvas 换算；DPR 1.5/2.0；多屏 |
| `tests/test_kwin_bridge.py` | DBus 方法参数/JSON 解析；服务注册失败降级 |
| `tests/test_overlay_layout.py` | 面板嵌入后的 geometry/动画/持久化迁移 |
| offscreen 行为回归 | 现有 `tests/behavior_check.py` 保持通过；物理不应受窗口层影响 |
| KWin 集成测试 | 启动应用，断言 overlay 尺寸、keepAbove、光标更新、窗口快照、热键 |
| 手动验收 | 点击穿透、拖猫、右键菜单、HUD/标签栏、托盘、全屏隐藏、音频 |

CI 建议：

- Linux：`ruff`、`params_doc --check`、offscreen 行为测试。
- Windows：现有完整行为回归，确认端口层没有回归。
- KWin 集成：自托管 runner 或本地脚本；不要求 GitHub 托管 runner 有 Plasma 会话。

#### 5.3 文档

- 更新 `README`：Linux 安装、KWin 集成、降级模式、已知限制。
- 更新 `ai-docs/PORTABILITY_ANALYSIS.md` 的结论，标注“原生 Wayland 方案已选定，详见本文”。
- 新增“Wayland 故障排查”：KWin 脚本未加载、光标不更新、输入区域异常、全屏检测失效。

---

## 4. 关键实现细节

### 4.1 主表面窗口标志

```python
flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
self.setWindowFlags(flags)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not self.debug)
```

- 不依赖 `WindowStaysOnTopHint`。
- 不在每帧调用 `move()`/`raise_()`。
- KWin 脚本负责几何和层级。
- 控制模式需要键盘时，由用户点击触发 `activateWindow()`，避免焦点抢占。
- overlay 首次映射时 KWin 仍可能自动激活它；脚本在映射后的宽限期内把键盘焦点还给原外部窗口，宽限期后的 ControlHud 激活按正常焦点处理。光标捕获面同样在激活后立即恢复原焦点。

### 4.2 输入区域算法

```python
def _pet_hit_region(pet) -> QRegion:
    # 抓点圆 + 身体/头/髋包围盒，外扩 6~8 px
    ...


def _item_hit_region(item) -> QRegion:
    # 物品包围盒 + 外扩
    ...


def _overlay_panels(self):
    return (self._tab, self._hud, self._control_hud, self._rain_dial, self._rain_card, self._toast)
```

规则：

- 默认：猫身 + 物品 + 可见面板。
- 拖拽/放置/控制/菜单打开：整窗。
- 无交互：表面外 1×1。
- 只在区域变化时 `windowHandle().setMask(region)`，随后调用 `windowHandle().requestUpdate()` 提交；不提交时 mask 可能不生效。
- `QRegion` 使用 overlay 局部逻辑坐标。
- 不要用 `QWidget.setMask()` 代替 `QWindow.setMask()`；前者还会影响子控件绘制裁剪，容易把 UI 裁掉。

### 4.3 KWin 脚本几何

已验证的最小写法：

```js
function placeOverlay(w) {
    if (!w || w.desktopFileName !== "org.slugcatpet.SlugcatPet") return;
    var target = workspace.screens[0];   // 第一版固定主屏；后续可改为配置的输出名
    var g = Object.assign({}, target.geometry);
    g.x = target.geometry.x;
    g.y = target.geometry.y;
    g.width = target.geometry.width;
    g.height = target.geometry.height;
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.skipSwitcher = true;
    w.frameGeometry = g;
}
```

注意：

- 目标屏要用 `workspace.screens[0]`，不要用 `w.output`：如果窗口初始落在副屏，用 `w.output` 会把它一直钉在副屏。
- `frameGeometry` 是 `QRectF`，不能直接赋 `QRect`。
- `Object.assign({}, ...)` 中转是 KWin 脚本社区的常用写法；本机验证可改变窗口尺寸。
- Wayland 客户端不知道自己的全局位置，`QWidget.geometry()` 仍可能显示 `(0,0)`；不要拿它判断是否定位成功，用 KWin 日志/截图验证。
- `workspace.clientArea(KWin.WorkArea, output, desktop)` 在本机 KWin 6.8 返回虚拟桌面尺寸（1707×1967），不是单屏；第一版用目标 `output.geometry`。

### 4.4 KWin 脚本事件

```js
workspace.windowAdded.connect(placeOverlay);
workspace.windowActivated.connect(placeOverlay);
workspace.cursorPosChanged.connect(sendCursor);
```

- `windowActivated` 时只重设 `keepAbove`，不激活主表面。
- 窗口列表变化时发送快照；对每个窗口连接 `frameGeometryChanged` 需要去重，避免重复连接。
- 光标推送要节流；不要每个像素都发 DBus。

### 4.5 热键映射

现有 id：

```text
HK_ABORT, HK_QUIT, HK_HUD, HK_PLACE_ESC, HK_FREEZE, HK_STEP, HK_STEP10
```

KWin 脚本按相同 id 调用 `HotkeyPressed`。应用侧：

- `HK_STEP`/`HK_STEP10` 只在 `pet.frozen` 时执行；不冻结时直接忽略。
- KWin 快捷键冲突时，脚本日志会提示；应用设置页显示“可能未注册”。
- 如果用户不接受 KWin 脚本，后续可接 `org.freedesktop.portal.GlobalShortcuts`；portal 会要求用户授权，且不同桌面行为不一致。

### 4.6 降级模式

`WaylandKWinBackend.available == False` 时：

| 功能 | 降级 |
| --- | --- |
| 主表面几何 | 由合成器放置；首次显示可能不是全屏 |
| 置顶 | 无保证 |
| 光标跟随 | 使用最近一次局部指针位置；不跟随桌面 |
| 全屏检测 | 禁用，不自动隐藏 |
| 挡雨窗口 | 返回空 |
| 全局热键 | 不注册；托盘/标签栏仍可操作 |
| 光标劫持 | 禁用 |

设置页必须显示当前后端和不可用原因，不能只写“Linux”。

---

## 5. 代码改动清单

| 文件/目录 | 改动 | 阶段 |
| --- | --- | --- |
| `slugcatpet/platform/backend.py` | 新增平台接口与选择逻辑 | 1 |
| `slugcatpet/platform/wayland/kwin_bridge.py` | QtDBus 服务、光标/窗口快照/热键信号 | 3 |
| `slugcatpet/platform/wayland/kwin_script/` | KWin 脚本、metadata、安装/卸载 | 3 |
| `slugcatpet/platform/wayland/input.py` | 输入区域辅助、坐标换算、mask 提交 | 1 |
| `slugcatpet/platform/wayland/cursor.py` | KWin 光标提供者/降级 | 1 |
| `slugcatpet/window.py` | 主表面、输入区域、光标、workspace、shelters、control、菜单 | 1–3 |
| `slugcatpet/control/mouse.py` | 移除 Win32-only 穿透；接后端输入区域 | 1 |
| `slugcatpet/control/hotkey.py` | 拆分 Windows/KWin/portal 后端 | 3 |
| `slugcatpet/platform/envwatch.py` | `fullscreen_provider`，Windows 路径保持 | 4 |
| `slugcatpet/platform/topmost.py` | Wayland no-op/桥接 | 4 |
| `slugcatpet/platform/shelters.py` | KWin 窗口矩形提供者 | 4 |
| `slugcatpet/platform/autostart.py` | XDG autostart | 4 |
| `slugcatpet/platform/appid.py` | `setDesktopFileName`/应用名 | 4 |
| `slugcatpet/platform/cursorfx.py` | Wayland 明确禁用 | 4 |
| `slugcatpet/platform/vsync.py` | 保持定时器降级，后续可选 frame callback | 4 |
| `slugcatpet/ui/panels/tabbar.py` | 子控件化、局部坐标、toast | 2 |
| `slugcatpet/ui/panels/hud.py` | 子控件化、局部拖动 | 2 |
| `slugcatpet/ui/panels/controlhud.py` | 子控件化、焦点 | 2 |
| `slugcatpet/ui/panels/hudrow.py` | 右键菜单/拖动局部坐标 | 2 |
| `slugcatpet/ui/panels/catmenu.py` | popup 锚点 | 2 |
| `slugcatpet/ui/panels/appearance.py` | 弹出层局部锚点 | 2 |
| `slugcatpet/ui/panels/scenemusic.py` | 弹出层局部锚点 | 2 |
| `slugcatpet/ui/panels/settings.py` | 去掉自定义 move/居中 | 2 |
| `slugcatpet/ui/panels/musicpanel.py` | 去掉自定义 move/居中 | 2 |
| `slugcatpet/ui/raintimer/dial.py` | 子控件化、提示/拖动 | 2 |
| `slugcatpet/ui/raintimer/card.py` | 子卡片、外部点击关闭 | 2 |
| `slugcatpet/ui/widgets/dialogs.py` | 确认框改 overlay 模态/transient | 2 |
| `slugcatpet/ui/widgets/tips.py` | 子 label/局部定位 | 2 |
| `slugcatpet/ui/widgets/screens.py` | overlay rect 替代全局 screenAt | 2 |
| `slugcatpet/main.py` | 组装 backend、embed、bridge、autostart、tray | 1–4 |
| `packaging/linux/` | desktop/icon/install/KWin 脚本 | 5 |
| `pyproject.toml` | Linux classifier/entry point/可选依赖 | 5 |
| `tests/` | 输入区域、坐标、桥、布局、回归 | 5 |

---

## 6. 验收标准

达到以下条件才算“原生 Wayland 可用移植”：

1. 桌面空白区域点击能穿透到下方应用。
2. 点击猫身、拖拽猫、右键菜单正常。
3. TabBar/HUD/控制条/雨表盘/雨卡片能定位、拖动、保存位置。
4. 主表面稳定覆盖目标屏，普通窗口不遮挡。
5. 光标跟随可用；或明确进入“不跟随光标”降级模式，且设置页可见。
6. 托盘可打开设置/音乐/退出；托盘不可用时 TabBar 可退出。
7. 全屏程序能触发隐藏/沉底，或明确禁用并有说明。
8. 挡雨窗口近似正确；KWin 桥不可用时雨不挡窗口且不崩。
9. 雨/雪/音频/素材/皮肤正常。
10. Linux 物理回归通过；帧哈希按平台记录，不与 Windows 直接比较。
11. `uv run slugcatpet` 和打包产物都能启动。
12. Windows 原有行为不回归。

---

## 7. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
| --- | --- | --- | --- |
| KWin 脚本在某些 Plasma 版本/配置下不生效 | 中 | 高 | Phase 0 闸门；失败回退 XWayland；设置页显示状态 |
| `frameGeometry` setter 兼容性 | 中 | 高 | 用 `Object.assign` 中转；固定测试 KWin 6.8；记录版本 |
| `workspace.clientArea` 单屏重载异常 | 已复现 | 中 | 用 `output.geometry`；面板遮挡后续再处理 |
| 输入区域有边缘缝隙/挡桌面 | 中 | 高 | 抓点外扩、拖拽时整窗、手工点击测试、区域单测 |
| 快速拖拽丢事件 | 中 | 中 | 拖拽/放置/控制时整窗接收输入 |
| 子控件嵌入后焦点/键盘失效 | 中 | 高 | Phase 0 验证；用户点击后 `activateWindow()`；保留失焦暂停 |
| Wayland popup/menu 定位不稳 | 中 | 中 | `QMenu` 以 overlay 为 parent；必要时改 overlay 内菜单 |
| KWin DBus 高频光标消息 | 中 | 中 | 20–30 Hz 节流；只发变化 |
| DPR 1.5/2.0 坐标错位 | 中 | 中 | 统一逻辑坐标；专门测试；禁止混用物理像素；`show()` 前绑定目标 `QScreen`，避免 KWin 移动窗口后 DPR 停留在旧屏 |
| 多屏/目标屏选择 | 中 | 中 | 第一版只支持主屏；后续加输出配置 |
| 非 KDE Wayland 功能缺失 | 高 | 中 | 明确降级；文档写明 KDE 专用 |
| 热键冲突 | 中 | 低 | 设置页提示；后续 portal fallback |
| 打包缺少 KWin 脚本/desktop 文件 | 中 | 中 | 安装脚本 + 启动自检 + 文档 |
| Windows 回归 | 低 | 高 | 平台后端隔离；Windows CI 保留 |

---

## 8. 工作量估算

| 阶段 | 人日 |
| --- | ---: |
| Phase 0 可行性闸门 | 2–3 |
| Phase 1 主表面/输入区域 | 4–6 |
| Phase 2 UI 嵌入 | 8–12 |
| Phase 3 KWin 桥 | 4–6 |
| Phase 4 平台功能 | 3–5 |
| Phase 5 打包/测试/文档 | 4–6 |
| 缓冲（约 15%） | 4–6 |
| **合计** | **29–44 人日** |

按 1 名熟悉 Qt/KDE 的开发者估算，约 **6–9 周**。UI 嵌入是最大不确定项；如果只做“猫 + 输入穿透 + 标签栏”，可先砍到约 15–20 人日，但 HUD/控制条/雨表盘仍需后续补齐。

---

## 9. 不在本计划内

- 不实现 GNOME/Sway 的完整原生支持。
- 不实现 Wayland 全局光标劫持/系统光标替换。
- 不实现跨所有合成器的 layer-shell 或自定义 QPA 插件。
- 不修改物理、行为、渲染核心。
- 不把 Rain World 游戏素材打包进发布物。
- 不使用 Wine/Proton 作为正式方案。

---

## 10. 附录：本机可行性验证记录

以下为本次分析期间做的**最小实验**，不是完整实现：

### 10.1 layer-shell 现状

- KWin 注册 `zwlr_layer_shell_v1` v5。
- 系统有 `layer-shell-qt 6.8.0` 和 `liblayer-shell.so`。
- PySide6 6.12 wheel 的 `wayland-shell-integration` 没有 layer-shell：
  - 设置 `QT_WAYLAND_SHELL_INTEGRATION=layer-shell` 报
    `No shell integration named "layer-shell" found`。
- 结论：第一版不走 layer-shell。

### 10.2 KWin 脚本几何/置顶

- 测试窗口：`Qt.Tool | FramelessWindowHint`，标题 `slugcatpet-probe`。
- KWin 脚本找到窗口后：
  - `w.keepAbove = true` 生效（日志确认）。
  - `w.frameGeometry = Object.assign({}, w.output.geometry)` 后，应用侧窗口尺寸变为 `1707×1067`（HDMI-A-1 逻辑尺寸），证明 setter 生效。
  - 正式脚本应把目标改成 `workspace.screens[0].geometry`，不要用 `w.output`，否则窗口初始在副屏时会被钉在副屏。
- 直接赋 `w.output.geometry` 报 `Cannot assign KWin::Rect to KWin::RectF`；必须中转。
- Wayland 客户端 `QWidget.geometry()` 的位置仍可能是 `(0,0)`，不能用它判断全局位置。

### 10.3 输入区域

`QWindow.setMask(QRegion(50,50,100,100))` 的 `WAYLAND_DEBUG` 输出：

```text
wl_compositor.create_region(new id wl_region#53)
wl_region#53.add(50, 50, 100, 100)
wl_surface#43.set_input_region(wl_region#53)
```

表面外区域：

```text
wl_region#51.add(300, 300, 1, 1)
wl_surface#43.set_input_region(wl_region#51)
```

空 `QRegion` 会发送 `set_input_region(nil)`，等价于整窗接收输入；因此不能用空区域做穿透。

Phase 0 复核发现了更关键的一点：**只调用 `setMask()` 不够，必须提交表面**。只设置 mask 时协议里虽出现 `set_input_region`，但没有后续 `wl_surface.commit()`，实测点击仍被 overlay 接收；在 `setMask()` 后调用 `windowHandle().requestUpdate()`，协议出现 commit 后，区域外点击才正常穿透到下层窗口。详见 `ai-docs/PHASE0_RESULTS.md` 第 3.3 节。

### 10.4 KWin → DBus 光标

- Python `QtDBus` 注册 `org.slugcatpet.Probe`。
- KWin 脚本 `callDBus(..., "Cursor", workspace.cursorPos.x, workspace.cursorPos.y)`。
- Python 收到：
  ```text
  CURSOR 540 1827
  ```
- 注意：QtDBus 默认接口名是 Python 类名；必须用 `Q_CLASSINFO("D-Bus Interface", ...)` 固定接口，否则 KWin 调用会找不到方法。

### 10.5 `workspace.clientArea` 异常

- KWin 6.8 中：
  ```js
  workspace.clientArea(KWin.WorkArea, output, workspace.currentDesktop)
  ```
  对 eDP-1/HDMI-A-1 都返回 `RectF(0, 0, 1707, 1967)`（整个虚拟桌面）。
- 因此第一版用 `output.geometry`，不要依赖该重载做单屏工作区计算。

### 10.6 当前屏幕

- Qt 主屏：`eDP-1`，`1440×900`，窗口 DPR 2.0。
- 副屏：`HDMI-A-1`，`1707×1067`，KWin 逻辑尺寸约 `1707.333×1067.333`；窗口 `devicePixelRatioF()` 为 **1.5**。
- 但 `QScreen.devicePixelRatio()` 对本机两块屏都报 **2.0**，与 HDMI 窗口实际 DPR 不一致。
- 结论：渲染缩放用 `window.devicePixelRatioF()`；全局坐标用 KWin 逻辑几何；输入区域用 overlay 局部逻辑坐标，不要用 `QScreen` 统一乘 DPR。
- Phase 0 在 HDMI 1.5 和 eDP 2.0 下点击换算误差均为 0 px。
- **输出绑定是额外约束**：如果窗口先在 HDMI 上创建、再由 KWin 只改 `frameGeometry` 移到 eDP，Qt 窗口 DPR 仍是 1.5；必须在 `show()` 前对目标 `QScreen` 调用 `setScreen()`，否则渲染缩放会停留在旧屏。运行中切换输出时同样要更新/重建表面。

---

**总结：** 原生 Wayland 路线可行，但必须接受“单主表面 + KWin 专用桥 + 降级模式”的架构。Phase 0 已完成并判定 **Go（有条件）**，未发现需要回退 XWayland 的阻塞项；下一步按 Phase 1→5 推进，先落实输入区域提交、子控件本地坐标和窗口级 DPR，再迁移全部 UI。
