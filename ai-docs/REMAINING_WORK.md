# 原生 Wayland 迁移剩余工作

- 日期：2026-10-20
- 依据：`PHASE0_RESULTS.md`、`PHASE1_RESULTS.md`、`PHASE2_RESULTS.md`、`PHASE3_RESULTS.md` 与当前代码审计
- 用途：记录 Phase 0–3 之后仍未完成的工作，作为 Phase 4–5 的执行清单
- 结论：**Phase 0–3 已完成（Phase 3 的脚本安装/启用留到 Phase 5）；Phase 4、Phase 5 尚未开始。**

---

## 1. 状态总览

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| Phase 0 | 已完成 | 可行性闸门结论为 Go（有条件） |
| Phase 1 | 已完成 | 单主表面、输入区域、KWin 几何/置顶、光标桥 |
| Phase 2 | 已完成（第一版） | UI 嵌入 overlay、局部坐标、菜单/卡片/提示 |
| Phase 3 | 已完成（开发期） | 全屏、窗口快照、热键、冲突提示、设置页状态与重载；脚本安装/启用留到 Phase 5 |
| Phase 4 | 未开始 | XDG 自启、输出选择、光标功能降级、托盘锚点等 |
| Phase 5 | 未开始 | Linux 打包、KWin 脚本安装、完整测试、README/故障排查、CI |

---

## 2. Phase 3：KWin 桥剩余工作

### 2.1 已完成的基础

- KWin 脚本运行时加载/卸载。
- overlay 固定到目标几何。
- `keepAbove`、`skipTaskbar`、`skipSwitcher`。
- `workspace.cursorPosChanged` → DBus → Python 光标位置。
- DBus 服务与 `CursorMoved`、`OverlayGeometryChanged`、`Log`。
- 应用退出时正常卸载脚本。

相关文件：

- `slugcatpet/platform/wayland/kwin_bridge.py`
- `slugcatpet/platform/wayland/kwin_script/contents/code/main.js`
- `slugcatpet/platform/wayland/kwin_script/metadata.json`

### 2.2 已完成

- [x] 增加 DBus 信号/槽：
  - `FullscreenChanged`
  - `WindowListChanged`
  - `HotkeyPressed`
  - `HotkeyStatus`
- [x] 增加后端能力标志：
  - `supports_fullscreen`
  - `supports_shelters`
  - `supports_hotkeys`
- [x] 扩展 KWin 脚本：
  - 跟踪活动窗口和 `fullScreenChanged`
  - 生成窗口矩形 JSON 快照并推送
  - 过滤 overlay、dock/panel、tooltip、最小化窗口
  - 注册 `GLOBAL_KEYS` + `FROZEN_KEYS`
  - 输出/桌面变化时重新应用几何
- [x] 全屏检测接回 `EnvironmentWatcher`
  - 增加 `fullscreen_provider`
  - Wayland 下不再依赖 `SHQueryUserNotificationState` / `GetForegroundWindow`
  - 未更新时返回 `None`，保持原状态，不能误隐藏
- [x] 挡雨窗口接回 `PetWindow._poll_shelters()`
  - 新增 KWin 窗口快照提供者
  - 直接返回 overlay-local 逻辑矩形
  - 去掉 `self.x()/self.y()/dpr` 的全局换算
  - 桥不可用时返回空列表且不崩溃
- [x] 全局热键 Linux 路径
  - KWin `HotkeyPressed` 接到现有 `HotkeyFilter.triggered`
  - 用 KGlobalAccel `action(keyCode)` 检查快捷键最终归属
  - 冲突在日志和设置页给出可见提示
- [x] 设置页增加 KWin 状态与“重新加载 KWin 脚本”
- [x] 多输出实测
  - HDMI 全屏收起/恢复
  - eDP 全屏不误收起 HDMI overlay
  - 挡雨窗口跨输出过滤

详细记录见 `ai-docs/PHASE3_RESULTS.md`。

### 2.3 仍待完成（转入 Phase 5）

- [ ] KWin 脚本安装/启用
  - 安装到 `~/.local/share/kwin/scripts/slugcatpet/`
  - 写 `kwinrc`，调用 `org.kde.KWin.reconfigure`
  - 设置页增加“启用 KWin 集成”开关
  - 必须由用户明确启用，不能静默修改系统窗口行为
- [ ] 输出选择设置项（Phase 4）
- [ ] 用 Rain World 实际全屏窗口做一次最终验收（Phase 5）

### 2.4 Phase 3 退出标准

- [x] 全屏程序能按 `fullscreen_mode` 触发 hide/sink，退出全屏后恢复。
- [x] 挡雨窗口近似正确；KWin 快照不可用时雨不挡窗口且不崩溃。
- [x] 冻结/HUD/退出/步进热键可用，冲突有提示。
- [x] 关闭 KWin 脚本后明确降级，设置页能看到状态。
- [x] eDP 与 HDMI 至少各完成一次实际交互验证。

---

## 3. Phase 4：平台功能

- [ ] XDG 开机自启
  - `platform/autostart.py` 目前只支持 Windows 注册表
  - 写/删 `~/.config/autostart/org.slugcatpet.SlugcatPet.desktop`
  - 当前 Linux 上设置页的“开机自动启动”实际无效
- [ ] 应用标识与桌面文件
  - `set_desktop_file_name()` 已有，但只有安装 `.desktop` 后才设置
  - 安装 `org.slugcatpet.SlugcatPet.desktop` 和图标
- [ ] 光标劫持/形状降级
  - Wayland 下 `cursorfx` 已是 mock
  - 设置页两个勾选框仍可操作，仅有一行说明
  - 应灰显或明确禁用，避免用户误以为生效
- [ ] 托盘雨循环卡片锚点
  - 当前：表盘可见 → 表盘；否则 overlay 右下角
  - 计划：标签栏可见 → 标签栏旁；KWin 光标可用 → 光标附近；最后才是右下角
  - 修改 `main.py` 的 `_open_rain()`
- [ ] 置顶与从属窗口收尾
  - Wayland 下 `TopmostKeeper` 是 no-op，属预期
  - 清理旧顶层窗口假设，确认设置/音乐只作为 transient 顶层存在
- [ ] 帧同步
  - 第一版继续使用定时器降级
  - 只有实测性能不足时再考虑 frame callback / `frameSwapped`

### Phase 4 退出标准

- 自启开关可写/删 `.desktop`，重启后生效。
- 全屏程序能隐藏/沉底，退出后恢复。
- 挡雨窗口近似正确。
- 托盘可用；雨循环卡片出现在合理位置。
- 不支持的功能在设置页有明确说明，不静默失败。

---

## 4. Phase 5：打包、测试、文档

### 4.1 Linux 打包

- [ ] 新增 `packaging/linux/`：
  - `org.slugcatpet.SlugcatPet.desktop`
  - `slugcatpet.svg`
  - `install.sh`
  - `uninstall.sh`
  - 可选 `slugcatpet.spec`
- [ ] 安装 KWin 脚本、desktop 文件、图标。
- [ ] 不打包 Rain World 游戏素材，首次启动仍走 `gameassets` 导入。
- [ ] 保留 `uv run slugcatpet` 源码运行方式。
- [ ] `pyproject.toml` 增加 Linux classifier / 多平台描述。

### 4.2 测试

- [ ] 输入区域测试：猫/面板/拖拽状态并集、空区域 1×1、clamp。
- [ ] 坐标测试：全局 → overlay → canvas，DPR 1.5/2.0，多屏。
- [ ] KWin 桥测试：DBus 参数、JSON 解析、服务注册失败降级。
- [ ] overlay 布局测试：geometry、动画、持久化迁移。
- [ ] KWin 集成测试：overlay 尺寸、keepAbove、光标、窗口快照、热键。
- [ ] 现有 offscreen 行为回归保持通过；物理不受窗口层影响。
- [ ] 手动验收：点击穿透、拖猫、右键菜单、HUD/标签栏、托盘、全屏隐藏、音频。
- [ ] Windows 行为回归。

### 4.3 文档与 CI

- [ ] README 增加 Linux 安装、KWin 集成、降级模式、已知限制。
- [ ] 更新 `PORTABILITY_ANALYSIS.md` 的最终结论。
- [ ] 新增 Wayland 故障排查：
  - KWin 脚本未加载
  - 光标不更新
  - 输入区域异常
  - 全屏检测失效
- [ ] Linux CI：ruff、`params_doc --check`、offscreen 行为测试。
- [ ] Windows CI：完整行为回归。
- [ ] KWin 集成测试至少提供本地脚本，不要求 GitHub 托管 runner 有 Plasma 会话。

---

## 5. Phase 2 遗留清理

这些不阻塞 Phase 3，但建议排进收尾：

- [ ] 设置/音乐内部的皮肤、尾巴、音量弹层仍是 `Qt.Popup + mapToGlobal`。
- [ ] 首次启动 `SetupPanel` 在 overlay 创建之前运行，没有 transient parent。
- [ ] overlay 首次显示抢焦点问题仍未解决。
- [ ] 托盘雨卡片仍是右下角降级锚点。
- [ ] 偶发 QtWayland 退出段错误（`QWaylandWindow::decoration`），尚未稳定复现。
- [ ] 整理提交：
  - 当前源码改动未提交；
  - `ai-docs` 新文档为 untracked；
  - `pyproject.toml`、`uv.lock` 含原有用户改动，需要分开处理。

---

## 6. 建议执行顺序

1. Phase 4：XDG 自启、输出选择、光标设置降级、托盘锚点。
2. 清理 Phase 2 遗留的 `Qt.Popup` 弹层、overlay 首次焦点和退出段错误。
3. Phase 5：KWin 脚本安装/启用、desktop 文件、图标、Linux CI。
4. 用 Rain World 实际全屏窗口做最终验收。
5. 最后统一分阶段提交。

---

## 7. 当前仓库状态

- 测试应用仍在运行（隔离配置 `/tmp/opencode/phase3-home`），KWin 脚本已加载。
- Phase 0–3 的源码改动尚未提交。
- `ai-docs/` 下新增文档尚未纳入版本控制。
- 最近一次自动检查结果：
  - `uv run ruff check .`：通过
  - `uv run ruff format --check .`：通过，283 个文件
  - `uv run python -m unittest discover -s tests`：23 个测试通过
  - `uv run python tools/params_doc.py --check`：通过
