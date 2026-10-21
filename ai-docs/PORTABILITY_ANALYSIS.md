# Linux 移植可行性分析

- 日期：2026-10-20；最终结论更新于 2026-10-21
- 范围：在**当前 Linux 环境**中评估 `slugcatpet` 是否能直接运行、作为桌面宠物使用，以及需要哪些修改。
- 性质：移植前静态分析 + 当时环境实测；**本文件保留历史判断，实际实施结果见文末“最终结论”**。

> **最终结论（2026-10-21）：** 本项目已选择并完成**原生 Wayland**路线，而不是当时建议的 X11/XWayland 最短路线。单全屏 overlay + 动态输入区域、KWin JS/DBus 桥、全局光标读取、Qt 6.12 pointer-warp 光标写入、焦点恢复、多输出逃逸、Linux 打包、KWin 持久安装、desktop/图标和 Linux/Windows CI 均已实现。仍待完成的是真实猫行为、Rain World 全屏和注销登录等最终人工验收；详见 `REMAINING_WORK.md`、`PHASE5_CURSOR_WRITE.md` 和 `PHASE5_PACKAGING.md`。

## 1. 当时的结论摘要

**当前源码不能在 Linux 上“开箱即用”地作为桌面宠物使用。**

可以分成两层看：

| 层面 | 结论 |
| --- | --- |
| 启动进程、导入依赖、跑物理/行为/渲染 | 基本可行；offscreen 启动无崩溃 |
| 读取 Rain World 素材 | 可行；Windows 版 Unity 资源可在 Linux 上用 UnityPy 读取 |
| 音频播放 | 可行；Qt FFmpeg 后端能加载 OGG，音频输出设备正常 |
| 单实例、存档、皮肤、目录结构 | 基本可复用 |
| 透明全屏窗口的鼠标穿透 | **不可用，当前会挡住整个桌面** |
| 窗口定位、置顶 | **原生 Wayland 不可用；XWayland 下可行** |
| 全局鼠标位置 | **当前 Wayland 会话不可用** |
| 全局热键、开机自启、全屏检测、挡雨、光标劫持 | **Windows 专用或静默降级** |
| 系统托盘 | KDE 下很可能可用，但尚未实际点击验证 |
| Linux 打包 | **没有现成方案，仅 Windows PowerShell/PyInstaller 流程** |
| 行为/渲染回归 | 物理大体可复现；帧哈希跨平台不可比 |

最关键的判断：

1. **鼠标穿透是 P0 阻塞项**：不修就没有可用的桌面交互。
2. **全局光标是 Wayland 路线的 P0 阻塞项**：不修则猫的跟随、舔光标、扑咬、后空翻等行为异常。
3. **窗口定位是原生 Wayland 的架构级问题**：现有 UI 大量依赖 `move()` 的顶层 `Qt.Tool` 窗口。
4. **最短可行路线是 X11/XWayland 后端**，而不是直接做原生 Wayland。
5. **原生 Wayland 需要改 UI 架构**，不只是加几个 `sys.platform` 分支。

---

## 2. 当前环境与验证方法

### 2.1 环境

| 项目 | 值 |
| --- | --- |
| 系统 | CachyOS Linux x86_64，kernel 7.2.11 |
| Python | 3.12.15 |
| PySide6 | 6.12.0 |
| UnityPy | 1.25.4 |
| numpy | 2.5.4 |
| Pillow | 12.3.0 |
| 桌面 | KDE Plasma 6.8.0 / KWin 6.8.0 |
| 会话类型 | Wayland（`XDG_SESSION_TYPE=wayland`） |
| XWayland | 可用，`DISPLAY=:0` |
| X11 Plasma 会话 | **未安装**（`/usr/share/xsessions` 为空） |
| 主屏 | `eDP-1` 1440×900 逻辑像素，DPR 2 |
| 副屏 | `HDMI-A-1` 1707×1067 逻辑像素，DPR 2 |
| Rain World | `/mnt/Data/Game/SteamShareLinux/steamapps/common/Rain World/` |

KWin 技术支持信息中确认：

- `SHAPE: yes; Version: 0x11`
- `XFIXES: yes; Version: 0x50`
- `Operation Mode: Wayland`

这意味着在 XWayland 下做 X11 输入区域、窗口几何和 XFixes 相关操作有基础。

### 2.2 已验证事项

- `uv run` 下依赖全部可导入。
- offscreen 模式启动应用 10 秒，没有崩溃；Qt 的 `raise()`/托盘警告来自平台插件，不是应用异常。
- 从 Windows 版 Rain World 的 `RainWorld_Data/resources.assets` 成功提取图集、4 首场景音乐、7 个雨声、9 个业力音效，完整素材约 38 MB。
- `QMediaPlayer` 使用 Qt FFmpeg 后端成功加载 OGG：`MediaStatus.LoadedMedia`，无错误，时长读取正常。
- `QMediaDevices.audioOutputs()` 能找到多个 ALSA/PipeWire 输出设备。
- KDE 的 `org.kde.StatusNotifierWatcher` 已注册，`IsStatusNotifierHostRegistered = true`。
- XWayland 下测试 `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint` 窗口：
  - `xprop` 显示 `_NET_WM_STATE_ABOVE`、`_NET_WM_STATE_STAYS_ON_TOP`。
  - 窗口类型包含 `_KDE_NET_WM_WINDOW_TYPE_OVERRIDE`。
  - 请求位置 300,250 逻辑像素，X11 实际坐标为 600,500 物理像素（DPR 2），说明位置被接受。
- `uv run ruff check .` 通过。
- `uv run ruff format --check .` 通过。
- `uv run python tools/params_doc.py --check` 通过。

### 2.3 没有做的事

**没有把完整 GUI 启动到真实桌面。** 原因不是无法启动，而是当前代码在 Linux 上没有鼠标穿透；完整启动后全屏透明窗口可能拦截桌面操作。这个结论来自代码路径和独立 Qt 窗口实验，不是来自一次“桌宠正常运行”的实测。

---

## 3. 已验证可复用的部分

### 3.1 物理、行为、渲染核心

核心模拟与平台层相对分离，`PetWindow`、`core/creature.py`、`brain/fsm.py`、渲染/行为代码大部分不依赖 Win32。

但跨平台回归结果并不完全一致：

- `items`、`env`、`cursor_play`：物理状态逐 tick 一致，但帧哈希分别有 83/100、87/90、108/108 帧不同。
- `trouble`：在 tick 3437 出现物理分歧，pet 1 的 `c0.x` 基线约 `510.587`，本次约 `510.341`，差约 0.246 px。
- 帧哈希不同基本可归因于 Linux/Qt 6.12/offscreen 与 Windows 的渲染差异；物理分歧仍需 Windows 复跑确认，不能直接判定为移植失败。

结论：**物理/行为核心可复用，但跨平台回归基线需要拆分。**

### 3.2 素材提取

`slugcatpet/gameassets.py` 已包含 Linux Steam 根目录：

- `~/.steam/steam`
- `~/.local/share/Steam`
- macOS 的 `~/Library/Application Support/Steam`

当前通过手动指定游戏目录导入成功，并写入 `~/.slugcatpet/assets/game_path.txt`；后续 `detect_install()` 可以直接复用。

Windows 版 Rain World 的资源文件在 Linux 上可由 UnityPy 直接解析，不需要运行游戏或 Wine。

结论：**素材路径基本可移植；只需在文档中说明手动选目录和 Steam 库路径。**

### 3.3 音频

`audio/player.py` 使用 `QMediaPlayer` + `QAudioOutput`，`audio/ambience.py` 使用 `QSoundEffect`。

- PySide6 Linux wheel 带 QtMultimedia FFmpeg 后端。
- 当前环境能加载 OGG 并读取时长。
- `QSoundEffect` 使用 WAV，当前素材是 WAV，理论上可用；未单独做听感验证。

结论：**音频可移植；需要在 PipeWire/ALSA 环境做一次实际播放验证。**

### 3.4 单实例与存档

`platform/singleton.py` 使用 `QLockFile` + `QLocalServer`，不依赖 Win32 命名互斥量，Linux 可用。

`_paths.py` 使用 `Path.home() / ".slugcatpet"`，Linux 正常。

结论：**单实例、存档、用户目录基本可复用。**

### 3.5 托盘

KDE Wayland 使用 StatusNotifierItem，当前宿主已注册。`QSystemTrayIcon` 在 KDE 下通常可用。

但需要注意：

- `QSystemTrayIcon.geometry()` 在 Wayland 下可能无效。
- `main.py` 在托盘几何无效时会退回 `QCursor.pos()`，而当前 Wayland 下该值是 `(0,0)`，雨循环卡片可能出现在左上角。
- 需要实际点击托盘图标、打开菜单、显示通知验证。

结论：**很可能可用，但不是零风险。**

### 3.6 XWayland 下的窗口定位与置顶

XWayland 测试窗口证明：

- `WindowStaysOnTopHint` 会映射为 `_NET_WM_STATE_ABOVE`。
- `Qt.Tool` + `FramelessWindowHint` 会带 `_KDE_NET_WM_WINDOW_TYPE_OVERRIDE`。
- `move()` 请求的位置被 X11 接受。

这使 XWayland 成为当前环境最现实的兼容路线。

---

## 4. 阻塞项与代码依据

### 4.1 鼠标穿透：当前完全无效

相关代码：

- `slugcatpet/window.py:93-115`
  - 创建 `FramelessWindowHint | WindowStaysOnTopHint | Tool` 的全屏透明窗口。
  - `resize(geom["win_w"], geom["win_h"])`，大小等于主屏可用工作区。
  - `move(area.x(), area.y())`。
- `slugcatpet/window.py:304-332`
  - `_update_passthrough()` 根据光标是否在猫身、是否拖拽、是否放置模式，决定 `want`。
  - 通过 `set_passthrough(self._hwnd, want)` 切换。
- `slugcatpet/control/mouse.py:155-165`
  - `set_passthrough()` 在 `not _IS_WIN or not hwnd` 时直接 `return`。

Linux 上没有 `WS_EX_TRANSPARENT` 的等价实现，结果是：

- 全屏透明窗口仍然接收整个屏幕的鼠标事件。
- 桌面图标、其他窗口、右键菜单都会被挡住。
- 透明只是视觉透明，不是输入穿透。

**这是当前版本最严重的可用性阻塞项。** 只强制 `QT_QPA_PLATFORM=xcb` 不会修复它。

### 4.2 原生 Wayland 不允许普通顶层窗口任意定位

相关代码：

- `slugcatpet/window.py:114-115`：宠物窗 `resize()` + `move()`。
- `slugcatpet/window.py:685-704`：`apply_workspace()` 再次 `resize()` + `move()`。
- `slugcatpet/ui/panels/tabbar.py`：`_apply_collapsed()` / `_apply_expanded()` 使用 `setGeometry()`。
- `slugcatpet/ui/panels/hud.py`：`_place()` 和拖动使用 `move()`。
- `slugcatpet/ui/panels/controlhud.py:95-105`：`_place()` 使用 `move()`。
- `slugcatpet/ui/panels/hud.py:144-149`、`controlhud.py:163-170`：拖动时 `move()`。

Wayland 的 `xdg_toplevel` 没有“客户端设置绝对位置”的请求。Qt 的 `QWidget.move()` 在原生 Wayland 下不能可靠生效，实际位置由 KWin 决定。

因此：

- HUD、TabBar、控制条、雨循环卡片的定位和拖动会失效。
- 保存的 `tab_y`、`hud_x`、`hud_y` 没有意义。
- 多窗口布局需要重写，或必须走 XWayland。

### 4.3 当前 Wayland 会话拿不到可靠的全局光标

实测：

- `QCursor.pos()` 在 `QT_QPA_PLATFORM=wayland` 下返回 `(0,0)`。
- `QCursor.pos()` 在 `QT_QPA_PLATFORM=xcb` 下也返回 `(0,0)`。
- 直接调用 XWayland 的 `XQueryPointer` 也返回 `(0,0)`。

影响：

- `window.cursor_logical()` 使用 `QCursor.pos()`，会把光标当成屏幕左上角。
- `_do_tick()` 中的 `cur = self.cursor_logical()` 会让猫朝左上角移动。
- `_update_passthrough()` 基于错误光标判断，可能让猫永远不可点击，或一直拦截桌面。
- 依赖光标位置的行为（舔、扑、后空翻、低好感攻击）都会异常。

Wayland 本身没有通用全局指针位置协议。XWayland 只有在指针位于 XWayland 表面时才知道位置；指针在原生 Wayland 窗口上时通常是过期值。

这是 XWayland 路线下仍然最难的一项。

### 4.4 其他平台功能是静默降级

| 功能 | 代码位置 | Linux 行为 |
| --- | --- | --- |
| 鼠标穿透 | `control/mouse.py:155-165` | 直接返回，完全无效 |
| 全局热键 | `control/hotkey.py:81-105` | `register()` 返回 `False` |
| 开机自启 | `platform/autostart.py:22-55` | 非 Windows 返回 `False` |
| AppUserModelID | `platform/appid.py:10-18` | 直接返回 |
| 垂直同步 | `platform/vsync.py:51-52` | 仅 Windows，Linux 走定时器 fallback |
| 置顶保持 | `platform/topmost.py:110-160` | `reassert()` 什么都不做 |
| 窗口从属关系 | `platform/topmost.py:206-211` | `own_by()` 在非 Windows 直接返回 |
| 挡雨窗口枚举 | `platform/shelters.py:27-56` | `ctypes.windll` 失败后返回空列表 |
| 全屏检测 | `platform/envwatch.py:31-79,146-190` | provider 返回 `5`/`None`，不会隐藏或沉底 |
| 光标劫持 | `platform/cursorfx.py:114` | `mock=True`，不移动/锁定真实光标 |

这些代码不会让程序崩溃，但会让功能“看起来有开关、实际没效果”。例如：

- 设置里的“开机自启”在 Linux 上会静默失败。
- 全屏模式 `hide`/`sink` 不会生效，宠物可能盖在全屏游戏上。
- 全局热键状态显示与实际不一致。
- 挡雨窗口永远为空，雨会穿过所有窗口。

### 4.5 UI 大量依赖顶层窗口定位

除了宠物窗，至少这些窗口依赖 `move()`/`setGeometry()`：

- `TabBar`（侧边栏）
- `HudPanel`（状态面板）
- `ControlHud`（手动控制条）
- `RainCard` / `RainDial`（雨循环卡片/表盘）
- 设置、音乐、外观、人格、键位等弹窗

原生 Wayland 下，这不是单个窗口的问题，而是整个 UI 组织方式的问题。

### 4.6 打包和测试仍是 Windows 假设

- `pyproject.toml` 的 classifier 只有 Windows。
- `packaging/build_release.ps1` 使用 PowerShell、Windows 版 PyInstaller、`.exe` 版本信息、Windows 路径分隔符。
- 没有 Linux `.desktop`、图标安装、AppImage/Flatpak/DEB 方案。
- `tests/behavior_check.py` 使用固定 1920×1080 offscreen 画面；帧哈希跨平台不可比。
- `tools/gen_arcs.py --check` 直接比较 gzip 字节；Linux 上会误报，解压后的 JSON 实际一致。

---

## 5. 修改方案

### 5.1 路线 A：X11 / XWayland 后端（推荐）

适用：当前 KDE Wayland 机器，优先“能正常用”，不追求纯 Wayland。

#### P0：恢复桌面可交互

1. **实现 Linux 输入区域/穿透**

   不建议只做“整窗开/关”，因为当前穿透判断依赖全局光标，而光标不可用。建议根据内容计算输入区域：

   - 猫的抓取圆：头、身体、胯。
   - 当前拖拽的物体、可交互物品。
   - 放置模式、拖拽中：临时扩到整个窗口。
   - 其他区域：不接收输入，点击穿透到桌面。

   Wayland 实现：

   - Qt 6.12 的 `QWindow.setMask(QRegion)` 在 `QWaylandWindow` 中会映射到 `wl_surface.set_input_region`。
   - 可以用 `window.windowHandle().setMask(region)` 设置猫身区域。
   - **注意：空 `QRegion` 在 Qt Wayland 中会变成 `set_input_region(nullptr)`，含义是“整个窗口都可输入”，不是穿透。** 整窗穿透应使用 `Qt.WindowTransparentForInput` flag，或设置一个窗口外的极小区域。
   - `setMask` 还会影响 opaque area；在透明背景 + 局部区域下需要实测 KWin 的合成效果。

   X11/XWayland 实现：

   - `QWindow.setMask()` 在 X11 上设置的是 `SHAPE_BOUNDING`，主要用于显示裁剪，不是输入区域；不要直接用它做穿透。
   - 应使用 XFIXES 的 `xcb_xfixes_set_window_shape_region(..., XCB_SHAPE_SK_INPUT, ...)`。
   - 也可以先用 `Qt.WindowTransparentForInput` 做整窗切换，但它会让猫也不可点击，必须和局部区域方案配合。

   只在区域变化时更新，不要每帧反复设置。

2. **修复光标来源**

   可选方案按优先级：

   - **原生 X11 会话**：`QCursor.pos()`/`XQueryPointer` 全局可用，现有逻辑基本能直接工作。
   - **KDE 专用**：KWin 6.8 脚本 API 有 `workspace.cursorPos`（Plasma 5.27+），可通过 KWin 脚本 + DBus/文件桥接把坐标传给 Python。只适用于 KDE。
   - **跨桌面**：`org.freedesktop.portal.InputCapture` 可拿指针事件，但需要用户授权，复杂度和权限成本较高。
   - **降级**：增加“Linux 不跟随光标”开关，用最后一次鼠标事件位置代替；行为会明显改变。

3. **窗口定位与置顶**

   - 短期：启动器检测到 Wayland 时设置 `QT_QPA_PLATFORM=xcb`，走 XWayland。
   - 已实测 XWayland 下 `WindowStaysOnTopHint` 会设置 `_NET_WM_STATE_ABOVE`，`move()` 生效。
   - 补一个 X11 `TopmostKeeper`：定期 `raise_()` / 重设 `_NET_WM_STATE_ABOVE`，避免被其他置顶窗口压下去。
   - 原生 Wayland 若不做 layer-shell 或主窗口内 UI，就无法恢复现有布局。

#### P1：补齐平台功能

4. **全局热键**
   - X11：`XGrabKey` + 原生事件过滤器；映射现有 Ctrl+Alt+P/H/Q/X 和定格单步键。
   - Wayland：`org.freedesktop.portal.GlobalShortcuts`（当前 KDE 已提供）或 KDE `KGlobalAccel`。
   - 第一版不做时，设置里应隐藏或标注“Linux 暂不支持”。

5. **开机自启**
   - 改为 XDG autostart：`~/.config/autostart/slugcatpet.desktop`。
   - `is_enabled()` 检查文件，`set_enabled()` 创建/删除文件，`sync_path()` 更新 `Exec=`。
   - 设置 `QGuiApplication.setDesktopFileName("slugcatpet")`，让 Wayland app ID 和托盘更规范。

6. **全屏检测 / 挡雨窗口**
   - X11：`_NET_ACTIVE_WINDOW`、`_NET_WM_STATE_FULLSCREEN`、窗口几何。
   - 挡雨：`_NET_CLIENT_LIST` / `_NET_CLIENT_LIST_STACKING` 枚举 X11 顶层窗口。
   - 注意：XWayland 只能看到 X11 窗口；原生 Wayland 应用会漏检。
   - 第一版可以接受“Linux 上雨不挡窗口”的降级，但要在文档/设置中说明。

7. **光标劫持**
   - X11 可用 `XWarpPointer`、`XGrabPointer`、XFixes 光标图像实现类似效果。
   - Wayland 普通客户端不能移动全局光标；建议 Linux 默认关闭 `cursor_hijack`，或只保留视觉动画。

8. **托盘与退出路径**
   - KDE 托盘宿主存在，`QSystemTrayIcon` 很可能可用，但需要实际点击验证。
   - `QSystemTrayIcon.geometry()` 在 Wayland 下可能无效，雨循环卡片需要固定锚点，不能依赖 `QCursor.pos()`。
   - 保留 TabBar 的退出按钮作为兜底。

#### P2：打包、测试、性能

9. **Linux 打包**
   - 增加 `.desktop`、图标、启动脚本。
   - 使用 PyInstaller Linux spec 或 AppImage/Flatpak。
   - 继续遵守“发布包不包含游戏素材”的现有安全闸。
   - `pyproject.toml` 增加 Linux classifier。

10. **测试**
    - `tools/gen_arcs.py --check` 改为比较 `gzip.decompress()` 后的内容。
    - `tests/behavior_check.py` 拆分 `--physics` / `--frames`。
    - Linux 物理回归使用平台基线；帧哈希按平台/渲染后端记录。
    - 增加合成图集测试夹具，避免依赖 `~/.slugcatpet/assets`。

11. **高 DPI / 性能**
    - 当前主屏 DPR 2、90Hz；全屏 raster 渲染在 XWayland 下多一层合成拷贝。
    - 需要实测 CPU/GPU 占用、帧率和输入延迟。
    - `trouble` 的 0.246 px 分歧需要在 Windows 上复跑确认。

### 5.2 路线 B：原生 Wayland

适用：必须在纯 Wayland 下运行，且愿意做架构改造。

需要改：

- 所有依赖 `move()` 的 `Qt.Tool` 窗口：
  - 改成画进主全屏窗口，自己做命中测试；或
  - 使用 layer-shell 锚定到屏幕边缘（KWin 对 layer-shell 的支持需验证）。
- 输入区域使用 `wl_surface.set_input_region`，并处理空区域语义。
- 全局光标只能使用 KWin 脚本/DBus、portal InputCapture，或放弃跟随。
- 全局热键使用 GlobalShortcuts portal。
- 全屏检测、挡雨窗口枚举使用 KWin 专用脚本或 portal。
- 置顶没有通用协议，需要 layer-shell 或 KWin 窗口规则。

这不是小补丁，属于 UI 架构 + 平台层改造。

### 5.3 路线 C：Wine / Proton

把现有 Windows exe 放进 Wine/Proton 运行，理论上可绕过部分平台实现：

- Wine 可能支持置顶、透明窗口、托盘。
- 但 DWM 垂直同步、全局热键、光标锁定、窗口枚举、透明点击穿透不保证。
- 需要 Windows 版 Python/PyInstaller 产物，当前 Linux 源码环境不能直接生成。
- 性能和输入延迟通常不如原生。

只适合临时看效果，不建议作为正式移植方案。

---

## 6. 平台后端建议接口

为了避免继续在每个模块里写 `if sys.platform`，建议抽象出平台后端：

```python
class PlatformBackend:
    def set_input_region(self, window, region): ...
    def cursor_pos(self): ...
    def warp_cursor(self, x, y): ...
    def set_topmost(self, window, on): ...
    def foreground_fullscreen(self): ...
    def window_rects(self, skip): ...
    def register_hotkey(self, hk_id, mods, vk): ...
    def unregister_hotkey(self, hk_id): ...
    def set_autostart(self, on): ...
    def set_app_id(self): ...
```

然后按平台提供：

- `platform/win32/`
- `platform/x11/`
- `platform/wayland/`

`window.py`、`control/mouse.py`、`control/hotkey.py`、`envwatch.py` 只依赖接口，不再直接调用 `ctypes.windll`。

---

## 7. 风险矩阵

| 风险 | 可能性 | 影响 | 说明 |
| --- | --- | --- | --- |
| 输入穿透实现后仍有边缘区域挡桌面 | 中 | 高 | 需要按猫身/物品动态计算区域并实测 |
| XWayland 全局光标不可用 | 高 | 高 | 当前已复现 `(0,0)` |
| 原生 Wayland 窗口定位无法恢复 | 高 | 高 | 需要 layer-shell 或 UI 重写 |
| 全屏检测漏掉原生 Wayland 应用 | 高 | 中 | XWayland 只能枚举 X11 窗口 |
| 挡雨窗口漏检 | 高 | 低/中 | 影响雨的遮挡效果，不影响启动 |
| 托盘卡片定位异常 | 中 | 低 | `tray.geometry()` 可能无效 |
| 高 DPI/90Hz 性能不足 | 中 | 中 | 需实测 |
| 帧哈希基线不可跨平台 | 高 | 低 | 测试问题，不是运行问题 |
| `trouble` 物理分歧 | 中 | 低/中 | 需 Windows 复跑确认 |

---

## 8. “可用移植”的验收标准

满足以下条件才算真正可用：

1. 桌面空白区域点击能穿透到下方应用。
2. 点击猫身、拖拽猫、右键菜单正常。
3. TabBar/HUD/控制条能定位、拖动、保存位置。
4. 宠物窗能稳定置顶，不被普通窗口盖住。
5. 光标跟随可工作，或明确提供“Linux 不跟随光标”的降级开关。
6. 托盘可打开设置/音乐/退出；托盘不可用时 TabBar 可退出。
7. 全屏程序能触发隐藏/沉底，或明确禁用。
8. 雨/雪/音频/素材/皮肤正常。
9. Linux 物理回归通过；帧哈希按平台记录。
10. 有 Linux 启动方式（源码 `uv run` 或打包产物）和基本使用说明。

---

## 9. 建议实施顺序

1. **不要直接启动完整 GUI**：先用 offscreen/测试模式验证；当前版本在 Linux 上可能挡住桌面。
2. **先做 XWayland 启动方式 + 输入区域**：让桌面恢复可点击。
3. **再解决光标**：优先考虑 Plasma X11 会话；如果必须留在 Wayland，再加 KDE KWin 脚本或 portal。
4. **补热键、自启、全屏、挡雨**，或明确禁用这些功能。
5. **最后做 Linux 打包和跨平台测试**。

---

## 10. 附：关键测试记录

### 10.1 行为回归

前次实测结果：

- `items`：物理一致，帧哈希 83/100 不同。
- `env`：物理一致，帧哈希 87/90 不同。
- `cursor_play`：物理一致，帧哈希 108/108 不同。
- `trouble`：tick 3437 出现物理分歧，`c0.x` 基线 `510.587`，本次 `510.341`。

解释：

- 帧哈希是整窗 MD5，受 Qt 版本、平台插件、字体/抗锯齿影响，跨平台不可比。
- 物理分歧需要 Windows 复跑确认，不能仅凭 Linux 结果判定回归。

### 10.2 `gen_arcs --check`

Linux 上报告“已过期”，但：

- `gzip.decompress()` 后的 JSON 与仓库内容逐字节一致。
- gzip 头第 9 字节不同（OS 字段，`0x0a` vs `0x03`）。

这是校验方式导致的跨平台误报，不是弧线数据过期。

### 10.3 Qt/XWayland 实验

- `QT_QPA_PLATFORM=wayland`：`QCursor.pos() == (0,0)`。
- `QT_QPA_PLATFORM=xcb`：`QCursor.pos() == (0,0)`。
- XWayland `XQueryPointer`：根坐标 `(0,0)`。
- XWayland `Qt.Tool + Frameless + StaysOnTop`：
  - `_NET_WM_STATE_ABOVE`
  - `_NET_WM_STATE_STAYS_ON_TOP`
  - `_KDE_NET_WM_WINDOW_TYPE_OVERRIDE`
  - 请求位置 300,250 逻辑像素，实际 600,500 物理像素。

### 10.4 Qt 6.12 输入区域能力

- `QWindow.setMask(QRegion)` 存在。
- `QWindow.setFlag(Qt.WindowTransparentForInput, bool)` 存在。
- 在 Wayland/XWayland 下切换 flag 不崩溃；实际穿透效果仍需完整 GUI 实测。
- Qt Wayland 源码中，`setMask` 会更新 `wl_surface` 的 input region；X11 的 `setMask` 设置的是 bounding shape，二者语义不同。

---

## 11. 最终结论与实施结果

| 层面 | 移植前判断 | 最终状态 |
| --- | --- | --- |
| 单全屏透明窗口 + 鼠标穿透 | P0 阻塞 | 已用单 overlay + 动态 `QWindow.setMask()` 输入区域解决 |
| 窗口定位/置顶 | 原生 Wayland 不可用 | KWin JS 脚本固定到目标输出并 `keepAbove` |
| 全局光标读取 | 不可用 | KWin `workspace.cursorPosChanged` → DBus → Python |
| 全局光标写入 | 当时认为不可行 | Qt 6.12 `QCursor.setPos()` / `wp_pointer_warp_v1` + 临时捕获面，best-effort |
| 全屏检测/挡雨窗口 | Windows 专用 | KWin 活动窗口/窗口快照 → DBus |
| 全局热键 | Windows 专用 | KWin `registerShortcut`，KGlobalAccel 检查冲突 |
| 开机自启 | 无 Linux 方案 | XDG autostart，支持源码和打包启动器 |
| Linux 打包 | 无现成方案 | `packaging/linux/install.sh` + uv tool + desktop/图标 |
| KWin 脚本持久安装 | 未实现 | 设置页显式启用，写入 `kwinrc`，`KPackageStructure` 修复 |
| CI/文档 | 无 | Linux/Windows 单元/静态 CI，README 和 Linux 故障排查 |

实际路线与当时建议不同：没有走 XWayland，而是直接实现原生 Wayland，并用 KWin 特权脚本补齐普通客户端缺失的能力。代价是 Plasma/KWin 之外的合成器会降级，且光标写入仍不是系统级 pointer lock。

剩余最终人工验收和已知限制见 `REMAINING_WORK.md`；实现细节见 `PHASE5_CURSOR_WRITE.md`、`PHASE5_PACKAGING.md`。
