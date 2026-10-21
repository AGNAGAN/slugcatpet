# Phase 3 结果：KWin 桥、全屏检测、挡雨窗口与全局热键

- 日期：2026-10-20
- 环境：KDE Plasma 6.8 / KWin 6.8 / Qt 6.12 / PySide6 6.12
- 目标输出：HDMI-A-1，逻辑几何 `0,900 1707x1067`
- 测试配置：`SLUGCATPET_HOME=/tmp/opencode/phase3-home`

## 1. 完成内容

### 1.1 DBus 桥

`slugcatpet/platform/wayland/kwin_bridge.py` 新增：

- `FullscreenChanged(bool, int, int, int, int)`
- `WindowListChanged(str)`，JSON 快照
- `HotkeyPressed(int)`
- `HotkeyStatus(str)`
- `Log(str)`

后端新增能力：

- `supports_fullscreen`
- `supports_shelters`
- `supports_hotkeys`
- `foreground_fullscreen()`
- `window_rects()`
- `parse_window_rects()`
- `reload()`

全屏判定由 Python 完成：只有活动窗口的全屏矩形**覆盖 overlay 所在输出**时才返回 `True`。全屏窗口在另一块屏幕上时不会误收起 overlay。

### 1.2 KWin 脚本

`slugcatpet/platform/wayland/kwin_script/contents/code/main.js` 现在会：

- 跟踪活动窗口的 `fullScreen` 状态和几何。
- 监听窗口几何、最小化、隐藏、桌面/活动、输出和关闭变化。
- 推送挡雨窗口 JSON 快照，过滤 overlay 自身、面板、tooltip、通知、最小化窗口等。
- 节流推送全局光标位置。
- 注册固定全局快捷键：
  - `Ctrl+Alt+Q` 中止光标劫持
  - `Ctrl+Alt+X` 退出
  - `Ctrl+Alt+H` HUD
  - `Ctrl+Alt+P` 定格
  - `Ctrl+Alt+Right` 单步
  - `Ctrl+Alt+Shift+Right` 十步
- 推送每个快捷键的注册状态。

### 1.3 运行时接线

- `EnvironmentWatcher` 支持 `fullscreen_provider`；Wayland 下使用 KWin 的活动窗口状态，不再依赖 Win32 API。
- `PetWindow._poll_shelters()` 在 Wayland 下直接使用后端返回的 overlay-local 矩形，不再用 `self.x()/self.y()/dpr` 做全局换算。
- `HotkeyFilter` 接收后端 `hotkey_pressed`，按当前有效 id 过滤；Windows 仍走 `RegisterHotKey`。
- `main.py` 只在 Wayland 下提供 KWin 全屏 provider；桥未就绪时返回 `None`，保持原状态。
- 设置页新增 “Wayland / KWin” 状态区：
  - 显示 KWin 集成是否连接；
  - 显示未生效的全局热键；
  - 提供“重新加载 KWin 脚本”按钮。

### 1.4 热键冲突检测

KWin 的 `registerShortcut()` 即使快捷键被占用也会返回成功，因此不能只看脚本状态。Python 侧在脚本加载后查询 KGlobalAccel：

- 用 `action(keyCode)` 查当前组合键最终属于哪个 action；
- 只有 owner 是 `slugcatpet_<id>` 才算真正生效；
- 冲突项进入 `hotkey_conflicts()`，设置页和日志都会显示。

测试环境中 `Ctrl+Alt+P` 被旧的 `SlugcatPet Phase0 Test` 占用，`Ctrl+Alt+Right` 被 Mineradio 占用，应用正确报告了这两项冲突；HUD 快捷键正常触发。

## 2. 验证结果

### 2.1 自动测试

```text
uv run ruff check .                         通过
uv run ruff format --check .                通过（283 个文件）
uv run python -m unittest discover -s tests 23 个测试通过
uv run python tools/params_doc.py --check   通过
```

新增 `tests/test_wayland_phase3.py`，覆盖：

- 窗口快照解析、输出过滤、坏数据跳过、overlay-local 坐标换算；
- 目标输出全屏覆盖判定；
- 其他输出全屏不触发收起；
- 状态未知时返回 `None`；
- `EnvironmentWatcher` 的全屏 hide/restore 防抖；
- 快捷键序列和 KGlobalAccel 键码。

### 2.2 实际交互

1. **脚本加载**
   - `loadScript("slugcatpet")` 成功，`isScriptLoaded` 为 true。
   - DBus 观察到 `OverlayGeometryChanged`、`CursorMoved`、`WindowListChanged`、`FullscreenChanged`。

2. **HUD 全局热键**
   - 用虚拟键盘发送 `Ctrl+Alt+H`。
   - `org.slugcatpet.Bridge.HotkeyPressed id=3` 收到两次。
   - 直接调用 `invokeShortcut("slugcatpet_3")` 也能触发，确认脚本回调链正确。

3. **HDMI 全屏收起/恢复**
   - 用临时 KWin 脚本把测试窗口移到 HDMI-A-1 并设为全屏。
   - overlay 在约 1 秒内隐藏，HDMI 截图只显示全屏测试窗口。
   - 关闭测试窗口后 overlay 自动恢复，截图重新出现猫和雨表盘。

4. **eDP 全屏不影响 HDMI overlay**
   - 测试窗口在 eDP-1 全屏时，HDMI-A-1 截图仍显示 overlay。
   - 与 `foreground_fullscreen()` 的多输出判定一致。

5. **挡雨窗口快照**
   - 把 Alacritty 从 `0,900 1707x1067` 移到 `100,950 800x600`。
   - 收到 `WindowListChanged`：
     `{"caption":"OC | 仓库分析","resourceClass":"Alacritty","output":"HDMI-A-1","x":100,"y":950,"w":800,"h":600,...}`
   - Python 侧换算为 `100,50 800x600` 的 overlay-local 矩形。
   - 移回后快照恢复。

6. **设置页**
   - Wayland / KWin 状态区可见。
   - 显示“KWin 集成已连接：置顶、全屏检测、挡雨窗口和全局热键可用。”
   - 显示未生效快捷键：`Ctrl+Alt+P, Ctrl+Alt+Right`。
   - “重新加载 KWin 脚本”按钮存在。

## 3. 已知限制

- Phase 3 当时仍在运行时 `loadScript`；Phase 5 已增加 `kwin_install`、设置页显式开关和 `~/.local/share/kwin/scripts/slugcatpet` 持久安装，详见 `PHASE5_PACKAGING.md`。
- 脚本是 KDE 专用；GNOME/Sway 降级为无置顶、无全局光标、无热键。
- 热键冲突检测使用 KGlobalAccel 的兼容方法 `action(int)`；在当前 Plasma 6.8 可用，后续版本若删除该兼容接口需要改为解析 `shortcutKeys`。
- 全屏测试使用临时 KWin 脚本强制窗口几何，尚未用 Rain World 实际全屏窗口验收。
- 全屏检测只跟随**活动**窗口；全屏窗口失焦后不会继续隐藏 overlay。
- overlay 首次显示抢焦点已由 Phase 5 的 KWin 脚本恢复逻辑处理；QtWayland 退出偶发段错误仍在 Phase 2 遗留清单中。
- 托盘雨循环卡片已在 Phase 4 改为标签栏/光标/表盘/右下角锚点。
- 设置/音乐内部的皮肤、尾巴、音量弹层仍是 `Qt.Popup + mapToGlobal`，仍待清理。

## 4. 涉及文件

- `slugcatpet/platform/wayland/kwin_bridge.py`
- `slugcatpet/platform/wayland/kwin_script/contents/code/main.js`
- `slugcatpet/platform/backend.py`
- `slugcatpet/platform/envwatch.py`
- `slugcatpet/control/hotkey.py`
- `slugcatpet/window.py`
- `slugcatpet/main.py`
- `slugcatpet/ui/panels/settings.py`
- `slugcatpet/i18n.py`
- `tests/test_wayland_phase3.py`

## 5. 下一步

进入 Phase 4：

1. XDG autostart。
2. 输出选择设置项。
3. 光标劫持/形状设置降级。
4. 托盘雨循环卡片锚点。
5. 清理 Phase 2 遗留的 `Qt.Popup` 弹层和 overlay 首次焦点问题。

Phase 5 的 KWin 脚本安装、desktop 文件、图标、Linux/Windows CI 和 README/故障排查已完成；剩余最终人工验收见 `REMAINING_WORK.md`。
