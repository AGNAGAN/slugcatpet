# Phase 1 结果：主表面、输入区域与 KWin 桥

- 日期：2026-10-20
- 对应计划：`ai-docs/NATIVE_WAYLAND_PORT_PLAN.md` 的 Phase 1
- 结论：**Phase 1 完成**。第一版主表面已经在 eDP-1 上全屏、穿透、可点击，并由 KWin 脚本置顶；KWin 不可用时仍有降级路径。
- 验证环境：KDE Plasma 6.8 / KWin 6.8 / Wayland，PySide6 6.12；eDP-1 1440×900（窗口 DPR 2.0），HDMI-A-1 位于 y=900 下方。

---

## 1. 实现内容

### 1.1 桌面后端接口

新增 `slugcatpet/platform/backend.py`：

- `DesktopBackend`：几何、置顶、光标、输入区域、全屏、挡雨窗口、自启、热键的统一接口；
- `Win32Backend`：包装现有 Windows 输入穿透和光标逻辑，Windows 路径不变；
- `NullBackend`：非 KDE/非 Wayland 或 KWin 不可用时的降级实现；
- `create_backend()`：在 `win32` 与原生 Wayland 之间选择。

接口同时保留了计划中的名称：

- `cursor_pos()`（本实现主路径为 `cursor_global()` / `cursor_overlay_pos()`）；
- `set_overlay_geometry()`（本实现主路径为 `configure_overlay(screen_name, rect)`）；
- `foreground_fullscreen()`、`window_rects()`、`set_autostart()`、`install_hotkeys()` 第一版返回未知/不可用，留给 Phase 3/5。

### 1.2 主表面

`slugcatpet/window.py`：

- Wayland 下去掉 `WindowStaysOnTopHint` 的依赖，保留 `FramelessWindowHint | Tool`；
- 在 `show()` 前对目标 `QScreen` 调用 `setScreen()`；
- 不再调用 `move()`，位置由 KWin 脚本设置；
- 目标输出名称使用初始化时绑定的 `self._screen`，不采用 `self.screen()`。实测 KWin 初次放置会先把窗口放到光标所在输出，若此时读取 `window.screen()` 会把 HDMI 误当成目标输出；
- `overlay_rect()` 给出带地板下延带的全局逻辑矩形；
- `apply_workspace()` / `_watch_screen()` 更新目标输出或工作区后，重新渲染 KWin 脚本；
- 光标改为 `backend.cursor_overlay_pos()` → `to_logical()`；桥不可用时返回 `_last_local_pointer`，再没有则返回 `None`；
- `mouseMoveEvent()` / `mousePressEvent()` 维护本地降级光标，`leaveEvent()` 清空；
- 输入区域统一通过 `backend.set_input_region()` 提交；
- `cursor_available` 暴露给设置页；没有全局光标时在交互设置下显示降级提示。

`slugcatpet/platform/appid.py`：

- 增加 `DESKTOP_FILE_NAME = "org.slugcatpet.SlugcatPet"`；
- 只有系统中确实安装了对应 `.desktop` 时才设置 Wayland app_id，避免源码运行时 portal 报 `App info not found`。KWin 脚本以窗口标题为主识别条件，源码运行不受影响。

### 1.3 KWin 脚本与 DBus 桥

新增：

```text
slugcatpet/platform/wayland/kwin_bridge.py
slugcatpet/platform/wayland/kwin_script/metadata.json
slugcatpet/platform/wayland/kwin_script/contents/code/main.js
```

`WaylandKWinBackend`：

- 注册 session bus 服务 `org.slugcatpet.Bridge`，路径 `/Bridge`，接口 `org.slugcatpet.Bridge`；
- 通过 `@ClassInfo({"D-Bus Interface": ...})` 固定接口名；
- 暴露 `CursorMoved(int,int)`、`OverlayGeometryChanged(int,int,int,int)`、`Log(QString)`；
- 通过 `org.kde.KWin /Scripting` 的 `loadScript` / `start` / `unloadScript` 管理脚本；
- 把运行时配置（目标输出、overlay 全局矩形、app id、标题、DBus 名称）替换进脚本模板，写到 `~/.slugcatpet/kwin/slugcatpet.js`；
- 启动前先 `unloadScript`，清理上次异常退出留下的同名脚本；
- 退出时卸载脚本、注销对象和服务，可重复调用。

KWin 脚本职责：

- 按标题 `SlugcatPet Overlay`（并兼容 app id）找到主表面；
- 设置 `frameGeometry` 为目标输出左上角 + Python 计算的 overlay 尺寸；
- 设置 `keepAbove = true`、`skipTaskbar = true`、`skipSwitcher = true`；
- 窗口新增/激活/切换桌面时重新扫描；
- 把实际 `frameGeometry` 推回 Python；
- 把 `workspace.cursorPos` 推回 Python。

---

## 2. 实测证据

### 2.1 脚本加载与几何

运行完整应用后，KWin 日志与 Python 日志确认：

```text
KWin bridge: script loaded for eDP-1 QRect(0, 0, 1440, 932)
KWin bridge: script loaded
slugcatpet target eDP-1 overlay 1440x932
```

KWin 探针脚本读取到：

```text
PHASE1P overlay KWin::RectF(0, 0, 1440, 932)
  output eDP-1
  keepAbove true
  desktop org.slugcatpet.SlugcatPet
```

说明：完整应用在 eDP-1 上得到 1440×932 的主表面；KWin 有时会把窗口高度夹到输出高度 900，Python 侧的输入区域和光标换算仍以实际窗口坐标工作。置顶和跳过任务栏生效。

### 2.2 输入区域与点击路由

使用绝对 uinput 鼠标、目标窗口铺满 eDP-1，验证：

```text
TARGET_CLICK 500 100
PET_CLICK 720 846
```

- 宠物/面板之外点击到达下方目标窗口；
- 猫头位置点击到达 overlay；
- 输入区域仍是 `QWindow.setMask()` + `requestUpdate()`，提交行为由 `tests/test_wayland_regions.py` 覆盖。

### 2.3 全局光标

KWin → DBus 推送实测：

```text
KWin bridge: cursor 500,100
KWin bridge: cursor 720,846
```

overlay 原点为 `(0,0)` 时，`cursor_logical()` 分别得到 `(250,50)` 与 `(360,423)`（`canvas_scale=2`）。光标移到 overlay 外时返回 `None`，行为层已有 `None` 分支。

### 2.4 降级路径

把后端替换为 `NullBackend` 后应用仍能启动、绘制和结束；没有 KWin 脚本时只是没有全局几何/置顶/光标，不会抛异常。KWin 服务不可用或脚本加载失败时，`attach_overlay()` 返回 False，应用继续运行。

---

## 3. 验证命令

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python tools/params_doc.py --check
timeout -s INT 8s env SLUGCATPET_HOME=/tmp/opencode/slugcatpet-phase1 \
  uv run python -m slugcatpet.main
```

结果：

- ruff 通过；
- 11 个单元测试通过（新增 `tests/test_wayland_backend.py`，覆盖脚本占位符、光标换算、桥不可用降级）；
- 完整应用退出后 `isScriptLoaded slugcatpet` 为 `false`，无遗留脚本；
- 源码运行不再出现 portal app id 警告。

---

## 4. 已知限制

1. 第一版只绑定主输出，尚未提供选择 eDP/HDMI 的设置项；HDMI 的 1.5 DPR 路径需要在 Phase 4/输出选择中补实测。
2. KWin 脚本当前只负责几何、置顶和光标；全屏检测、窗口矩形快照、全局热键、挡雨窗口仍是 Phase 3 内容，`supports_*` 对这些能力返回 False/空。
3. KWin 脚本按窗口标题识别主表面，标题是固定英文常量；设置/音乐窗口使用不同标题。后续若标题本地化，需要同步更新识别条件。
4. 异常被杀（SIGKILL）时脚本会留在 KWin 中；下次启动会先卸载同名脚本，验证正常退出路径已清理。
5. 应用由源码启动且没有安装 `.desktop` 时不会设置自定义 app_id；进入打包/XDG 自启阶段后安装 desktop 文件即可启用。
6. KWin 有时将 932 高的主表面夹到 900；这是合成器对窗口几何的约束，不影响猫的地板线（`_HL=450`）和输入区域。

---

## 5. 下一步

- Phase 3：把 `foreground_fullscreen()`、`window_rects()`、`FullscreenChanged`、`WindowListChanged`、`registerShortcut` 接到同一桥；
- 在 KWin 桥可用后恢复环境全屏收起/沉底、挡雨窗口和全局热键；
- Phase 4/输出选择：验证 HDMI 1.5 DPR、非主输出和任务栏占用；
- 为 KWin 脚本/DBus 失败增加设置页可见状态，而不是静默降级。
