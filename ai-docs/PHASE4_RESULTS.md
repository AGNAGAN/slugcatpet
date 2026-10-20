# Phase 4 结果：平台功能补齐

- 日期：2026-10-20
- 后续更新：Wayland 光标写入已通过“临时全屏捕获面 + Qt 6.12 pointer-warp”实现，本文 1.4 节的“Wayland 直接禁用”和“已知限制”中的相应条目已被 `PHASE5_CURSOR_WRITE.md` 取代。
- 环境：KDE Plasma 6.8 / KWin 6.8 / Qt 6.12 / PySide6 6.12
- 测试配置：`SLUGCATPET_HOME=/tmp/opencode/phase3-home`
- 测试 XDG 配置：`XDG_CONFIG_HOME=/tmp/opencode/phase4-config`
- 输出：eDP-1 `1440x900`，HDMI-A-1 `1707x1067`（逻辑坐标 `0,900`）

## 1. 完成内容

### 1.1 XDG 开机自启

`slugcatpet/platform/autostart.py` 新增 Linux 分支：

- 源码运行写：
  ```text
  ~/.config/autostart/org.slugcatpet.SlugcatPet.desktop
  ```
- `Exec` 指向当前 `.venv/bin/python` 和 `run_slugcatpet.py`。
- 冻结/打包运行 `Exec` 指向当前可执行文件，`Path` 指向可执行文件目录。
- 兼容 `XDG_CONFIG_HOME`，测试时不会污染真实配置。
- 路径中的空格、反斜杠、双引号和 `%` 按 Desktop Entry `Exec` 规则转义。
- `sync_path()` 在启动时更新已存在的自启文件；`set_enabled()` 写/删文件并返回是否成功。
- Windows 注册表路径保持不变。

### 1.2 应用标识

`slugcatpet/platform/appid.py` 在非 Windows 上设置：

- `QGuiApplication.setApplicationName("SlugcatPet")`
- 不设置 `applicationDisplayName`，避免 Qt 把 `— SlugcatPet` 追加到 overlay 标题，破坏 KWin 脚本的精确匹配。

`setDesktopFileName()` 仍只在 `org.slugcatpet.SlugcatPet.desktop` 已安装时调用，避免源码运行时 portal 找不到应用。KWin 脚本继续以窗口标题识别 overlay。

> `.desktop` 和图标安装、Linux 打包仍属于 Phase 5；Phase 4 只保证应用名和安装后的 app_id 路径就绪。

### 1.3 输出选择

`slugcatpet/window.py`：

- 新增持久化参数 `output`，空字符串表示跟随主屏。
- `_desired_screen()` 按输出名选择 `QScreen`，找不到时回退主屏。
- `set_output(name)` 切换输出、重建工作区几何、同步 KWin overlay 矩形和输入区域。
- `display_hz()`、`_screen_name()` 改用当前目标屏，而不是固定主屏。
- 监听 `primaryScreenChanged`、`screenAdded`、`screenRemoved`，目标屏变化时重算定时器/后端几何。

`slugcatpet/platform/envwatch.py`：

- `EnvironmentWatcher` 不再固定使用主屏，改为通过 `pet.target_screen()` 取目标输出。
- 输出切换或屏幕增删后，下一次轮询会重新绑定工作区几何并应用。
- Windows 的全屏/前台路径不变。

`slugcatpet/ui/panels/settings.py`：

- 系统页新增“输出屏幕”下拉框：
  - 跟随主屏
  - 每个 `QScreen` 的名称和分辨率
- 选择后立即写盘并切换 overlay。

### 1.4 光标能力降级（历史记录；Wayland 写入已在 Phase 5 实现）

- `PetWindow.cursor_hijack_available` 明确表示能否移动/替换系统光标；Wayland 返回 `False`。
- Wayland 启动时强制关闭本会话的 `cfg_cursor_hijack` / `cfg_cursor_shape`，保留持久化值给 Windows。
- `set_cursor_hijack()` / `set_cursor_shape()` 在 Wayland 直接忽略。
- 设置页两个勾选框在 Wayland 灰显，并显示说明：
  - 猫仍会跟随真实光标；
  - 不会抢光标，也不会替换忙碌样式。
- KWin 光标桥继续提供全局光标位置，因此跟随/舔光标等只读行为仍可用。

### 1.5 托盘雨循环卡片锚点

`main.py::_open_rain()` 的嵌入 UI 路径改为：

1. 调用方显式传入的锚点（标签栏按钮等）；
2. 标签栏可见且几何有效 → 标签栏旁；
3. KWin 光标可用且光标在 overlay 内 → 光标附近；
4. 表盘可见 → 表盘旁；
5. 最后回退到 overlay 右下角。

不再依赖 `QSystemTrayIcon.geometry()` 的全局坐标。

### 1.6 从属窗口

- Wayland 下设置窗和音乐窗保留普通顶层窗口，但把 overlay 设为 transient parent。
- 实现方式：先 `winId()` 创建原生 surface，再调用
  `windowHandle().setTransientParent(overlay.windowHandle())`；仅调用
  `QWidget.setParent()` 在 KWin 中不会留下 `transientFor` 关系。
- 不把设置/音乐变成 overlay 子控件，也不自己 `move()`。
- Setup 窗仍没有 overlay parent。

### 1.7 帧同步

第一版继续使用现有定时器降级路径；未引入 Wayland frame callback。当前性能满足验收，后续只有实测不足时再改。

## 2. 验证

### 2.1 自动检查

```text
uv run python -m unittest discover -s tests -v
Ran 26 tests in 0.003s
OK

uv run ruff check .
All checks passed!

uv run ruff format --check .
285 files already formatted

uv run python tools/params_doc.py --check
ai-docs/PARAMS.md 是最新的
```

新增测试：`tests/test_phase4.py`

- 自启文件写入/读取/删除；
- `sync_path()` 更新旧 `Exec`；
- Desktop Entry `Exec` 转义（空格、引号、`%`）；
- 没有自启文件时 `sync_path()` 不创建文件。

### 2.2 手动验收

- 设置页“输出屏幕”列出：
  - 跟随主屏
  - HDMI-A-1 1707x1067
  - eDP-1 1440x900
- 选择 eDP-1 后：
  - `app.json` 写入 `"output": "eDP-1"`；
  - KWin 中 overlay `frameGeometry` 变为 `0,0 1440x900`（当前地板下延配置为 `1440x932`）；
  - 重启应用后仍绑定 eDP-1。
- 切换输出后 KWin 桥重新加载脚本，overlay 的 `keepAbove` / `skipTaskbar` / `skipSwitcher` 均为 true。
- 目标输出 eDP-1 上的 Alacritty 进入全屏后 overlay 按 `hide` 模式收起；退出全屏后恢复。
- 托盘“雨循环”打开卡片，卡片出现在标签栏旁，未掉到屏幕角落。
- Wayland 设置页两个光标勾选框灰显，说明文字正确；勾选状态不再写回。
- 设置窗和音乐窗能在目标输出上正常打开，没有被改成 overlay 子控件；KWin 中两者的 `transientFor` 都正确指向 `SlugcatPet Overlay`。
- overlay 标题保持 `SlugcatPet Overlay`，KWin 脚本能继续识别并应用 `keepAbove`/`skipTaskbar`/`skipSwitcher`。
- 自启勾选后在隔离的 `XDG_CONFIG_HOME` 下生成 `.desktop`，再次取消后文件删除；`desktop-file-validate` 返回 0。

## 3. 已知限制

- `.desktop` 应用条目和图标尚未安装，源码运行时 KWin 仍显示 `resourceClass python`；这是 Phase 5 打包工作。
- 自启的“注销/重新登录后实际拉起”需要在 Phase 5 的完整桌面会话验收中再确认；当前已验证文件内容、路径和开关行为。
- Wayland 光标写入已在 Phase 5 通过临时捕获面和 Qt pointer-warp 实现；仍不是系统级锁定，见 `PHASE5_CURSOR_WRITE.md`。
- overlay 首次显示抢焦点、QtWayland 退出偶发段错误、内部 `Qt.Popup` 层仍是 Phase 2 遗留，未在 Phase 4 解决。
- Phase 3 的跨输出全屏结论继续有效；Phase 4 另外验证了切换目标屏到 eDP-1 后的全屏收起/恢复。HDMI-A-1 全屏未在切换输出后重复验收，留 Phase 5 最终回归。

## 4. 涉及文件

- `slugcatpet/platform/autostart.py`
- `slugcatpet/platform/appid.py`
- `slugcatpet/platform/envwatch.py`
- `slugcatpet/ui/panels/settings.py`
- `slugcatpet/window.py`
- `slugcatpet/main.py`
- `slugcatpet/i18n.py`
- `tests/test_phase4.py`
- `ai-docs/REMAINING_WORK.md`
- `ai-docs/NATIVE_WAYLAND_PORT_PLAN.md`
